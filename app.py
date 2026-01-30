from flask import Flask, request, jsonify, render_template
from config import Config
from models import db, Message, MessageStatus
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
    
    # Lista de contactos con estadísticas
    contacts_query = db.session.query(
        Message.phone_number,
        func.count(Message.id).label('message_count'),
        func.max(Message.timestamp).label('last_timestamp'),
        func.max(Message.content).label('last_message')
    ).filter(
        Message.phone_number.notin_(['unknown', 'outbound', ''])
    ).group_by(Message.phone_number).order_by(func.max(Message.timestamp).desc()).all()
    
    contacts = []
    for c in contacts_query:
        contacts.append({
            'phone_number': c.phone_number,
            'message_count': c.message_count,
            'last_timestamp': c.last_timestamp,
            'last_message': (c.last_message[:50] + '...') if c.last_message and len(c.last_message) > 50 else c.last_message
        })
    
    # Si hay contacto seleccionado, obtener sus mensajes
    messages = []
    contact_stats = {}
    selected_contact = None
    
    if selected_phone:
        selected_contact = selected_phone
        messages = Message.query.filter_by(phone_number=selected_phone).order_by(Message.timestamp.asc()).all()
        
        # Estadísticas del contacto
        outbound_msgs = [m for m in messages if m.direction == 'outbound']
        contact_stats = {
            'message_count': len(messages),
            'sent': sum(1 for m in outbound_msgs if m.latest_status in ['sent', 'delivered', 'read']),
            'delivered': sum(1 for m in outbound_msgs if m.latest_status in ['delivered', 'read']),
            'read': sum(1 for m in outbound_msgs if m.latest_status == 'read')
        }
    elif contacts:
        # Seleccionar primer contacto por defecto
        selected_contact = contacts[0]['phone_number']
        messages = Message.query.filter_by(phone_number=selected_contact).order_by(Message.timestamp.asc()).all()
        outbound_msgs = [m for m in messages if m.direction == 'outbound']
        contact_stats = {
            'message_count': len(messages),
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
    
    return render_template('dashboard.html', 
                         stats=stats, 
                         contacts=contacts, 
                         messages=messages,
                         selected_contact=selected_contact,
                         contact_stats=contact_stats,
                         chart_data=chart_data)

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
    
    # Insights
    peak_hour = max(sent_by_hour, key=lambda x: x.count) if sent_by_hour else None
    busiest_dow = dow_counts.index(max(dow_counts)) if dow_counts else 0
    days_names = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    
    insights = {
        'peak_hour': int(peak_hour.hour) if peak_hour and peak_hour.hour else 12,
        'peak_hour_count': peak_hour.count if peak_hour else 0,
        'read_rate': round((read / outbound * 100) if outbound > 0 else 0, 1),
        'busiest_day': days_names[busiest_dow],
        'avg_daily': round(total_messages / 30, 1) if total_messages > 0 else 0
    }
    
    return render_template('analytics.html', stats=stats, chart_data=chart_data, insights=insights)

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
                    new_msg = Message(
                        wa_message_id=msg_id,
                        phone_number=phone_number or "unknown",
                        direction="outbound",
                        message_type="text",
                        content=content,
                        timestamp=datetime.utcnow()
                    )
                    db.session.add(new_msg)
                    db.session.commit()
                    logger.info(f"✅ Mensaje saliente creado: {msg_id}")
        
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
    """API para enviar mensaje con template."""
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    to_phone = data.get("to")
    template_name = data.get("template_name")
    language = data.get("language", "es_AR")
    components = data.get("components")
    
    if not to_phone or not template_name:
        return jsonify({"error": "to y template_name son requeridos"}), 400
    
    result = whatsapp_api.send_template_message(to_phone, template_name, language, components)
    
    if result.get("success"):
        # Guardar mensaje en BD
        new_msg = Message(
            wa_message_id=result.get("message_id", f"template_{datetime.utcnow().timestamp()}"),
            phone_number=to_phone,
            direction="outbound",
            message_type="template",
            content=f"[Template: {template_name}]",
            timestamp=datetime.utcnow()
        )
        db.session.add(new_msg)
        db.session.commit()
        
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
        # Guardar mensaje en BD
        new_msg = Message(
            wa_message_id=result.get("message_id", f"text_{datetime.utcnow().timestamp()}"),
            phone_number=to_phone,
            direction="outbound",
            message_type="text",
            content=text,
            timestamp=datetime.utcnow()
        )
        db.session.add(new_msg)
        db.session.commit()
        
    return jsonify(result)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=Config.PORT, debug=True)
