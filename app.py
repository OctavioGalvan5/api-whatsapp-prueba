import logging
import json
import requests
import io
import pandas as pd
from flask import Flask, request, jsonify, render_template, send_file
from config import Config
from models import db, Message, MessageStatus, Contact
from event_handlers import process_event
from sqlalchemy import func
from datetime import datetime, timedelta, timezone
import logging
import pytz

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

# Inicializar SQLAlchemy
db.init_app(app)

# Crear tablas al iniciar
with app.app_context():
    db.create_all()

# Importar servicio de WhatsApp (después de crear app)
from whatsapp_service import whatsapp_api

@app.route("/", methods=["GET"])
def index():
    return "WhatsApp Middleware is running!", 200

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
            logger.error(f"Verificación fallida. Token recibido: {token} != Esperado: {Config.VERIFY_TOKEN}")
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
        
        contact_details = Contact.query.get(selected_phone)
        
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
    # Obtener todos los mensajes salientes
    outbound_messages = Message.query.filter(
        Message.direction == 'outbound'
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

def register_contact_if_new(phone_number, name=None):
    """Registra un contacto si no existe."""
    try:
        if not phone_number or phone_number in ['unknown', 'outbound', '']:
            return
            
        contact = Contact.query.get(phone_number)
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

@app.route("/api/contacts/<phone_number>", methods=["GET", "POST"])
def api_contact_detail(phone_number):
    """API para obtener o actualizar un contacto."""
    contact = Contact.query.get(phone_number)
    
    if request.method == "POST":
        data = request.json
        if not contact:
            contact = Contact(phone_number=phone_number)
            db.session.add(contact)
        
        # Mapeo de campos
        fields = ['name', 'first_name', 'last_name', 'notes', 
                  'custom_field_1', 'custom_field_2', 'custom_field_3', 
                  'custom_field_4', 'custom_field_5', 'custom_field_6', 'custom_field_7']
        
        for field in fields:
            if field in data:
                setattr(contact, field, data[field])
                
        if 'tags' in data:
            contact.tags = data['tags']  # Debe ser una lista
            
        try:
            db.session.commit()
            logger.info(f"✅ Contacto actualizado: {phone_number}")
            return jsonify({'success': True, 'contact': contact.to_dict()})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500
            
    # GET method
    if not contact:
        return jsonify({'found': False, 'details': {'phone_number': phone_number}})
    
    return jsonify({'found': True, 'details': contact.to_dict()})

@app.route("/api/contacts/import", methods=["POST"])
def api_import_contacts():
    """Importar contactos desde Excel/CSV."""
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
            
        # Normalizar columnas
        df.columns = [c.lower().strip() for c in df.columns]
        
        required = ['phone', 'phone_number', 'telefono', 'numero']
        phone_col = next((c for c in df.columns if c in required), None)
        
        if not phone_col:
            return jsonify({'error': 'Columna de teléfono no encontrada (phone, phone_number, telefono)'}), 400
            
        count = 0
        updated = 0
        
        # Mapeo simple de nombres de columna a atributos del modelo
        col_map = {
            'name': 'name', 'nombre': 'name',
            'first_name': 'first_name', 'nombre_pila': 'first_name',
            'last_name': 'last_name', 'apellido': 'last_name',
            'notes': 'notes', 'notas': 'notes',
            'custom_1': 'custom_field_1', 'campo_1': 'custom_field_1',
            'custom_2': 'custom_field_2', 'campo_2': 'custom_field_2',
            'custom_3': 'custom_field_3', 'campo_3': 'custom_field_3',
            'custom_4': 'custom_field_4', 'campo_4': 'custom_field_4',
            'custom_5': 'custom_field_5', 'campo_5': 'custom_field_5',
            'custom_6': 'custom_field_6', 'campo_6': 'custom_field_6',
            'custom_7': 'custom_field_7', 'campo_7': 'custom_field_7'
        }

        for _, row in df.iterrows():
            phone = str(row[phone_col]).replace('.0', '').strip()
            
            contact = Contact.query.get(phone)
            if not contact:
                contact = Contact(phone_number=phone)
                db.session.add(contact)
                count += 1
            else:
                updated += 1
            
            # Actualizar campos detectados
            for col in df.columns:
                if col in col_map:
                    val = row.get(col)
                    if pd.notna(val):
                        setattr(contact, col_map[col], str(val))
                        
            # Tags special handling
            tags_str = row.get('tags') or row.get('etiquetas')
            if pd.notna(tags_str):
                contact.tags = [t.strip() for t in str(tags_str).split(',')] if tags_str else []
            
        db.session.commit()
        return jsonify({
            'success': True, 
            'message': f'Procesados {count + updated} contactos ({count} nuevos, {updated} actualizados)'
        })
        
    except Exception as e:
        logger.error(f"Error importando contactos: {e}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/contacts/export", methods=["GET"])
def api_export_contacts():
    # ... (code for export remains same) ...
    """Exportar contactos a Excel."""
    try:
        contacts = Contact.query.all()
        data = []
        for c in contacts:
            data.append({
                'Telefono': c.phone_number,
                'Nombre Completo': c.name,
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
                'Etiquetas': ', '.join(c.tags) if c.tags else '',
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
        contact = Contact.query.get(phone)
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
                'status': m.latest_status
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
    """Página para ver listado de contactos."""
    contacts = Contact.query.order_by(Contact.created_at.desc()).all()
    return render_template('contacts.html', contacts=contacts)

@app.route("/tags")
def tags_page():
    """Página para ver etiquetas y estadísticas."""
    # Obtener todas las etiquetas y contarlas
    contacts = Contact.query.all()
    tags_count = {}
    for c in contacts:
        if c.tags:
            for tag in c.tags:
                tag = tag.strip()
                if tag:
                    tags_count[tag] = tags_count.get(tag, 0) + 1
    
    # Ordenar por cantidad
    sorted_tags = sorted(tags_count.items(), key=lambda item: item[1], reverse=True)
    return render_template('tags.html', tags=sorted_tags, total_contacts=len(contacts))

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
    
    # Enriquecer con nombre de contacto
    enriched_failures = []
    for msg, status in failed_msgs:
        contact = Contact.query.get(msg.phone_number)
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
        contact = Contact.query.get(to_phone)
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=Config.PORT, debug=True)
