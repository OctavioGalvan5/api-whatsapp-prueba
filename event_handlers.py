import requests
import json
import logging
from datetime import datetime
from config import Config

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def forward_to_chatwoot(payload):
    """
    Reenvía el payload exacto a Chatwoot.
    """
    if not Config.CHATWOOT_WEBHOOK_URL:
        logger.warning("CHATWOOT_WEBHOOK_URL no está configurada. No se reenviará el evento.")
        return

    try:
        # Reenviamos el payload tal cual a Chatwoot
        response = requests.post(
            Config.CHATWOOT_WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        if response.status_code != 200:
            logger.error(f"Error al reenviar a Chatwoot: {response.status_code} - {response.text}")
        else:
            logger.info(f"Evento reenviado a Chatwoot exitosamente. Status: {response.status_code}")
    except Exception as e:
        logger.error(f"Excepción al conectar con Chatwoot: {e}")

def save_message(wa_message_id, phone_number, direction, message_type, content):
    """Guarda un mensaje en la base de datos y registra el contacto."""
    from app import app
    from models import db, Message, Contact
    
    try:
        with app.app_context():
            # Verificar si ya existe
            existing = Message.query.filter_by(wa_message_id=wa_message_id).first()
            if existing:
                logger.info(f"Mensaje {wa_message_id} ya existe, omitiendo...")
                return
            
            # --- AUTO REGISTRO DE CONTACTO ---
            if phone_number and phone_number not in ['unknown', 'outbound', '']:
                contact = Contact.query.get(phone_number)
                if not contact:
                    new_contact = Contact(phone_number=phone_number)
                    db.session.add(new_contact)
                    logger.info(f"🆕 Contacto auto-registrado: {phone_number}")
            
            message = Message(
                wa_message_id=wa_message_id,
                phone_number=phone_number,
                direction=direction,
                message_type=message_type,
                content=content,
                timestamp=datetime.utcnow()
            )
            db.session.add(message)
            db.session.commit()
            logger.info(f"✅ Mensaje guardado en BD: {wa_message_id}")
    except Exception as e:
        logger.error(f"Error guardando mensaje en BD: {e}")

def save_status(wa_message_id, status, recipient_id=None, error_code=None, error_title=None, error_details=None):
    """Guarda un estado de mensaje en la base de datos."""
    from app import app
    from models import db, Message, MessageStatus
    
    try:
        with app.app_context():
            # Verificar si el mensaje existe, si no, crear uno placeholder
            message = Message.query.filter_by(wa_message_id=wa_message_id).first()
            if not message:
                # Crear mensaje placeholder para mensajes salientes
                message = Message(
                    wa_message_id=wa_message_id,
                    phone_number=recipient_id or "unknown",
                    direction="outbound",
                    message_type="text",
                    timestamp=datetime.utcnow()
                )
                db.session.add(message)
                db.session.commit()
            elif message.phone_number in ["outbound", "unknown"] and recipient_id:
                # Actualizar el número si antes era placeholder
                message.phone_number = recipient_id
                db.session.commit()
            
            msg_status = MessageStatus(
                wa_message_id=wa_message_id,
                status=status,
                error_code=error_code,
                error_title=error_title,
                error_details=error_details,
                timestamp=datetime.utcnow()
            )
            db.session.add(msg_status)
            db.session.commit()
            logger.info(f"✅ Estado '{status}' guardado para mensaje: {wa_message_id}")
    except Exception as e:
        logger.error(f"Error guardando estado en BD: {e}")

def process_event(data):
    """
    Procesa el evento entrante de WhatsApp.
    Aquí es donde extraemos datos para nuestra propia lógica (DB, Dashboard, etc.)
    antes de reenviarlo a Chatwoot.
    """
    
    # Validar estructura básica
    entry = data.get("entry", [])
    if not entry:
        return

    for item in entry:
        changes = item.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            
            # --- MANEJO DE MENSAJES ---
            if "messages" in value:
                for message in value["messages"]:
                    sender = message.get("from")
                    msg_type = message.get("type")
                    msg_id = message.get("id")
                    
                    # Extraer contenido según tipo
                    content = None
                    if msg_type == "text":
                        content = message.get("text", {}).get("body")
                    elif msg_type == "image":
                        content = "[Imagen]"
                    elif msg_type == "audio":
                        content = "[Audio]"
                    elif msg_type == "video":
                        content = "[Video]"
                    elif msg_type == "document":
                        content = "[Documento]"
                    elif msg_type == "sticker":
                        content = "[Sticker]"
                    elif msg_type == "location":
                        content = "[Ubicación]"
                    
                    logger.info(f"NUEVO MENSAJE de {sender} tipo {msg_type}: {message}")
                    
                    # Guardar mensaje en base de datos
                    save_message(msg_id, sender, "inbound", msg_type, content)

            # --- MANEJO DE ESTADOS (SENT, DELIVERED, READ, FAILED) ---
            if "statuses" in value:
                for status in value["statuses"]:
                    # DEBUG: Ver todo el objeto status
                    logger.info(f"📋 STATUS COMPLETO: {json.dumps(status, indent=2)}")
                    
                    recipient = status.get("recipient_id")
                    status_type = status.get("status")  # sent, delivered, read, failed
                    msg_id = status.get("id")
                    
                    logger.info(f"ACTUALIZACIÓN DE ESTADO: {status_type} para {recipient} (msg_id: {msg_id})")
                    
                    # Extraer errores si existen
                    error_code = None
                    error_title = None
                    error_details = None
                    
                    if status_type == "failed":
                        errors = status.get("errors", [])
                        if errors:
                            error_code = str(errors[0].get("code", ""))
                            error_title = errors[0].get("title", "")
                            error_details = json.dumps(errors)
                        logger.error(f"❌ ERROR DE ENVÍO a {recipient}. Detalles: {errors}")
                    
                    if status_type == "read":
                        logger.info(f"👁️‍🗨️ ¡El usuario {recipient} LEYÓ el mensaje!")
                    
                    # Guardar estado en base de datos
                    save_status(msg_id, status_type, recipient, error_code, error_title, error_details)

    # Finalmente, reenviar todo a Chatwoot para que su flujo no se rompa
    forward_to_chatwoot(data)

