import logging
import json
import requests
import io
import pandas as pd
import hmac
from flask import Flask, request, jsonify, render_template, send_file, session, redirect, url_for
from config import Config
from models import db, Message, MessageStatus, Contact, Tag, contact_tags, Campaign, CampaignLog
import threading
import time as time_module
from event_handlers import process_event
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload
from datetime import datetime, timedelta, timezone
import logging
import pytz
import mimetypes

# Fix MIME types for Windows/Local
mimetypes.add_type('audio/ogg', '.oga')
mimetypes.add_type('audio/ogg', '.ogg')
mimetypes.add_type('audio/ogg', '.opus')

app = Flask(__name__)
logger = logging.getLogger(__name__)

# Zona horaria de Argentina
ARGENTINA_TZ = pytz.timezone('America/Argentina/Buenos_Aires')

# Filtro Jinja2 para convertir UTC a hora Argentina
@app.template_filter('to_argentina')
def to_argentina_filter(dt):
    """Convierte datetime UTC a hora de Argentina."""
    if dt is None:
        return ''
    # Si el datetime es naive, asumir que es UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ARGENTINA_TZ)

# Configuración de la base de datos
app.config['SQLALCHEMY_DATABASE_URI'] = Config.DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = Config.SECRET_KEY

# Inicializar SQLAlchemy
db.init_app(app)

# Crear tablas al iniciar
with app.app_context():
    db.create_all()

# Importar servicio de WhatsApp (después de crear app)
from whatsapp_service import whatsapp_api

# Rutas públicas que no requieren autenticación
PUBLIC_PATHS = {'/', '/login', '/logout', '/webhook', '/chatwoot-webhook'}

@app.before_request
def check_auth():
    if request.path in PUBLIC_PATHS or request.path.startswith('/static/'):
        return None
    if not session.get('logged_in'):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Unauthorized'}), 401
        return redirect(url_for('login'))

@app.route("/", methods=["GET"])
def index():
    return redirect(url_for('dashboard'))

@app.route("/login", methods=["GET"])
def login():
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    return render_template('login.html', error=False)

@app.route("/login", methods=["POST"])
def login_post():
    password = request.form.get('password', '')
    if hmac.compare_digest(password, Config.LOGIN_PASSWORD):
        session['logged_in'] = True
        return redirect(url_for('dashboard'))
    return render_template('login.html', error=True)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """
    Endpoint de verificación para Meta (Facebook).
    Meta enviará un GET request con hub.mode, hub.verify_token y hub.challenge.
    """
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == Config.VERIFY_TOKEN:
            logger.info("WEBHOOK_VERIFIED")
            return challenge, 200
        else:
            logger.error("Verificación fallida. Token recibido no coincide.")
            return "Verification token mismatch", 403
    
    return "Hello world", 200

@app.route("/webhook", methods=["POST"])
def webhook_handler():
    """
    Endpoint principal para recibir eventos de WhatsApp.
    """
    try:
        data = request.json
        if not data:
            return "No data received", 400
            
        # Procesar el evento (loguear, guardar, reenviar)
        process_event(data)
        
        return "EVENT_RECEIVED", 200
        
    except Exception as e:
        logger.error(f"Error procesando el webhook: {e}")
        return "Internal Server Error", 500

@app.route("/dashboard")
def dashboard():
    """Dashboard para visualizar conversaciones tipo WhatsApp."""
    selected_phone = request.args.get('phone')
    
    # Estadísticas generales
    total = Message.query.count()
    sent = db.session.query(func.count(MessageStatus.id)).filter(
        MessageStatus.status == 'sent'
    ).scalar() or 0
    read = db.session.query(func.count(MessageStatus.id)).filter(
        MessageStatus.status == 'read'
    ).scalar() or 0
    failed = db.session.query(func.count(MessageStatus.id)).filter(
        MessageStatus.status == 'failed'
    ).scalar() or 0
    
    stats = {'total': total, 'sent': sent, 'read': read, 'failed': failed}
    
    # Lista de contactos con estadísticas y datos CRM
    # 1. Obtener estadísticas de mensajes por teléfono
    stats_query = db.session.query(
        Message.phone_number,
        func.count(Message.id).label('message_count'),
        func.max(Message.timestamp).label('last_timestamp'),
        func.max(Message.content).label('last_message')
    ).filter(
        Message.phone_number.notin_(['unknown', 'outbound', ''])
    ).group_by(Message.phone_number).order_by(func.max(Message.timestamp).desc()).limit(100).all()
    
    # 2. Obtener contactos para enriquecer la data
    # Optimizamos trayendo solo los necesarios si hay muchos, pero para dashboard está bien traer los relevantes
    phones_in_view = [s.phone_number for s in stats_query]
    contacts_map = {}
    if phones_in_view:
        found_contacts = Contact.query.filter(Contact.phone_number.in_(phones_in_view)).all()
        contacts_map = {c.phone_number: c for c in found_contacts}
    
    contacts = []
    for s in stats_query:
        contact = contacts_map.get(s.phone_number)
        contacts.append({
            'phone_number': s.phone_number,
            'message_count': s.message_count,
            'last_timestamp': s.last_timestamp,
            'last_message': (s.last_message[:50] + '...') if s.last_message and len(s.last_message) > 50 else s.last_message,
            'name': contact.name if contact else None,
            'tags': contact.tags if contact else []
        })
    
    # Si hay contacto seleccionado, obtener sus mensajes
    messages = []
    contact_stats = {}
    selected_contact = None
    contact_details = None
    
    # Límite de mensajes para mostrar en el chat (optimización)
    MESSAGE_LIMIT = 100

    if selected_phone:
        selected_contact = selected_phone
        # Optimización: Solo traer los últimos 100 mensajes
        # Primero obtenemos los últimos N por fecha descendente (los más nuevos)
        # Luego los reordenamos ascendente para mostrar en el chat
        recent_messages = Message.query.filter_by(phone_number=selected_phone)\
            .order_by(Message.timestamp.desc())\
            .limit(MESSAGE_LIMIT).all()
        messages = sorted(recent_messages, key=lambda m: m.timestamp)
        
        contact_details = Contact.query.filter_by(phone_number=selected_phone).first()
        
        # Estadísticas del contacto (estas sí pueden requerir contar todos, o podemos estimar)
        # Para mantener rendimiento, calculamos stats solo de lo que traemos o hacemos count query aparte si es crítico
        # Hacemos query ligera solo para cuentas
        outbound_count = Message.query.filter_by(phone_number=selected_phone, direction='outbound').count()
        # Estimación rápida basada en lo cargado para evitar query pesada de status específico
        # Si se necesita precisión absoluta, se deben hacer queries count() específicas
        
        outbound_msgs = [m for m in messages if m.direction == 'outbound']
        contact_stats = {
            'message_count': Message.query.filter_by(phone_number=selected_phone).count(), # Total real
            'sent': sum(1 for m in outbound_msgs if m.latest_status in ['sent', 'delivered', 'read']),
            'delivered': sum(1 for m in outbound_msgs if m.latest_status in ['delivered', 'read']),
            'read': sum(1 for m in outbound_msgs if m.latest_status == 'read')
        }
    elif contacts:
        # Seleccionar primer contacto por defecto
        selected_contact = contacts[0]['phone_number']
        recent_messages = Message.query.filter_by(phone_number=selected_contact)\
            .order_by(Message.timestamp.desc())\
            .limit(MESSAGE_LIMIT).all()
        messages = sorted(recent_messages, key=lambda m: m.timestamp)
        
        outbound_msgs = [m for m in messages if m.direction == 'outbound']
        contact_stats = {
            'message_count': Message.query.filter_by(phone_number=selected_contact).count(),
            'sent': sum(1 for m in outbound_msgs if m.latest_status in ['sent', 'delivered', 'read']),
            'delivered': sum(1 for m in outbound_msgs if m.latest_status in ['delivered', 'read']),
            'read': sum(1 for m in outbound_msgs if m.latest_status == 'read')
        }
    
    # Datos para gráficos
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    
    # Mensajes por día
    messages_by_day = db.session.query(
        func.date(Message.timestamp).label('date'),
        func.count(Message.id).label('count')
    ).filter(Message.timestamp >= seven_days_ago).group_by(func.date(Message.timestamp)).all()
    
    # Mensajes por hora
    messages_by_hour = db.session.query(
        func.extract('hour', Message.timestamp).label('hour'),
        func.count(Message.id).label('count')
    ).group_by(func.extract('hour', Message.timestamp)).order_by('hour').all()
    
    # Entrantes vs Salientes
    inbound_count = Message.query.filter_by(direction='inbound').count()
    outbound_count = Message.query.filter_by(direction='outbound').count()
    
    chart_data = {
        'messages_by_day': [{'date': str(d.date), 'count': d.count} for d in messages_by_day],
        'messages_by_hour': [{'hour': int(h.hour) if h.hour else 0, 'count': h.count} for h in messages_by_hour],
        'direction_stats': {'inbound': inbound_count, 'outbound': outbound_count}
    }
    
    # Verificar ventana de 24 horas para envío de mensajes
    can_send_free_text = False
    last_inbound_msg = None
    templates = []
    whatsapp_configured = whatsapp_api.is_configured()
    
    if selected_contact and whatsapp_configured:
        # Buscar último mensaje entrante del contacto
        twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
        last_inbound = Message.query.filter_by(
            phone_number=selected_contact,
            direction='inbound'
        ).filter(Message.timestamp >= twenty_four_hours_ago).order_by(Message.timestamp.desc()).first()
        
        if last_inbound:
            can_send_free_text = True
            last_inbound_msg = last_inbound.timestamp
        
        # Obtener templates aprobados
        templates_result = whatsapp_api.get_templates()
        templates = [t for t in templates_result.get("templates", []) if t.get("status") == "APPROVED"]
    
    return render_template('dashboard.html', 
                         stats=stats, 
                         contacts=contacts, 
                         messages=messages,
                         selected_contact=selected_contact,
                         contact_stats=contact_stats,
                         chart_data=chart_data,
                         can_send_free_text=can_send_free_text,
                         last_inbound_msg=last_inbound_msg,
                         templates=templates,
                         whatsapp_configured=whatsapp_configured)

