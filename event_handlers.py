import requests
import json
import logging
from datetime import datetime
from config import Config

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def forward_to_n8n(user_number, user_message, msg_type, media_url=None, media_data=None, message_id=None):
    """
    Envía el mensaje procesado directamente al webhook del chatbot en n8n.
    """
    if not Config.N8N_CHATBOT_WEBHOOK_URL:
        logger.warning("N8N_CHATBOT_WEBHOOK_URL no está configurada. No se enviará el mensaje al chatbot.")
        return

    MEDIA_TYPES = {'image', 'audio', 'video', 'document', 'sticker'}
    has_attachments = msg_type in MEDIA_TYPES

    # Mapeo de content-type y extensión según tipo
    CONTENT_TYPE_MAP = {
        'image': 'image/jpeg', 'audio': 'audio/ogg',
        'video': 'video/mp4', 'document': 'application/octet-stream', 'sticker': 'image/webp'
    }
    EXT_MAP = {'image': 'jpg', 'audio': 'ogg', 'video': 'mp4', 'sticker': 'webp'}

    attachment_content_type = CONTENT_TYPE_MAP.get(msg_type, '') if has_attachments else ''
    attachment_extension = EXT_MAP.get(msg_type, '') if has_attachments else ''

    # Para documentos intentar extraer extensión del filename
    if msg_type == 'document' and media_data:
        filename = media_data.get('filename', '')
        if '.' in filename:
            attachment_extension = filename.rsplit('.', 1)[-1].lower()
            if attachment_extension == 'pdf':
                attachment_content_type = 'application/pdf'

    payload = {
        "user_number": user_number,
        "message_type": 0,
        "user_message": user_message or "",
        "has_attachments": has_attachments,
        "attachment_type": msg_type if has_attachments else "none",
        "attachment_url": (Config.FLASK_BASE_URL.rstrip('/') + media_url if media_url and media_url.startswith('/') else media_url or ""),
        "attachment_content_type": attachment_content_type,
        "attachment_extension": attachment_extension,
        "message_id": message_id or "",
        "updated_at": datetime.utcnow().isoformat()
    }

    try:
        response = requests.post(
            Config.N8N_CHATBOT_WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        if response.status_code not in [200, 202]:
            logger.error(f"Error al llamar n8n: {response.status_code} - {response.text}")
        else:
            logger.info(f"✅ Mensaje enviado a n8n para {user_number}")
    except Exception as e:
        logger.error(f"Excepción al conectar con n8n: {e}")

def save_message(wa_message_id, phone_number, direction, message_type, content, media_id=None, media_url=None, caption=None):
    """Guarda un mensaje en la base de datos y registra el contacto."""
    from app import app
    from models import db, Message, Contact
    
    from sqlalchemy.exc import IntegrityError
    
    try:
        with app.app_context():
            # Verificar si ya existe el mensaje
            existing = Message.query.filter_by(wa_message_id=wa_message_id).first()
            if existing:
                logger.info(f"Mensaje {wa_message_id} ya existe, omitiendo...")
                return
            
            # --- AUTO REGISTRO DE CONTACTO (Con manejo de Race Condition) ---
            if phone_number and phone_number not in ['unknown', 'outbound', '']:
                # Intentar buscar primero
                contact = Contact.query.filter_by(phone_number=phone_number).first()
                if not contact:
                    try:
                        # Intentar crear y commitear inmediatamente solo el contacto
                        new_contact = Contact(phone_number=phone_number)
                        db.session.add(new_contact)
                        db.session.commit()
                        logger.info(f"🆕 Contacto auto-registrado: {phone_number}")
                    except IntegrityError:
                        db.session.rollback()
                        logger.info(f"Contacto {phone_number} ya fue creado concurrentemente.")
                    except Exception as e:
                        db.session.rollback()
                        logger.error(f"Error creando contacto {phone_number}: {e}")

            # Manejo de tipos interactivos si el contenido es nulo
            if not content and message_type == "interactive":
                content = "[Interactivo/Botón]"

            message = Message(
                wa_message_id=wa_message_id,
                phone_number=phone_number,
                direction=direction,
                message_type=message_type,
                content=content or "[Contenido no compatible]", # Fallback para evitar nulos confusos
                media_id=media_id,
                media_url=media_url,
                caption=caption,
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
            
            # --- ACTUALIZAR ESTADO DE CAMPAÑA SI CORRESPONDE ---
            from models import CampaignLog
            campaign_log = CampaignLog.query.filter_by(message_id=wa_message_id).first()
            if campaign_log:
                campaign_log.status = status
                if error_details:
                    campaign_log.error_detail = error_details
                logger.info(f"📊 Actualizado log de campaña {campaign_log.id} a '{status}'")
            
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
                    media_id = None
                    media_url = None
                    caption = None
                    
                    if msg_type == "text":
                        content = message.get("text", {}).get("body")
                    
                    elif msg_type in ["image", "audio", "video", "document", "sticker"]:
                        media_data = message.get(msg_type, {})
                        media_id = media_data.get("id")
                        caption = media_data.get("caption") if msg_type in ["image", "video", "document"] else None
                        content = f"[{msg_type.capitalize()}] {caption or ''}".strip()
                        
                        # Descargar media
                        from whatsapp_service import whatsapp_api
                        media_url = whatsapp_api.download_media(media_id)
                        
                    elif msg_type == "location":
                        loc = message.get("location", {})
                        lat = loc.get("latitude", "")
                        lon = loc.get("longitude", "")
                        content = f"[Ubicación: {lat}, {lon}]"

                    elif msg_type == "contacts":
                        contacts = message.get("contacts", [])
                        if contacts:
                            names = [c.get("name", {}).get("formatted_name", "Contacto") for c in contacts]
                            content = f"[Contacto: {', '.join(names)}]"
                        else:
                            content = "[Contacto compartido]"

                    elif msg_type == "reaction":
                        reaction = message.get("reaction", {})
                        emoji = reaction.get("emoji", "")
                        content = f"[Reacción: {emoji}]" if emoji else "[Reacción eliminada]"

                    elif msg_type == "interactive":
                        interactive = message.get("interactive", {})
                        int_type = interactive.get("type", "")
                        if int_type == "button_reply":
                            reply = interactive.get("button_reply", {})
                            content = reply.get("title", "[Respuesta a botón]")
                        elif int_type == "list_reply":
                            reply = interactive.get("list_reply", {})
                            content = reply.get("title", "[Respuesta a lista]")
                        else:
                            content = "[Respuesta interactiva]"

                    elif msg_type == "button":
                        button = message.get("button", {})
                        content = button.get("text", "[Respuesta a botón]")

                    elif msg_type == "unsupported":
                        content = "[Mensaje no soportado por WhatsApp API]"

                    else:
                        # Tipo desconocido - logear para debug
                        logger.warning(f"⚠️ Tipo de mensaje no manejado: {msg_type}")
                        content = f"[{msg_type or 'Desconocido'}]"

                    logger.info(f"NUEVO MENSAJE de {sender} tipo {msg_type}: {message}")

                    # Guardar mensaje en base de datos
                    save_message(msg_id, sender, "inbound", msg_type, content,
                               media_id=media_id, media_url=media_url, caption=caption)

                    # Cancelar follow-ups activos si el cliente responde
                    try:
                        from followup_sender import cancel_enrollment_on_reply
                        from app import app
                        cancel_enrollment_on_reply(sender, app.app_context())
                    except Exception as e:
                        logger.warning(f"No se pudo cancelar follow-up para {sender}: {e}")

                    # Enviar mensaje al chatbot n8n
                    media_data = message.get(msg_type, {}) if msg_type in {'image','audio','video','document','sticker'} else None
                    forward_to_n8n(sender, content, msg_type, media_url=media_url, media_data=media_data, message_id=msg_id)

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


