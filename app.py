from flask import Flask, request, jsonify, render_template
from config import Config
from models import db, Message, MessageStatus
from event_handlers import process_event
from sqlalchemy import func
from datetime import datetime, timedelta
import logging

app = Flask(__name__)
logger = logging.getLogger(__name__)

# Configuración de la base de datos
app.config['SQLALCHEMY_DATABASE_URI'] = Config.DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inicializar SQLAlchemy
db.init_app(app)

# Crear tablas al iniciar
with app.app_context():
    db.create_all()

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
    """Dashboard para visualizar estadísticas de mensajes."""
    # Obtener estadísticas
    twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
    
    # Total de mensajes
    total = Message.query.filter(Message.timestamp >= twenty_four_hours_ago).count()
    
    # Contar estados
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
    
    # Calcular tasa de éxito
    total_attempts = sent + delivered + read + failed
    success_rate = round(((delivered + read) / total_attempts * 100) if total_attempts > 0 else 100, 1)
    
    stats = {
        'total': total,
        'sent': sent,
        'delivered': delivered,
        'read': read,
        'failed': failed,
        'success_rate': success_rate
    }
    
    # Obtener mensajes recientes
    messages = Message.query.order_by(Message.timestamp.desc()).limit(50).all()
    
    return render_template('dashboard.html', stats=stats, messages=messages)

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
            
            if messages:
                first_msg = messages[0]
                message_type_cw = first_msg.get("message_type")
                source_id = first_msg.get("source_id")
            
            # Obtener el número de teléfono desde contact_inbox
            contact_inbox = conversation.get("contact_inbox", {})
            phone_number = contact_inbox.get("source_id", "").replace("+", "")
            
            logger.info(f"📝 message_type: {message_type_cw}, content: {content[:100] if content else 'N/A'}")
            
            # Solo mensajes salientes (message_type=1 en Chatwoot)
            if message_type_cw == 1 and content:
                logger.info(f"📤 MENSAJE SALIENTE: '{content[:50]}...' para {phone_number} (source_id: {source_id})")
                
                # Si tenemos source_id (wa_message_id), actualizar o crear
                if source_id:
                    existing = Message.query.filter_by(wa_message_id=source_id).first()
                    if existing:
                        if not existing.content:
                            existing.content = content
                            logger.info(f"✅ Contenido actualizado para mensaje existente: {source_id}")
                        if phone_number and existing.phone_number in ["outbound", "unknown"]:
                            existing.phone_number = phone_number
                        db.session.commit()
                    else:
                        # Crear el mensaje
                        new_msg = Message(
                            wa_message_id=source_id,
                            phone_number=phone_number or "unknown",
                            direction="outbound",
                            message_type="text",
                            content=content,
                            timestamp=datetime.utcnow()
                        )
                        db.session.add(new_msg)
                        db.session.commit()
                        logger.info(f"✅ Mensaje saliente creado con source_id: {source_id}")
                else:
                    # Si no hay source_id, crear con ID de Chatwoot
                    if messages:
                        cw_msg_id = f"cw_{messages[0].get('id', '')}"
                        existing = Message.query.filter_by(wa_message_id=cw_msg_id).first()
                        if not existing:
                            new_msg = Message(
                                wa_message_id=cw_msg_id,
                                phone_number=phone_number or "unknown",
                                direction="outbound",
                                message_type="text",
                                content=content,
                                timestamp=datetime.utcnow()
                            )
                            db.session.add(new_msg)
                            db.session.commit()
                            logger.info(f"✅ Mensaje saliente guardado con cw_id: {cw_msg_id}")
        
        return "OK", 200
        
    except Exception as e:
        logger.error(f"Error en chatwoot webhook: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return "Internal Server Error", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=Config.PORT, debug=True)