@app.route("/analytics")
def analytics():
    """Página de analytics con estadísticas detalladas."""
    # Zona horaria de Argentina
    ARGENTINA_TZ = 'America/Argentina/Buenos_Aires'
    
    # Estadísticas generales
    total_messages = Message.query.count()
    outbound = Message.query.filter_by(direction='outbound').count()
    inbound = Message.query.filter_by(direction='inbound').count()
    
    read = db.session.query(func.count(MessageStatus.id)).filter(
        MessageStatus.status == 'read'
    ).scalar() or 0
    delivered = db.session.query(func.count(MessageStatus.id)).filter(
        MessageStatus.status == 'delivered'
    ).scalar() or 0
    sent = db.session.query(func.count(MessageStatus.id)).filter(
        MessageStatus.status == 'sent'
    ).scalar() or 0
    failed = db.session.query(func.count(MessageStatus.id)).filter(
        MessageStatus.status == 'failed'
    ).scalar() or 0
    
    stats = {
        'total_messages': total_messages,
        'outbound': outbound,
        'inbound': inbound,
        'read': read,
        'delivered': delivered,
        'sent': sent,
        'failed': failed
    }
    
    # Datos para gráficos - últimos 30 días
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    # Mensajes por día (hora Argentina) - usando SQL directo para timezone
    messages_by_day = db.session.execute(db.text(f"""
        SELECT 
            DATE(timestamp AT TIME ZONE 'UTC' AT TIME ZONE '{ARGENTINA_TZ}') as date,
            direction,
            COUNT(*) as count
        FROM whatsapp_messages
        WHERE timestamp >= :since
        GROUP BY DATE(timestamp AT TIME ZONE 'UTC' AT TIME ZONE '{ARGENTINA_TZ}'), direction
    """), {'since': thirty_days_ago}).fetchall()
    
    # Formatear datos por día
    day_data = {}
    for row in messages_by_day:
        date_str = str(row.date) if row.date else ''
        if date_str not in day_data:
            day_data[date_str] = {'date': date_str, 'inbound': 0, 'outbound': 0}
        if row.direction == 'inbound':
            day_data[date_str]['inbound'] = row.count
        else:
            day_data[date_str]['outbound'] = row.count
    
    # Mensajes enviados por hora (hora Argentina)
    sent_by_hour = db.session.execute(db.text(f"""
        SELECT 
            EXTRACT(HOUR FROM timestamp AT TIME ZONE 'UTC' AT TIME ZONE '{ARGENTINA_TZ}')::int as hour,
            COUNT(*) as count
        FROM whatsapp_messages
        WHERE direction = 'outbound'
        GROUP BY EXTRACT(HOUR FROM timestamp AT TIME ZONE 'UTC' AT TIME ZONE '{ARGENTINA_TZ}')
        ORDER BY hour
    """)).fetchall()
    
    # Mensajes leídos por hora (hora Argentina)
    read_by_hour = db.session.execute(db.text(f"""
        SELECT 
            EXTRACT(HOUR FROM timestamp AT TIME ZONE 'UTC' AT TIME ZONE '{ARGENTINA_TZ}')::int as hour,
            COUNT(*) as count
        FROM whatsapp_message_statuses
        WHERE status = 'read'
        GROUP BY EXTRACT(HOUR FROM timestamp AT TIME ZONE 'UTC' AT TIME ZONE '{ARGENTINA_TZ}')
        ORDER BY hour
    """)).fetchall()
    
    # Mensajes por día de la semana (hora Argentina)
    by_day_of_week = db.session.execute(db.text(f"""
        SELECT 
            EXTRACT(DOW FROM timestamp AT TIME ZONE 'UTC' AT TIME ZONE '{ARGENTINA_TZ}')::int as dow,
            COUNT(*) as count
        FROM whatsapp_messages
        GROUP BY EXTRACT(DOW FROM timestamp AT TIME ZONE 'UTC' AT TIME ZONE '{ARGENTINA_TZ}')
    """)).fetchall()
    
    dow_counts = [0] * 7
    for row in by_day_of_week:
        if row.dow is not None:
            idx = int(row.dow)
            # Ajustar para que lunes sea 0
            idx = (idx - 1) % 7
            dow_counts[idx] = row.count
    
    # Top contactos
    top_contacts = db.session.query(
        Message.phone_number,
        func.count(Message.id).label('count')
    ).filter(
        Message.phone_number.notin_(['unknown', 'outbound', ''])
    ).group_by(Message.phone_number).order_by(func.count(Message.id).desc()).limit(5).all()
    
    chart_data = {
        'messages_by_day': sorted(day_data.values(), key=lambda x: x['date']),
        'status_dist': {'read': read, 'delivered': delivered, 'sent': sent, 'failed': failed},
        'sent_by_hour': [{'hour': int(h.hour) if h.hour else 0, 'count': h.count} for h in sent_by_hour],
        'read_by_hour': [{'hour': int(h.hour) if h.hour else 0, 'count': h.count} for h in read_by_hour],
        'by_day_of_week': dow_counts,
        'direction': {'inbound': inbound, 'outbound': outbound},
        'top_contacts': [{'phone': c.phone_number, 'count': c.count} for c in top_contacts]
    }
    
    # ========== ESTADÍSTICAS DE TEMPLATES ==========
    # Obtener mensajes salientes de los últimos 30 días (no todo el historial)
    outbound_messages = Message.query.filter(
        Message.direction == 'outbound',
        Message.timestamp >= thirty_days_ago
    ).all()
    
    # Obtener templates de la API para mapeo
    templates_info = whatsapp_api.get_templates().get("templates", [])
    
    # Agrupar por "nombre" de template
    stats_by_template = {} # key: template_name, value: {sent: 0, read: 0}
    
    import re
    # Pre-calcular patrones de templates para mayor velocidad
    template_patterns = []
    for t in templates_info:
        for comp in t.get("components", []):
            if comp.get("type") == "BODY":
                body = comp.get("text", "").strip()
                if not body: continue
                # Limpiar el escape de re.escape para que sea más flexible
                # En lugar de re.escape completo, escapamos solo caracteres especiales pero no espacios
                pattern = re.escape(body)
                # Reemplazar variables {{n}} por un comodín
                pattern = re.sub(r'\\\{\\\{\d+\\\}\\\}', '.*?', pattern)
                # Permitir cualquier cantidad de espacios/newslines donde haya uno
                pattern = re.sub(r'\\ ', r'\\s+', pattern)
                pattern = re.sub(r'\\n', r'\\s*', pattern)
                
                template_patterns.append({
                    'name': t.get("name"), 
                    'regex': f".*{pattern}.*" # Permitir que esté contenido (por si hay Header/Footer)
                })
    
    for msg in outbound_messages:
        t_name = None
        content = (msg.content or "").strip()
        if not content: continue
        
        # 1. Prioridad: Mensajes ya marcados con [Template: nombre]
        match_name = re.match(r'^\[Template: ([^\]]+)\]', content)
        if match_name:
            t_name = match_name.group(1)
        
        # 2. Si no, intentar por coincidencia de patrones (independiente de message_type)
        if not t_name:
            for tp in template_patterns:
                try:
                    if re.match(tp['regex'], content, re.DOTALL | re.IGNORECASE):
                        t_name = tp['name']
                        break
                except: continue
        
        # 3. Si aún no hay nombre pero es tipo template, usar contenido truncado
        if not t_name and msg.message_type == 'template':
            t_name = content[:50] + "..." if len(content) > 50 else content
        
        # Si detectamos que es un template, sumar a stats
        if t_name:
            if t_name not in stats_by_template:
                stats_by_template[t_name] = {'sent': 0, 'read': 0}
            
            stats_by_template[t_name]['sent'] += 1
            is_read = any(s.status == 'read' for s in msg.statuses)
            if is_read:
                stats_by_template[t_name]['read'] += 1

    # Convertir a lista para el template
    template_performance = []
    for name, s in stats_by_template.items():
        read_rate = round((s['read'] / s['sent'] * 100) if s['sent'] > 0 else 0, 1)
        template_performance.append({
            'name': name,
            'sent': s['sent'],
            'read': s['read'],
            'read_rate': read_rate
        })
    
    # Ordenar por más enviados
    template_performance = sorted(template_performance, key=lambda x: x['sent'], reverse=True)[:10]
    
    # ========== MEJORES HORARIOS PARA LECTURA ==========
    # Convertir datos de lectura por hora a un formato más útil
    read_by_hour_dict = {int(h.hour) if h.hour else 0: h.count for h in read_by_hour}
    sent_by_hour_dict = {int(h.hour) if h.hour else 0: h.count for h in sent_by_hour}
    
    # Calcular tasa de lectura por hora
    hourly_read_rate = []
    for hour in range(24):
        sent_at_hour = sent_by_hour_dict.get(hour, 0)
        read_at_hour = read_by_hour_dict.get(hour, 0)
        rate = round((read_at_hour / sent_at_hour * 100) if sent_at_hour > 0 else 0, 1)
        hourly_read_rate.append({
            'hour': hour,
            'sent': sent_at_hour,
            'read': read_at_hour,
            'rate': rate
        })
    
    # Encontrar las mejores horas para enviar (mayor tasa de lectura)
    # Solo considerar horas con al menos 5 mensajes enviados
    best_hours = sorted(
        [h for h in hourly_read_rate if h['sent'] >= 5],
        key=lambda x: x['rate'],
        reverse=True
    )[:3]
    
    # Hora con más lecturas (no tasa, cantidad absoluta)
    peak_read_hour = max(hourly_read_rate, key=lambda x: x['read']) if hourly_read_rate else None
    
    # Insights
    peak_hour = max(sent_by_hour, key=lambda x: x.count) if sent_by_hour else None
    busiest_dow = dow_counts.index(max(dow_counts)) if dow_counts else 0
    days_names = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    
    insights = {
        'peak_hour': int(peak_hour.hour) if peak_hour and peak_hour.hour else 12,
        'peak_hour_count': peak_hour.count if peak_hour else 0,
        'read_rate': round((read / outbound * 100) if outbound > 0 else 0, 1),
        'busiest_day': days_names[busiest_dow],
        'avg_daily': round(total_messages / 30, 1) if total_messages > 0 else 0,
        'best_hours': best_hours,
        'peak_read_hour': peak_read_hour['hour'] if peak_read_hour else 12,
        'template_count': len(template_performance)
    }
    
    return render_template('analytics.html', 
                         stats=stats, 
                         chart_data=chart_data, 
                         insights=insights,
                         template_performance=template_performance,
                         hourly_read_rate=hourly_read_rate)

@app.route("/api/stats")
def api_stats():
    """API endpoint para obtener estadísticas en JSON."""
    twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
    
    total = Message.query.filter(Message.timestamp >= twenty_four_hours_ago).count()
    
    sent = db.session.query(func.count(MessageStatus.id)).filter(
        MessageStatus.status == 'sent',
        MessageStatus.timestamp >= twenty_four_hours_ago
    ).scalar() or 0
    
    delivered = db.session.query(func.count(MessageStatus.id)).filter(
        MessageStatus.status == 'delivered',
        MessageStatus.timestamp >= twenty_four_hours_ago
    ).scalar() or 0
    
    read = db.session.query(func.count(MessageStatus.id)).filter(
        MessageStatus.status == 'read',
        MessageStatus.timestamp >= twenty_four_hours_ago
    ).scalar() or 0
    
    failed = db.session.query(func.count(MessageStatus.id)).filter(
        MessageStatus.status == 'failed',
        MessageStatus.timestamp >= twenty_four_hours_ago
    ).scalar() or 0
    
    total_attempts = sent + delivered + read + failed
    success_rate = round(((delivered + read) / total_attempts * 100) if total_attempts > 0 else 100, 1)
    
    return jsonify({
        'total': total,
        'sent': sent,
        'delivered': delivered,
        'read': read,
        'failed': failed,
        'success_rate': success_rate
    })

def format_utc_iso(dt):
    """Convierte datetime a string ISO 8601 con sufijo Z para UTC."""
    if not dt:
        return None
    if dt.tzinfo is None:
        # Asumir UTC si es naive
        return dt.isoformat() + 'Z'
    # Si tiene zona horaria, convertir a UTC explícitamente
    return dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')

def register_contact_if_new(phone_number, name=None):
    """Registra un contacto si no existe."""
    try:
        if not phone_number or phone_number in ['unknown', 'outbound', '']:
            return
            
        contact = Contact.query.filter_by(phone_number=phone_number).first()
        if not contact:
            new_contact = Contact(phone_number=phone_number, name=name)
            db.session.add(new_contact)
            db.session.commit()
            logger.info(f"🆕 Nuevo contacto registrado: {phone_number}")
        elif name and not contact.name:
            contact.name = name
            db.session.commit()
    except Exception as e:
        logger.error(f"Error registrando contacto auto: {e}")
        db.session.rollback()

# ==========================================
# API CRM CONTACTOS
# ==========================================

@app.route("/api/contacts/<identifier>", methods=["GET", "POST"])
def api_contact_detail(identifier):
    """API para obtener o actualizar un contacto.

    El identificador puede ser:
    - Un ID numérico interno (ej: 123) - solo dígitos cortos
    - Un contact_id externo (ej: CLI-001) - si contiene letras/guiones
    - Un número de teléfono (ej: 5491123456789) - solo dígitos largos

    POST permite cambiar el phone_number y contact_id.
    """
    # Determinar tipo de identificador
    contact = None
    is_internal_id = identifier.isdigit() and len(identifier) <= 10  # IDs internos son cortos
    is_phone = identifier.isdigit() and len(identifier) > 10  # Teléfonos son largos

    if is_internal_id:
        contact = Contact.query.get(int(identifier))
    elif is_phone:
        contact = Contact.query.filter_by(phone_number=identifier).first()
    else:
        # Buscar por contact_id externo
        contact = Contact.query.filter_by(contact_id=identifier).first()

    if request.method == "POST":
        data = request.json
        is_new = False

        if not contact:
            # Crear nuevo contacto (solo si se pasa un teléfono, no un ID)
            if is_internal_id:
                return jsonify({'error': f'Contacto con ID {identifier} no encontrado'}), 404
            if not is_phone:
                return jsonify({'error': f'Contacto con contact_id "{identifier}" no encontrado'}), 404
            contact = Contact(phone_number=identifier)
            db.session.add(contact)
            is_new = True

        # Permitir cambio de contact_id (ID externo editable)
        if 'contact_id' in data:
            new_contact_id = data['contact_id'].strip() if data['contact_id'] else None
            if new_contact_id and new_contact_id != contact.contact_id:
                # Verificar que no exista otro contacto con ese contact_id
                existing = Contact.query.filter_by(contact_id=new_contact_id).first()
                if existing and existing.id != contact.id:
                    return jsonify({
                        'error': f'El ID externo "{new_contact_id}" ya pertenece a otro contacto (ID interno: {existing.id}, Nombre: {existing.name or "Sin nombre"})'
                    }), 400
                contact.contact_id = new_contact_id
                logger.info(f"🆔 Contact ID actualizado para contacto ID {contact.id}: → {new_contact_id}")
            elif not new_contact_id:
                contact.contact_id = None

        # Permitir cambio de teléfono si viene en el payload
            contact.phone_number = new_phone
            logger.info(f"📱 Teléfono actualizado para contacto ID {contact.id}: {identifier} → {new_phone}")

        # Mapeo de campos
        fields = ['name', 'first_name', 'last_name', 'notes',
                  'custom_field_1', 'custom_field_2', 'custom_field_3',
                  'custom_field_4', 'custom_field_5', 'custom_field_6', 'custom_field_7']

        for field in fields:
            if field in data:
                setattr(contact, field, data[field])

        if 'tags' in data:
            new_tag_names = set(data['tags'])
            current_tag_names = {t.name for t in contact.tags}
            # Tags a agregar
            for name in new_tag_names - current_tag_names:
                tag = Tag.query.filter_by(name=name).first()
                if not tag:
                    tag = Tag(name=name)
                    db.session.add(tag)
                    db.session.flush()
                contact.tags.append(tag)
            # Tags a eliminar
            to_remove = current_tag_names - new_tag_names
            contact.tags = [t for t in contact.tags if t.name not in to_remove]

        try:
            db.session.commit()
            action = "creado" if is_new else "actualizado"
            logger.info(f"✅ Contacto {action}: ID={contact.id}, Tel={contact.phone_number}")
            return jsonify({'success': True, 'contact': contact.to_dict()})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    # GET method
    if not contact:
        return jsonify({'found': False, 'details': {'phone_number': identifier if is_phone else None, 'id': int(identifier) if is_internal_id else None}})

    return jsonify({'found': True, 'details': contact.to_dict()})

@app.route("/api/contacts/import", methods=["POST"])

def api_import_contacts():
    """Importar contactos desde Excel/CSV con mapeo estricto y optimización por lotes.

    Prioridad de búsqueda:
    1. Si existe columna ID y tiene valor → buscar por ID (permite cambiar teléfono)
    2. Si no hay ID → buscar por Teléfono (comportamiento tradicional)
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    try:
        # Leer archivo
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)

        # Normalizar columnas (strip solamente, mantener case)
        df.columns = [str(c).strip() for c in df.columns]

        # Identificar columna de ID interno (opcional, para actualizaciones)
        id_cols = ['ID', 'Id', 'id']
        id_col = next((c for c in df.columns if c in id_cols), None)

        # Identificar columna de Contact ID externo (opcional)
        contact_id_cols = ['Contact ID', 'ContactID', 'contact_id', 'ID Externo', 'External ID']
        contact_id_col = next((c for c in df.columns if c in contact_id_cols), None)

        # Identificar columna de teléfono (requerida)
        phone_cols = ['Telefono', 'Teléfono', 'Phone', 'Celular']
        phone_col = next((c for c in df.columns if c in phone_cols), None)

        if not phone_col:
            return jsonify({'error': f'Columna de teléfono no encontrada. Se busca una de: {", ".join(phone_cols)}'}), 400

        col_map = {
            'Nombre completo': 'name',
            'Nombre': 'first_name',
            'Apellido': 'last_name',
            'Notas': 'notes',
            'Campo 1': 'custom_field_1',
            'Campo 2': 'custom_field_2',
            'Campo 3': 'custom_field_3',
            'Campo 4': 'custom_field_4',
            'Campo 5': 'custom_field_5',
            'Campo 6': 'custom_field_6',
            'Campo 7': 'custom_field_7'
        }

        # Pre-calcular tag de importación
        import_tag = None
        import_tag_name = request.form.get('assign_tag', '').strip()
        if import_tag_name:
            import_tag = Tag.query.filter_by(name=import_tag_name).first()
            if not import_tag:
                import_tag = Tag(name=import_tag_name)
                db.session.add(import_tag)
                db.session.flush()

        # =====================================================
        # OPTIMIZACIÓN POR LOTES (BATCH PROCESSING)
        # =====================================================
        
        # 1. Recolectar todos los identificadores del archivo para hacer un solo query
        all_contact_ids = set()
        all_phones = set()
        all_internal_ids = set()
        
        # Normalizar datos en el dataframe para facilitar procesamiento
        # Convertir a string y limpiar
        df['clean_phone'] = df[phone_col].apply(lambda x: str(x).replace('.0', '').strip() if pd.notna(x) else '')
        
        if contact_id_col:
            df['clean_contact_id'] = df[contact_id_col].apply(lambda x: str(x).strip() if pd.notna(x) else None)
            all_contact_ids = set(df['clean_contact_id'].dropna().unique())
            # Eliminar strings vacíos
            all_contact_ids = {cid for cid in all_contact_ids if cid}
            
        if id_col:
            # IDs internos suelen ser enteros
            def clean_id(x):
                try: 
                    return int(float(x)) 
                except: 
                    return None
            df['clean_internal_id'] = df[id_col].apply(clean_id)
            all_internal_ids = set(df['clean_internal_id'].dropna().unique())

        all_phones = set(df['clean_phone'].dropna().unique())
        all_phones = {p for p in all_phones if p} # Eliminar vacíos
        
        # 2. Pre-cargar contactos existentes de la base de datos
        existing_contacts_by_cid = {}
        existing_contacts_by_phone = {}
        existing_contacts_by_iid = {}
        
        # Buscar por Contact ID
        if all_contact_ids:
            results_cid = Contact.query.filter(Contact.contact_id.in_(all_contact_ids)).all()
            for c in results_cid:
                existing_contacts_by_cid[c.contact_id] = c
                existing_contacts_by_phone[c.phone_number] = c # También indexar por tel para evitar dups
                existing_contacts_by_iid[c.id] = c

        # Buscar por Phone (que no hayamos traído ya)
        phones_to_fetch = all_phones - set(existing_contacts_by_phone.keys())
        if phones_to_fetch:
            # Optimización: Consultar en chunks si son muchísimos (>1000)
            # SQLAlchemy maneja bien IN clauses grandes pero postgres tiene límites de parámetros (~65k)
            # Para 3000 filas es seguro hacerlo de una vez
            results_phone = Contact.query.filter(Contact.phone_number.in_(phones_to_fetch)).all()
            for c in results_phone:
                existing_contacts_by_phone[c.phone_number] = c
                if c.contact_id: existing_contacts_by_cid[c.contact_id] = c
                existing_contacts_by_iid[c.id] = c
                
        # Buscar por Internal ID (fallback)
        ids_to_fetch = all_internal_ids - set(existing_contacts_by_iid.keys())
        if ids_to_fetch:
            results_iid = Contact.query.filter(Contact.id.in_(ids_to_fetch)).all()
            for c in results_iid:
                existing_contacts_by_iid[c.id] = c
                existing_contacts_by_phone[c.phone_number] = c
                if c.contact_id: existing_contacts_by_cid[c.contact_id] = c

        count = 0
        updated = 0
        phone_updated = 0
        errors = []
        
        # 3. Procesar filas en memoria
        for idx, row in df.iterrows():
            phone = row['clean_phone']
            if not phone:
                continue

            contact = None
            found_by = None
            
            # A. Buscar en memoria
            # 1. Contact ID
            ext_id = row.get('clean_contact_id') if contact_id_col else None
            if ext_id and ext_id in existing_contacts_by_cid:
                contact = existing_contacts_by_cid[ext_id]
                found_by = 'contact_id'
            
            # 2. Internal ID
            int_id = row.get('clean_internal_id') if id_col else None
            if not contact and int_id and int_id in existing_contacts_by_iid:
                contact = existing_contacts_by_iid[int_id]
                found_by = 'id'
                
            # 3. Phone
            if not contact and phone in existing_contacts_by_phone:
                contact = existing_contacts_by_phone[phone]
                found_by = 'phone'
            
            is_new = False
            
            if not contact:
                # CREACIÓN
                
                # Validar Client ID obligatorio
                if not ext_id: # ext_id ya está limpio y verificado
                    errors.append(f"Fila {idx+2}: Ignorado - Se requiere Client ID (contact_id) para crear nuevos contactos")
                    continue
                
                # Crear nuevo
                contact = Contact(phone_number=phone)
                contact.contact_id = ext_id
                
                db.session.add(contact)
                
                # Actualizar índices en memoria para futuras filas en este mismo loop (por si hay reps)
                existing_contacts_by_cid[ext_id] = contact
                existing_contacts_by_phone[phone] = contact
                
                is_new = True
                count += 1
            else:
                # ACTUALIZACIÓN
                if found_by in ('contact_id', 'id') and contact.phone_number != phone:
                    old_phone = contact.phone_number
                    # Actualizar índice en memoria: quitar el viejo teléfono
                    if old_phone in existing_contacts_by_phone:
                        # Solo si apunta a este contacto (cuidado con colisiones)
                        if existing_contacts_by_phone[old_phone] == contact:
                            del existing_contacts_by_phone[old_phone]
                            
                    contact.phone_number = phone
                    # Actualizar índice con nuevo teléfono
                    existing_contacts_by_phone[phone] = contact
                    
                    phone_updated += 1
                    # logger.info(...) # Evitar exceso de logs en loop
                updated += 1

            # Actualizar campos mapeados
            for excel_col, model_attr in col_map.items():
                if excel_col in df.columns:
                    val = row[excel_col]
                    if pd.notna(val):
                        setattr(contact, model_attr, str(val))

            # Actualizar Contact ID si fue encontrado por teléfono y el archivo tiene uno nuevo
            if found_by in ('phone', 'id') and ext_id:
                if ext_id != contact.contact_id:
                    # Verificar unicidad (en los ya cargados o en DB)
                    # Si ya existe otro contacto con ese ID en memoria...
                    if ext_id in existing_contacts_by_cid and existing_contacts_by_cid[ext_id] != contact:
                         errors.append(f"Fila {idx+2}: El Contact ID '{ext_id}' ya existe en otro contacto")
                    else:
                        contact.contact_id = ext_id
                        existing_contacts_by_cid[ext_id] = contact # Actualizar índice

            # Asignar tag
            if import_tag:
                # Verificar si ya tiene el tag. 
                # Nota: acceder a contact.tags dispara query si no está cargado.
                # Para optimización extrema se podría hacer eager loading al principio join tags.
                # Al ser lazy='select', esto hará N queries si son updates. 
                # Pero como SQLAlchemy tiene identity map, si ya cargamos tags quizas reusa.
                # Una optimización simple: si es nuevo, append directo.
                if is_new:
                    contact.tags.append(import_tag)
                else:
                    if import_tag not in contact.tags:
                        contact.tags.append(import_tag)

        # 4. Commit masivo
        db.session.commit()

        message = f'Procesados {count + updated} contactos ({count} nuevos, {updated} actualizados)'
        if phone_updated > 0:
            message += f', {phone_updated} teléfonos actualizados'

        result = {'success': True, 'message': message}
        if errors:
            result['warnings'] = errors[:100] # Limitar warnings para no saturar respuesta

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error importando contactos: {e}")
        return jsonify({'error': f"Error procesando archivo: {str(e)}"}), 500

@app.route("/api/contacts/export", methods=["GET"])
def api_export_contacts():
    """Exportar contactos a Excel.

    Incluye columna ID y Contact ID para permitir reimportar y actualizar.
    """
    try:
        contacts = Contact.query.all()
        data = []
        for c in contacts:
            data.append({
                'ID': c.id,  # ID interno (no editable)
                'Contact ID': c.contact_id,  # ID externo editable
                'Telefono': c.phone_number,
                'Nombre completo': c.name,
                'Nombre': c.first_name,
                'Apellido': c.last_name,
                'Campo 1': c.custom_field_1,
                'Campo 2': c.custom_field_2,
                'Campo 3': c.custom_field_3,
                'Campo 4': c.custom_field_4,
                'Campo 5': c.custom_field_5,
                'Campo 6': c.custom_field_6,
                'Campo 7': c.custom_field_7,
                'Notas': c.notes,
                'Etiquetas': ', '.join(t.name for t in c.tags) if c.tags else '',
                'Fecha Creacion': c.created_at
            })
            
        df = pd.DataFrame(data)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Contactos')
            
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'contactos_crm_{datetime.now().strftime("%Y%m%d")}.xlsx'
        )
        
    except Exception as e:
        logger.error(f"Error exportando contactos: {e}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/contacts/template", methods=["GET"])
def api_contacts_template():
    """Descargar plantilla Excel para importar contactos."""
    try:
        # Crear datos de ejemplo - Contact ID es el identificador principal
        example_data = [
            {
                'Contact ID': 'CLI-001',
                'Telefono': '5491123456789',
                'Nombre': 'Juan',
                'Apellido': 'Perez',
                'Nombre completo': 'Juan Perez',
                'Etiquetas': 'cliente, vip',
                'Notas': 'Cliente desde 2024',
                'Campo 1': 'Valor personalizado 1',
                'Campo 2': 'Valor personalizado 2',
                'Campo 3': '',
                'Campo 4': '',
                'Campo 5': '',
                'Campo 6': '',
                'Campo 7': ''
            },
            {
                'Contact ID': 'CLI-002',
                'Telefono': '5491198765432',
                'Nombre': 'Maria',
                'Apellido': 'Garcia',
                'Nombre completo': 'Maria Garcia',
                'Etiquetas': 'prospecto',
                'Notas': 'Interesada en servicios',
                'Campo 1': '',
                'Campo 2': '',
                'Campo 3': '',
                'Campo 4': '',
                'Campo 5': '',
                'Campo 6': '',
                'Campo 7': ''
            }
        ]

        df = pd.DataFrame(example_data)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Contactos')

            # Agregar hoja de instrucciones
            instructions = pd.DataFrame({
                'Instrucciones': [
                    'PLANTILLA PARA IMPORTAR CONTACTOS',
                    '',
                    '============================================',
                    'IDENTIFICADOR PRINCIPAL: Contact ID',
                    '============================================',
                    '',
                    '- Contact ID es TU identificador para cada contacto',
                    '- Usa codigos de tu sistema: legajo, DNI, expediente, etc.',
                    '- Al importar, el sistema busca por Contact ID',
                    '- Si existe, actualiza el contacto (incluyendo telefono)',
                    '- Si no existe, crea uno nuevo',
                    '',
                    'COLUMNAS:',
                    '',
                    '- Contact ID: Tu identificador unico (legajo, DNI, codigo cliente)',
                    '- Telefono (REQUERIDO): Con codigo de pais, sin + ni espacios',
                    '  Ejemplo: 5491123456789',
                    '- Nombre, Apellido: Datos del contacto',
                    '- Etiquetas: Separadas por coma. Ej: cliente, vip',
                    '- Notas: Notas adicionales',
                    '- Campo 1-7: Campos personalizados',
                    '',
                    'COMO ACTUALIZAR CONTACTOS:',
                    '1. Exporta tus contactos actuales',
                    '2. Modifica lo que necesites (telefono, nombre, etc)',
                    '3. Mantene el Contact ID igual (es la clave de busqueda)',
                    '4. Reimporta el archivo',
                    '5. El sistema actualizara los telefonos manteniendo etiquetas y datos',
                    '',
                    'IMPORTANTE:',
                    '- Solo la columna Telefono es obligatoria',
                    '- El numero debe incluir codigo de pais (54 para Argentina)',
                    '- NO uses el simbolo + al inicio',
                    '- NO uses espacios, guiones ni parentesis',
                    '- Las etiquetas se crean automaticamente si no existen'
                ]
            })
            instructions.to_excel(writer, index=False, sheet_name='Instrucciones')

        output.seek(0)

        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='plantilla_contactos.xlsx'
        )

    except Exception as e:
        logger.error(f"Error generando plantilla: {e}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/messages/<phone>")
def api_get_messages(phone):
    """API para obtener mensajes de un contacto (optimizado para AJAX)."""
    try:
        # Límite de mensajes
        MESSAGE_LIMIT = 100
        
        # Obtener mensajes recientes
        recent_messages = Message.query.filter_by(phone_number=phone)\
            .order_by(Message.timestamp.desc())\
            .limit(MESSAGE_LIMIT).all()
        
        # Reordenar cronológicamente
        messages = sorted(recent_messages, key=lambda m: m.timestamp)
        
        # Obtener info de contacto
        contact = Contact.query.filter_by(phone_number=phone).first()
        contact_dict = contact.to_dict() if contact else None
        
        # Calcular stats básicos
        outbound_msgs = [m for m in messages if m.direction == 'outbound']
        stats = {
            'sent': sum(1 for m in outbound_msgs if m.latest_status in ['sent', 'delivered', 'read']),
            'delivered': sum(1 for m in outbound_msgs if m.latest_status in ['delivered', 'read']),
            'read': sum(1 for m in outbound_msgs if m.latest_status == 'read')
        }
        
        # Verificar ventana de 24hs
        can_send_free_text = False
        last_inbound_msg = None
        
        whatsapp_configured = whatsapp_api.is_configured()
        if whatsapp_configured:
            twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
            # Solo buscamos en lo que ya trajimos para ser rápidos, 
            # o hacemos query específica si no hay inbound recientes en los últimos 100
            
            # Buscar en los mensajes cargados primero
            inbound_loaded = [m for m in messages if m.direction == 'inbound']
            if inbound_loaded:
                last_msg = inbound_loaded[-1] # El más reciente de los cargados
                if last_msg.timestamp >= twenty_four_hours_ago:
                    can_send_free_text = True
                    last_inbound_msg = last_msg.timestamp
            
            # Si no encontramos en los últimos 100, quizás hay uno anterior pero dentro de 24h
            if not can_send_free_text:
                # Query específica rápida
                last_inbound = Message.query.filter_by(
                    phone_number=phone,
                    direction='inbound'
                ).filter(Message.timestamp >= twenty_four_hours_ago).order_by(Message.timestamp.desc()).first()
                
                if last_inbound:
                    can_send_free_text = True
                    last_inbound_msg = last_inbound.timestamp

        # Serializar mensajes
        messages_data = []
        for m in messages:
            # Convertir a hora argentina
            dt_arg = to_argentina_filter(m.timestamp)
            time_str = dt_arg.strftime('%H:%M') if dt_arg else ''
            date_str = dt_arg.strftime('%d/%m/%Y') if dt_arg else ''
            
            messages_data.append({
                'id': m.id,
                'content': m.content,
                'direction': m.direction,
                'time': time_str,
                'date': date_str,
                'status': m.latest_status,
                'message_type': m.message_type,
                'media_url': m.media_url,
                'caption': m.caption
            })

        return jsonify({
            'success': True,
            'contact': contact_dict,
            'messages': messages_data,
            'stats': stats,
            'can_send_free_text': can_send_free_text,
            'whatsapp_configured': whatsapp_configured
        })
        
    except Exception as e:
        logger.error(f"Error fetching messages API: {e}")
        return jsonify({'error': str(e)}), 500

@app.route("/contacts")
def contacts_page():
    """Página para ver listado de contactos con paginación y búsqueda."""
    tag_filter = request.args.get('tag')
    search_query = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    # Base query
    query = Contact.query

    # Apply tag filter
    if tag_filter:
        query = query.filter(Contact.tags.any(Tag.name == tag_filter))

    # Apply search filter
    if search_query:
        search_pattern = f"%{search_query}%"
        query = query.filter(
            or_(
                Contact.name.ilike(search_pattern),
                Contact.phone_number.ilike(search_pattern),
                Contact.contact_id.ilike(search_pattern)
            )
        )

    # Order and paginate
    query = query.order_by(Contact.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        'contacts.html',
        contacts=pagination.items,
        pagination=pagination,
        tag_filter=tag_filter,
        search_query=search_query
    )

@app.route("/tags")
def tags_page():
    """Página para ver etiquetas y estadísticas."""
    tags_with_count = db.session.query(
        Tag,
        func.count(contact_tags.c.contact_id).label('cnt')
    ).outerjoin(
        contact_tags, Tag.id == contact_tags.c.tag_id
    ).group_by(Tag.id).order_by(func.count(contact_tags.c.contact_id).desc()).all()

    tags_list = [(tag.name, cnt) for tag, cnt in tags_with_count]
    total_contacts = Contact.query.count()
    return render_template('tags.html', tags=tags_list, total_contacts=total_contacts)

@app.route("/api/tags", methods=["GET"])
def api_list_tags():
    """Lista todas las etiquetas con conteo de contactos."""
    tags_with_count = db.session.query(
        Tag,
        func.count(contact_tags.c.contact_id).label('cnt')
    ).outerjoin(
        contact_tags, Tag.id == contact_tags.c.tag_id
    ).group_by(Tag.id).order_by(func.count(contact_tags.c.contact_id).desc()).all()

    return jsonify([{'name': tag.name, 'count': cnt} for tag, cnt in tags_with_count])

@app.route("/api/tags", methods=["POST"])
def api_create_tag():
    """Crea una nueva etiqueta."""
    data = request.json
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Nombre requerido'}), 400

    if Tag.query.filter_by(name=name).first():
        return jsonify({'error': 'Etiqueta ya existe'}), 409

    tag = Tag(name=name)
    db.session.add(tag)
    db.session.commit()
    return jsonify({'success': True, 'name': name}), 201

@app.route("/api/tags/<tag_name>", methods=["DELETE"])
def api_delete_tag(tag_name):
    """Elimina una etiqueta y todas sus referencias."""
    try:
        tag = Tag.query.filter_by(name=tag_name).first()
        if not tag:
            return jsonify({'error': 'Tag no encontrado'}), 404
        db.session.execute(contact_tags.delete().where(contact_tags.c.tag_id == tag.id))
        db.session.delete(tag)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error eliminando tag '{tag_name}': {e}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/contacts/bulk-tags", methods=["POST"])
def api_bulk_tags():
    """Asignar o remover tags de múltiples contactos.

    Acepta contact_ids (preferido) o phones (legacy) para identificar contactos.
    """
    data = request.json
    contact_ids = data.get('contact_ids', [])
    phones = data.get('phones', [])  # Legacy support
    tag_name = (data.get('tag') or '').strip()
    action = data.get('action')  # 'add' or 'remove'

    if (not contact_ids and not phones) or not tag_name or action not in ('add', 'remove'):
        return jsonify({'error': 'contact_ids (o phones), tag y action (add/remove) requeridos'}), 400

    try:
        # Preferir IDs sobre phones
        if contact_ids:
            contacts = Contact.query.filter(Contact.id.in_(contact_ids)).all()
        else:
            contacts = Contact.query.filter(Contact.phone_number.in_(phones)).all()

        if action == 'add':
            tag = Tag.query.filter_by(name=tag_name).first()
            if not tag:
                tag = Tag(name=tag_name)
                db.session.add(tag)
                db.session.flush()
            for contact in contacts:
                if tag not in contact.tags:
                    contact.tags.append(tag)
        elif action == 'remove':
            tag = Tag.query.filter_by(name=tag_name).first()
            if tag:
                for contact in contacts:
                    contact.tags = [t for t in contact.tags if t.id != tag.id]

        db.session.commit()
        return jsonify({'success': True, 'affected': len(contacts)})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route("/api/tags/bulk-action", methods=["POST"])
def api_tags_bulk_action():
    """Agregar o quitar etiqueta de múltiples contactos via archivo Excel/CSV con optimización por lotes."""
    tag_name = request.form.get('tag_name', '').strip()
    action = request.form.get('action', '').strip()

    if not tag_name or action not in ('add', 'remove'):
        return jsonify({'error': 'tag_name y action (add/remove) requeridos'}), 400

    if 'file' not in request.files or request.files['file'].filename == '':
        return jsonify({'error': 'Archivo requerido'}), 400

    file = request.files['file']
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)

        # Normalizar columnas
        df.columns = [str(c).lower().strip() for c in df.columns]

        # Buscar columna de Contact ID (PRIORIDAD)
        contact_id_candidates = ['contact id', 'contact_id', 'contactid', 'id externo', 'external_id']
        contact_id_col = next((c for c in df.columns if c in contact_id_candidates), None)

        # Buscar columna de teléfono (fallback)
        phone_candidates = ['telefono', 'phone', 'phone_number', 'numero', 'celular']
        phone_col = next((c for c in df.columns if c in phone_candidates), None)

        if not contact_id_col and not phone_col:
            return jsonify({'error': 'Se requiere columna "Contact ID" o "Telefono"'}), 400

        # Obtener o crear tag
        tag = Tag.query.filter_by(name=tag_name).first()
        if not tag:
            if action == 'remove':
                return jsonify({'success': True, 'added': 0, 'removed': 0, 'skipped': 0})
            tag = Tag(name=tag_name)
            db.session.add(tag)
            db.session.flush()

        # =====================================================
        # OPTIMIZACIÓN POR LOTES
        # =====================================================

        # 1. Recolectar identificadores
        all_contact_ids = set()
        all_phones = set()

        # Limpiar datos
        if contact_id_col:
            df['clean_contact_id'] = df[contact_id_col].apply(lambda x: str(x).strip() if pd.notna(x) else None)
            all_contact_ids = {cid for cid in df['clean_contact_id'].dropna().unique() if cid}

        if phone_col:
            df['clean_phone'] = df[phone_col].apply(lambda x: str(x).replace('.0', '').strip() if pd.notna(x) else '')
            all_phones = {p for p in df['clean_phone'].dropna().unique() if p}

        # 2. Batch Fetch de contactos existentes
        existing_contacts_by_cid = {}
        existing_contacts_by_phone = {}

        # Fetch por Contact ID
        if all_contact_ids:
            results_cid = Contact.query.options(joinedload(Contact.tags)).filter(Contact.contact_id.in_(all_contact_ids)).all()
            for c in results_cid:
                existing_contacts_by_cid[c.contact_id] = c
                existing_contacts_by_phone[c.phone_number] = c  # Indexar también por teléfono

        # Fetch por Phone (evitando duplicados)
        phones_to_fetch = all_phones - set(existing_contacts_by_phone.keys())
        if phones_to_fetch:
             results_phone = Contact.query.options(joinedload(Contact.tags)).filter(Contact.phone_number.in_(phones_to_fetch)).all()
             for c in results_phone:
                 existing_contacts_by_phone[c.phone_number] = c
                 if c.contact_id:
                     existing_contacts_by_cid[c.contact_id] = c

        added = 0
        removed = 0
        skipped = 0
        not_found = 0

        # 3. Procesar en memoria
        for _, row in df.iterrows():
            contact = None

            # Buscar
            if contact_id_col:
                ext_id = row.get('clean_contact_id')
                if ext_id and ext_id in existing_contacts_by_cid:
                    contact = existing_contacts_by_cid[ext_id]
            
            if not contact and phone_col:
                phone = row.get('clean_phone')
                if phone and phone in existing_contacts_by_phone:
                    contact = existing_contacts_by_phone[phone]

            if not contact:
                not_found += 1
                continue

            # Nota: Acceder a contact.tags puede disparar lazy loads si no están cargados.
            # Sin embargo, Identity Map de SQLAlchemy ayuda.
            # Para optimización máxima, se debería cargar con joinedload, pero batch fetch es el mayor paso.
            
            if action == 'add':
                if tag not in contact.tags:
                    contact.tags.append(tag)
                    added += 1
                else:
                    skipped += 1
            elif action == 'remove':
                if tag in contact.tags:
                    # Remover tag de la lista
                    contact.tags = [t for t in contact.tags if t.id != tag.id]
                    removed += 1
                else:
                    skipped += 1

        db.session.commit()
        
        return jsonify({
            'success': True,
            'added': added,
            'removed': removed,
            'skipped': skipped,
            'not_found': not_found
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error en bulk tag action: {e}")
        return jsonify({'error': str(e)}), 500

@app.route("/failed-messages")
def failed_messages_page():
    """Página para ver mensajes fallidos."""
    # Buscar mensajes con estado 'failed' en su último status
    # Hacemos un join con MessageStatus
    
    # Subquery para obtener el último status de cada mensaje
    last_status_subquery = db.session.query(
        MessageStatus.wa_message_id,
        func.max(MessageStatus.timestamp).label('max_timestamp')
    ).group_by(MessageStatus.wa_message_id).subquery()
    
    failed_msgs = db.session.query(Message, MessageStatus).join(
        MessageStatus, Message.wa_message_id == MessageStatus.wa_message_id
    ).join(
        last_status_subquery, 
        (MessageStatus.wa_message_id == last_status_subquery.c.wa_message_id) & 
        (MessageStatus.timestamp == last_status_subquery.c.max_timestamp)
    ).filter(
        MessageStatus.status == 'failed'
    ).order_by(Message.timestamp.desc()).all()
    
    # Batch load contactos para evitar N+1 queries
    phones = list({msg.phone_number for msg, _ in failed_msgs})
    contacts_map = {}
    if phones:
        contacts_map = {c.phone_number: c for c in Contact.query.filter(Contact.phone_number.in_(phones)).all()}

    enriched_failures = []
    for msg, status in failed_msgs:
        contact = contacts_map.get(msg.phone_number)
        enriched_failures.append({
            'message': msg,
            'status': status,
            'contact_name': contact.name if contact else None
        })
        
    return render_template('failed_messages.html', failures=enriched_failures)

@app.route("/chatwoot-webhook", methods=["POST"])
def chatwoot_webhook():
    """
    Endpoint para recibir webhooks de Chatwoot.
    Captura mensajes salientes enviados por agentes.
    """
    try:
        data = request.json
        if not data:
            return "No data received", 400
        
        event = data.get("event")
        logger.info(f"📬 CHATWOOT WEBHOOK: {event}")
        
        # Manejar mensaje creado o actualizado
        if event in ["message_created", "message_updated"]:
            # En Chatwoot, el contenido viene en el nivel raíz
            content = data.get("content", "")
            conversation = data.get("conversation", {})
            
            # Obtener el message_type desde messages[0] dentro de conversation
            messages = conversation.get("messages", [])
            message_type_cw = None
            source_id = None
            cw_msg_id = None
            
            if messages:
                first_msg = messages[0]
                message_type_cw = first_msg.get("message_type")
                source_id = first_msg.get("source_id")  # wa_message_id de WhatsApp
                cw_msg_id = first_msg.get("id")  # ID interno de Chatwoot
            
            # Obtener el número de teléfono desde contact_inbox
            contact_inbox = conversation.get("contact_inbox", {})
            phone_number = contact_inbox.get("source_id", "").replace("+", "")
            
            logger.info(f"📝 message_type: {message_type_cw}, cw_id: {cw_msg_id}, source_id: {source_id}")
            
            # Solo mensajes salientes (message_type=1 en Chatwoot)
            if message_type_cw == 1 and content and cw_msg_id:
                logger.info(f"📤 MENSAJE SALIENTE: '{content[:50]}...' para {phone_number}")
                
                # Buscar primero por source_id (wa_message_id) si existe
                existing = None
                if source_id:
                    existing = Message.query.filter_by(wa_message_id=source_id).first()
                
                # Si no existe por source_id, buscar por cw_id
                cw_id_str = f"cw_{cw_msg_id}"
                if not existing:
                    existing = Message.query.filter_by(wa_message_id=cw_id_str).first()
                
                if existing:
                    # Actualizar mensaje existente
                    updated = False
                    if not existing.content and content:
                        existing.content = content
                        updated = True
                    if phone_number and existing.phone_number in ["outbound", "unknown"]:
                        existing.phone_number = phone_number
                        updated = True
                    # Si tenemos source_id y el mensaje tenía cw_id, actualizar al wa_message_id real
                    if source_id and existing.wa_message_id.startswith("cw_"):
                        existing.wa_message_id = source_id
                        updated = True
                    if updated:
                        db.session.commit()
                        logger.info(f"✅ Mensaje actualizado: {existing.wa_message_id}")
                else:
                    # Crear nuevo mensaje
                    # Usar source_id si está disponible, sino usar cw_id
                    msg_id = source_id if source_id else cw_id_str
                    
                    # Intentar detectar si el contenido es un template
                    detected_type = "text"
                    final_content = content
                    
                    try:
                        templates_result = whatsapp_api.get_templates()
                        for t in templates_result.get("templates", []):
                            if t.get("status") == "APPROVED":
                                for comp in t.get("components", []):
                                    if comp.get("type") == "BODY":
                                        template_body = comp.get("text", "")
                                        # Limpieza básica para comparación (quitar variables {{1}}, etc)
                                        import re
                                        pattern = re.escape(template_body)
                                        pattern = re.sub(r'\\\{\\\{\d+\\\}\\\}', '.*', pattern)
                                        
                                        if re.match(f"^{pattern}$", content, re.DOTALL):
                                            detected_type = "template"
                                            # Opcional: podríamos normalizar el contenido al template original
                                            # pero mejor dejar el texto real enviado.
                                            break
                                if detected_type == "template": break
                    except Exception as te:
                        logger.error(f"Error detecting template in webhook: {te}")

                    new_msg = Message(
                        wa_message_id=msg_id,
                        phone_number=phone_number or "unknown",
                        direction="outbound",
                        message_type=detected_type,
                        content=final_content,
                        timestamp=datetime.utcnow()
                    )
                    db.session.add(new_msg)
                    db.session.commit()
                    logger.info(f"✅ Mensaje saliente creado ({detected_type}): {msg_id}")
        
        return "OK", 200
        
    except Exception as e:
        logger.error(f"Error en chatwoot webhook: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return "Internal Server Error", 500

# ==================== WhatsApp Settings ====================

@app.route("/whatsapp-settings")
def whatsapp_settings():
    """Página de configuración y templates de WhatsApp."""
    is_configured = whatsapp_api.is_configured()
    
    templates = []
    phone_numbers = []
    profile = {}
    error = None
    
    if is_configured:
        # Obtener templates
        templates_result = whatsapp_api.get_templates()
        if "error" in templates_result:
            error = templates_result["error"]
        templates = templates_result.get("templates", [])
        
        # Obtener números
        numbers_result = whatsapp_api.get_phone_numbers()
        phone_numbers = numbers_result.get("phone_numbers", [])
        
        # Obtener perfil
        profile_result = whatsapp_api.get_business_profile()
        profile = profile_result.get("profile", {})
    
    return render_template('whatsapp_settings.html',
                         is_configured=is_configured,
                         templates=templates,
                         phone_numbers=phone_numbers,
                         profile=profile,
                         error=error)

@app.route("/templates/new")
def create_template_page():
    """Página dedicada para crear nuevas plantillas de WhatsApp con vista previa en vivo."""
    return render_template('create_template.html')

@app.route("/api/whatsapp/templates")
def api_whatsapp_templates():
    """API para obtener templates."""
    return jsonify(whatsapp_api.get_templates())

@app.route("/api/whatsapp/phone-numbers")
def api_whatsapp_phone_numbers():
    """API para obtener números de teléfono."""
    return jsonify(whatsapp_api.get_phone_numbers())

@app.route("/api/whatsapp/profile")
def api_whatsapp_profile():
    """API para obtener perfil del negocio."""
    return jsonify(whatsapp_api.get_business_profile())

@app.route("/api/whatsapp/create-template", methods=["POST"])
def api_create_template():
    """API para crear una nueva plantilla de mensaje."""
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    name = data.get("name", "").strip().lower().replace(" ", "_")
    category = data.get("category")
    language = data.get("language", "es_AR")

    if not name or not category:
        return jsonify({"error": "name y category son requeridos"}), 400

    if category not in ["MARKETING", "UTILITY", "AUTHENTICATION"]:
        return jsonify({"error": "category debe ser MARKETING, UTILITY o AUTHENTICATION"}), 400

    # Construir componentes
    components = []

    # Header (opcional)
    header = data.get("header")
    if header and header.get("format"):
        header_component = {"type": "HEADER", "format": header["format"]}
        if header["format"] == "TEXT" and header.get("text"):
            header_component["text"] = header["text"]
        components.append(header_component)

    # Body (requerido)
    body_text = data.get("body", "").strip()
    if not body_text:
        return jsonify({"error": "body es requerido"}), 400
    components.append({"type": "BODY", "text": body_text})

    # Footer (opcional)
    footer_text = data.get("footer", "").strip()
    if footer_text:
        components.append({"type": "FOOTER", "text": footer_text})

    # Buttons (opcional)
    buttons = data.get("buttons", [])
    if buttons:
        button_components = []
        for btn in buttons:
            if btn.get("type") == "QUICK_REPLY" and btn.get("text"):
                button_components.append({"type": "QUICK_REPLY", "text": btn["text"]})
            elif btn.get("type") == "URL" and btn.get("text") and btn.get("url"):
                button_components.append({"type": "URL", "text": btn["text"], "url": btn["url"]})
            elif btn.get("type") == "PHONE_NUMBER" and btn.get("text") and btn.get("phone_number"):
                button_components.append({"type": "PHONE_NUMBER", "text": btn["text"], "phone_number": btn["phone_number"]})
        if button_components:
            components.append({"type": "BUTTONS", "buttons": button_components})

    result = whatsapp_api.create_template(name, category, language, components)

    if result.get("error"):
        return jsonify(result), 400
    return jsonify(result)

@app.route("/api/whatsapp/send-template", methods=["POST"])
def api_send_template():
    """API para enviar mensaje con template y variables dinámicas."""
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    to_phone = data.get("to")
    template_name = data.get("template_name")
    language = data.get("language", "es_AR")
    # variable_mapping es una lista de nombres de campos del contacto, ej: ['first_name', 'custom_field_1']
    variable_mapping = data.get("variable_mapping", []) 
    
    if not to_phone or not template_name:
        return jsonify({"error": "to y template_name son requeridos"}), 400
    
    # Construir componentes si hay mapeo de variables
    components = data.get("components") # Permitir componentes manuales si se envían
    
    if variable_mapping and not components:
        contact = Contact.query.filter_by(phone_number=to_phone).first()
        parameters = []
        
        for field in variable_mapping:
            value = "-" # Fallback para evitar errores de API
            
            # Valores especiales
            if field == 'phone_number':
                value = to_phone
            elif contact:
                # Obtener valor del atributo del contacto
                val = getattr(contact, field, None)
                if val:
                    value = str(val)
            
            parameters.append({
                "type": "text",
                "text": value
            })
            
        if parameters:
            components = [{
                "type": "body",
                "parameters": parameters
            }]
    
    # Obtener el contenido del template para guardarlo en el historial
    # Esto es una aproximación, ya que no tenemos el texto final renderizado por WhatsApp
    template_content = f"[Template: {template_name}]"
    templates_result = whatsapp_api.get_templates()
    for t in templates_result.get("templates", []):
        if t.get("name") == template_name and t.get("language") == language:
            for comp in t.get("components", []):
                if comp.get("type") == "BODY":
                    text = comp.get("text", "")
                    # Intentar rellenar variables para el historial local
                    if variable_mapping and contact:
                        for i, field in enumerate(variable_mapping):
                            val = getattr(contact, field, "") or "-"
                            text = text.replace(f"{{{{{i+1}}}}}", str(val))
                    template_content = text
                    break
            break
            
    # Fallback si por alguna razón el contenido está vacío
    if not template_content:
        template_content = f"[Template: {template_name}]"
    
    result = whatsapp_api.send_template_message(to_phone, template_name, language, components)
    
    if result.get("success"):
        wa_id = result.get("message_id")
        if wa_id:
            # Verificar si ya existe (creado por save_status en event_handlers.py por ejemplo)
            existing = Message.query.filter_by(wa_message_id=wa_id).first()
            if existing:
                existing.content = template_content
                existing.message_type = "template"
                existing.phone_number = to_phone
                logger.info(f"✅ Mensaje existente actualizado con contenido del template: {wa_id}")
            else:
                new_msg = Message(
                    wa_message_id=wa_id,
                    phone_number=to_phone,
                    direction="outbound",
                    message_type="template",
                    content=template_content,
                    timestamp=datetime.utcnow()
                )
                db.session.add(new_msg)
            
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error al guardar mensaje en BD: {e}")
    
    return jsonify(result)

@app.route("/api/whatsapp/send-text", methods=["POST"])
def api_send_text():
    """API para enviar mensaje de texto."""
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    to_phone = data.get("to")
    text = data.get("text")
    
    if not to_phone or not text:
        return jsonify({"error": "to y text son requeridos"}), 400
    
    result = whatsapp_api.send_text_message(to_phone, text)
    
    if result.get("success"):
        wa_id = result.get("message_id")
        if wa_id:
            # Verificar si ya existe (creado por save_status en event_handlers.py por ejemplo)
            existing = Message.query.filter_by(wa_message_id=wa_id).first()
            if existing:
                existing.content = text
                existing.phone_number = to_phone
                logger.info(f"✅ Mensaje existente actualizado con texto: {wa_id}")
            else:
                new_msg = Message(
                    wa_message_id=wa_id,
                    phone_number=to_phone,
                    direction="outbound",
                    message_type="text",
                    content=text,
                    timestamp=datetime.utcnow()
                )
                db.session.add(new_msg)
            
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error al guardar mensaje en BD: {e}")
    
    return jsonify(result)

# ==================== CAMPAÑAS ====================

@app.route("/campaigns")
def campaigns_page():
    """Página de campañas."""
    campaigns = Campaign.query.order_by(Campaign.created_at.desc()).all()

    campaigns_data = []
    for c in campaigns:
        total = len(c.logs)
        sent = sum(1 for l in c.logs if l.status in ('sent', 'delivered', 'read'))
        failed = sum(1 for l in c.logs if l.status == 'failed')
        campaigns_data.append({
            'campaign': c,
            'stats': {'total': total, 'sent': sent, 'failed': failed}
        })

    tags = Tag.query.all()

    templates = []
    if whatsapp_api.is_configured():
        templates_result = whatsapp_api.get_templates()
        templates = [t for t in templates_result.get("templates", []) if t.get("status") == "APPROVED"]

    return render_template('campaigns.html',
                         campaigns=campaigns_data,
                         tags=tags,
                         templates=templates)

@app.route("/campaigns/<int:campaign_id>")
def campaign_details_page(campaign_id):
    """Página de detalles de campaña."""
    campaign = Campaign.query.get_or_404(campaign_id)
    return render_template('campaign_details.html', campaign_id=campaign_id)

@app.route("/api/campaigns", methods=["GET"])
def api_list_campaigns():
    """Lista campañas."""
    campaigns = Campaign.query.order_by(Campaign.created_at.desc()).all()
    result = []
    for c in campaigns:
        total = len(c.logs)
        sent = sum(1 for l in c.logs if l.status in ('sent', 'delivered', 'read'))
        failed = sum(1 for l in c.logs if l.status == 'failed')
        result.append({
            'id': c.id,
            'name': c.name,
            'status': c.status,
            'tag': c.tag.name if c.tag else None,
            'template_name': c.template_name,
            'total': total,
            'sent': sent,
            'failed': failed,
            'created_at': format_utc_iso(c.created_at),
            'started_at': format_utc_iso(c.started_at),
            'completed_at': format_utc_iso(c.completed_at)
        })
    return jsonify(result)

@app.route("/api/campaigns", methods=["POST"])
def api_create_campaign():
    """Crea una nueva campaña."""
    data = request.json
    name = data.get('name')
    tag_id = data.get('tag_id')
    template_name = data.get('template_name')
    template_language = data.get('template_language', 'es_AR')
    scheduled_at_str = data.get('scheduled_at')
    variables = data.get('variables') # Dict {"1": "first_name", ...}

    if not name or not template_name:
        return jsonify({'error': 'name y template_name requeridos'}), 400

    if not tag_id:
        return jsonify({'error': 'tag_id requerido'}), 400

    tag = Tag.query.get(tag_id)
    if not tag:
        return jsonify({'error': 'Tag no encontrado'}), 404
        
    scheduled_at = None
    status = 'draft'
    
    if scheduled_at_str:
        # Asumimos que viene en ISO format o timestamp
        try:
            # Si viene con timezone, convertir a UTC. Si no, asumir que es UTC o manejarlo.
            # Simplificación: el frontend debe enviar ISO string.
            dt = datetime.fromisoformat(scheduled_at_str.replace('Z', '+00:00'))
            
            # Si es naive (no tiene timezone), asumir que es hora de Argentina
            if dt.tzinfo is None:
                ar_tz = pytz.timezone('America/Argentina/Buenos_Aires')
                dt = ar_tz.localize(dt)
            
            # Convertir a UTC para almacenamiento
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            
            scheduled_at = dt
            status = 'scheduled'
        except Exception as e:
            return jsonify({'error': f'Error en fecha programada: {str(e)}'}), 400

    campaign = Campaign(
        name=name,
        template_name=template_name,
        template_language=template_language,
        tag_id=tag_id,
        status=status,
        scheduled_at=scheduled_at,
        variables=variables
    )
    try:
        db.session.add(campaign)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating campaign: {e}")
        return jsonify({'error': str(e)}), 500

    return jsonify({
        'success': True,
        'id': campaign.id,
        'name': campaign.name,
        'status': campaign.status
    }), 201

@app.route("/api/campaigns/<int:campaign_id>", methods=["DELETE"])
def api_delete_campaign(campaign_id):
    """Elimina una campaña (solo si está en draft)."""
    campaign = Campaign.query.get(campaign_id)
    if not campaign:
        return jsonify({'error': 'Campaña no encontrada'}), 404
    if campaign.status != 'draft':
        return jsonify({'error': 'Solo se puede eliminar una campaña en estado draft'}), 400

    CampaignLog.query.filter_by(campaign_id=campaign_id).delete()
    db.session.delete(campaign)
    db.session.commit()
    return jsonify({'success': True})

@app.route("/api/campaigns/<int:campaign_id>/send", methods=["POST"])
def api_send_campaign(campaign_id):
    """Inicia el envío de una campaña en background."""
    campaign = Campaign.query.get(campaign_id)
    if not campaign:
        return jsonify({'error': 'Campaña no encontrada'}), 404
    if campaign.status != 'draft':
        return jsonify({'error': 'Solo se puede enviar una campaña en estado draft'}), 400

    if not campaign.tag_id:
        return jsonify({'error': 'La campaña debe tener un tag asignado'}), 400

    contacts = Contact.query.filter(
        Contact.tags.any(Tag.id == campaign.tag_id)
    ).all()

    if not contacts:
        return jsonify({'error': 'No hay contactos con ese tag'}), 400

    # Actualizar estado
    campaign.status = 'sending'
    campaign.started_at = datetime.utcnow()
    db.session.commit()

    # Crear logs pendientes - OPTIMIZADO PARA LOTES
    # 1. Obtener IDs de contactos que ya tienen log para esta campaña
    existing_logs = db.session.query(CampaignLog.contact_id)\
        .filter_by(campaign_id=campaign.id).all()
    existing_contact_ids = {r[0] for r in existing_logs}

    # 2. Preparar objetos para insert masivo
    new_logs = []
    for contact in contacts:
        if contact.id not in existing_contact_ids:
            new_logs.append(CampaignLog(
                campaign_id=campaign.id,
                contact_id=contact.id,
                contact_phone=contact.phone_number,
                status='pending'
            ))
    
    # 3. Insertar y commitear
    if new_logs:
        db.session.bulk_save_objects(new_logs)
        db.session.commit()

    ctx = app.app_context()
    t = threading.Thread(target=send_campaign_bg, args=(ctx, campaign.id))
    t.daemon = True
    t.start()

    return jsonify({
        'success': True,
        'status': 'sending',
        'total_contacts': len(contacts)
    })

def send_campaign_bg(app_context, cid):
    """Función de envío en background (reutilizable)."""
    with app_context:
        camp = Campaign.query.get(cid)
        if not camp: return
        
        logs = CampaignLog.query.filter_by(campaign_id=cid, status='pending').all()

        for log in logs:
            try:
                # Construir componentes con variables dinámicas
                components = None
                if camp.variables:
                    parameters = []
                    # Variables es un dict {"1": "field_name", ...}
                    sorted_vars = sorted(camp.variables.items(), key=lambda x: int(x[0]))

                    # Usar contact_id para obtener el contacto (o la relación directa)
                    contact = log.contact or Contact.query.get(log.contact_id)

                    for idx, field in sorted_vars:
                        value = "-"
                        if field == 'phone_number':
                            value = contact.phone_number
                        elif contact:
                            val = getattr(contact, field, None)
                            if val:
                                value = str(val)
                        
                        parameters.append({
                            "type": "text",
                            "text": value
                        })
                    
                    if parameters:
                        components = [{
                            "type": "body",
                            "parameters": parameters
                        }]

                result = whatsapp_api.send_template_message(
                    log.contact_phone,
                    camp.template_name,
                    camp.template_language,
                    components=components
                )
                
                if result.get('success'):
                    log.status = 'sent'
                    log.message_id = result.get('message_id')
                    wa_id = result.get('message_id')
                    if wa_id:
                        # Reemplazar placeholders para el historial local simplificado
                        content_preview = f'[Campaña: {camp.name}] [Template: {camp.template_name}]'
                        
                        new_msg = Message(
                            wa_message_id=wa_id,
                            phone_number=log.contact_phone,
                            direction='outbound',
                            message_type='template',
                            content=content_preview,
                            timestamp=datetime.utcnow()
                        )
                        db.session.add(new_msg)
                else:
                    log.status = 'failed'
                    log.error_detail = str(result.get('error') or result)
            except Exception as e:
                log.status = 'failed'
                log.error_detail = str(e)

            db.session.commit()
            time_module.sleep(1)  # Rate limiting

        camp.status = 'completed'
        camp.completed_at = datetime.utcnow()
        db.session.commit()

def run_scheduler():
    """Scheduler para verificar campañas programadas."""
    while True:
        try:
            with app.app_context():
                now = datetime.utcnow()
                # Buscar campañas programadas que ya deberían salir
                pending = Campaign.query.filter(
                    Campaign.status == 'scheduled',
                    Campaign.scheduled_at <= now
                ).all()
                
                for camp in pending:
                    logger.info(f"🚀 Ejecutando campaña programada: {camp.name}")
                    
                    # Verificar contactos
                    contacts = Contact.query.filter(
                        Contact.tags.any(Tag.id == camp.tag_id)
                    ).all()
                    
                    if not contacts:
                        camp.status = 'failed'
                        camp.completed_at = now
                        logger.warning(f"Campaña {camp.name} fallida: Sin contactos")
                        db.session.commit()
                        continue
                        
                    # Pasar a sending
                    camp.status = 'sending'
                    camp.started_at = now
                    db.session.commit()
                    
                    # Crear logs
                    # Crear logs - OPTIMIZADO
                    # 1. Obtener existentes
                    existing_logs = db.session.query(CampaignLog.contact_id)\
                        .filter_by(campaign_id=camp.id).all()
                    existing_ids = {r[0] for r in existing_logs}
                    
                    # 2. Batch insert
                    new_logs_sched = []
                    for contact in contacts:
                         if contact.id not in existing_ids:
                            new_logs_sched.append(CampaignLog(
                                campaign_id=camp.id,
                                contact_id=contact.id,
                                contact_phone=contact.phone_number,
                                status='pending'
                            ))
                    
                    if new_logs_sched:
                        db.session.bulk_save_objects(new_logs_sched)
                        db.session.commit()
                    
                    # Lanzar thread de envío
                    t = threading.Thread(target=send_campaign_bg, args=(app.app_context(), camp.id))
                    t.daemon = True
                    t.start()
                    
        except Exception as e:
            logger.error(f"Error en scheduler: {e}")
            
        time_module.sleep(60) # Revisar cada minuto

# Iniciar scheduler
scheduler_thread = threading.Thread(target=run_scheduler)
scheduler_thread.daemon = True
scheduler_thread.start()



@app.route("/api/campaigns/<int:campaign_id>/status", methods=["GET"])
def api_campaign_status(campaign_id):
    """Obtiene el estado en tiempo real de una campaña."""
    campaign = Campaign.query.get(campaign_id)
    if not campaign:
        return jsonify({'error': 'Campaña no encontrada'}), 404

    logs = CampaignLog.query.filter_by(campaign_id=campaign_id).all()
    total = len(logs)
    sent = sum(1 for l in logs if l.status in ('sent', 'delivered', 'read'))
    failed = sum(1 for l in logs if l.status == 'failed')
    pending = sum(1 for l in logs if l.status == 'pending')

    return jsonify({
        'id': campaign.id,
        'status': campaign.status,
        'total': total,
        'sent': sent,
        'failed': failed,
        'pending': pending,
        'started_at': format_utc_iso(campaign.started_at),
        'completed_at': format_utc_iso(campaign.completed_at)
    })

@app.route("/api/campaigns/<int:campaign_id>/stats_preview", methods=["GET"]) # Renamed to avoid conflict
def api_get_campaign_stats_preview(campaign_id):
    """Obtiene detalles completos de una campaña (Preview)."""
    campaign = Campaign.query.get(campaign_id)
    if not campaign:
        return jsonify({'error': 'Campaña no encontrada'}), 404

    logs = CampaignLog.query.filter_by(campaign_id=campaign_id).all()
    total = len(logs)
    sent = sum(1 for l in logs if l.status in ('sent', 'delivered', 'read'))
    read = sum(1 for l in logs if l.status == 'read')
    failed = sum(1 for l in logs if l.status == 'failed')
    
    # Preview de logs (últimos 50)
    preview_logs = []
    for l in logs[-50:]:
        contact = l.contact or Contact.query.get(l.contact_id)
        preview_logs.append({
            'phone': l.contact_phone,
            'name': contact.name if contact else '',
            'status': l.status,
            'error': l.error_detail
        })

    return jsonify({
        'id': campaign.id,
        'name': campaign.name,
        'status': campaign.status,
        'template_name': campaign.template_name,
        'tag_name': campaign.tag.name if campaign.tag else '??',
        'created_at': format_utc_iso(campaign.created_at),
        'scheduled_at': format_utc_iso(campaign.scheduled_at),
        'started_at': format_utc_iso(campaign.started_at),
        'completed_at': format_utc_iso(campaign.completed_at),
        'stats': {
            'total': total,
            'sent': sent,
            'read': read,
            'failed': failed
        },
        'logs_preview': preview_logs,
        'variables': campaign.variables
    })

@app.route("/api/campaigns/<int:campaign_id>")
def api_campaign_details(campaign_id):
    """API para obtener detalles y estadísticas de una campaña."""
    try:
        campaign = Campaign.query.get_or_404(campaign_id)
        
        # Estadísticas agregadas
        total_logs = CampaignLog.query.filter_by(campaign_id=campaign_id).count()
        
        # Contar por estados
        logs_stats = db.session.query(
            CampaignLog.status, func.count(CampaignLog.id)
        ).filter(
            CampaignLog.campaign_id == campaign_id
        ).group_by(CampaignLog.status).all()
        
        stats_map = {s: c for s, c in logs_stats}
        sent_count = stats_map.get('sent', 0)
        delivered_count = stats_map.get('delivered', 0)
        read_count = stats_map.get('read', 0)
        failed_count = stats_map.get('failed', 0)
        
        # 'Enviados' para la UI incluye todo lo que salió exitosamente (sent, delivered, read)
        total_successful = sent_count + delivered_count + read_count
        
        # Logs preview (últimos 50)
        # Logs preview con PAGINACIÓN
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        pagination = db.session.query(
            CampaignLog, Contact.name
        ).outerjoin(
            Contact, CampaignLog.contact_id == Contact.id
        ).filter(
            CampaignLog.campaign_id == campaign_id
        ).order_by(CampaignLog.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
        
        logs_preview = []
        for log, contact_name in pagination.items:
            logs_preview.append({
                'phone': log.contact_phone,
                'name': contact_name,
                'status': log.status,
                'error': log.error_detail,
                'created_at': format_utc_iso(log.created_at)
            })
            
        return jsonify({
            'id': campaign.id,
            'name': campaign.name,
            'status': campaign.status,
            'template_name': campaign.template_name,
            'tag_name': campaign.tag.name if campaign.tag else 'N/A',
            'created_at': format_utc_iso(campaign.created_at),
            'started_at': format_utc_iso(campaign.started_at),
            'completed_at': format_utc_iso(campaign.completed_at),
            'scheduled_at': format_utc_iso(campaign.scheduled_at),
            'stats': {
                'total': total_logs,
                'sent': total_successful,
                'read': read_count, 
                'failed': failed_count
            },
            'logs_preview': logs_preview,
            'pagination': {
                'page': pagination.page,
                'per_page': pagination.per_page,
                'total_pages': pagination.pages,
                'total_items': pagination.total,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting campaign details: {e}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/campaigns/<int:campaign_id>/export", methods=["GET"])
def api_export_campaign_stats(campaign_id):
    """Exporta reporte de campaña a Excel."""
    try:
        campaign = Campaign.query.get(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaña no encontrada'}), 404
            
        logs = CampaignLog.query.filter_by(campaign_id=campaign_id).all()
        
        data = []
        for l in logs:
            contact = l.contact or Contact.query.get(l.contact_id)
            data.append({
                'Telefono': l.contact_phone,
                'ID Cliente': contact.contact_id if contact else '',
                'Nombre Completo': contact.name if contact else '',
                'Nombre': contact.first_name if contact else '',
                'Apellido': contact.last_name if contact else '',
                'Estado Mensaje': l.status,
                'Error': l.error_detail or '',
                'Mensaje ID': l.message_id or ''
            })
            
        df = pd.DataFrame(data)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Reporte')
            
        output.seek(0)
        
        filename = f"reporte_{campaign.name}_{datetime.now().strftime('%Y%m%d')}.xlsx"
        # Limpiar nombre de archivo
        filename = "".join([c for c in filename if c.isalnum() or c in (' ', '.', '_')]).strip().replace(' ', '_')
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        logger.error(f"Error exportando campaña: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=Config.PORT, debug=False)
