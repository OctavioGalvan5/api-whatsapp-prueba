"""
Conversation Categorizer Service
Detects inactive conversations and categorizes them using OpenAI.
Sessions are separated by 30+ minute gaps between messages.
"""
import os
import logging
import json
from datetime import datetime, timedelta
from openai import OpenAI

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = None
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)
    logger.info("OpenAI client initialized for conversation categorization")
else:
    logger.warning("OPENAI_API_KEY not set - conversation categorization disabled")

# Configuration
INACTIVITY_MINUTES = 15  # Wait time before categorizing
SESSION_GAP_MINUTES = 30  # Gap between messages to consider separate sessions
CATEGORIZATION_START_DATE = datetime(2026, 2, 3, 23, 0, 0)  # Only categorize from this date onwards


def run_categorization(app_context, force_phone=None):
    """Main categorization job - runs periodically.
    Args:
        app_context: Flask app context
        force_phone: If set, only categorize this phone number
    """
    if not client:
        logger.warning("⚠️ [CATEGORIZER] OpenAI client not initialized - skipping")
        return
    
    with app_context:
        from models import db, Message, ConversationTopic, ConversationSession
        
        try:
            logger.info(f"🔄 [CATEGORIZER] Job started (inactivity={INACTIVITY_MINUTES}min, session_gap={SESSION_GAP_MINUTES}min, start_date={CATEGORIZATION_START_DATE})")
            
            # Find all topics for prompt
            topics = ConversationTopic.query.all()
            if not topics:
                logger.warning("⚠️ [CATEGORIZER] No topics configured - skipping")
                return
            
            logger.info(f"📋 [CATEGORIZER] {len(topics)} topics loaded: {[t.name for t in topics]}")
            
            cutoff_time = datetime.utcnow() - timedelta(minutes=INACTIVITY_MINUTES)
            
            # Get distinct phone numbers with activity since start date
            phones_q = db.session.query(
                Message.phone_number
            ).filter(
                Message.phone_number.notin_(['unknown', 'outbound', '']),
                Message.timestamp >= CATEGORIZATION_START_DATE
            )
            if force_phone:
                phones_q = phones_q.filter(Message.phone_number == force_phone)
            phones_query = phones_q.distinct().all()
            
            total_phones = len(phones_query)
            total_categorized = 0
            total_skipped_active = 0
            total_skipped_existing = 0
            total_skipped_few_msgs = 0
            
            logger.info(f"📱 [CATEGORIZER] Found {total_phones} phones with activity since {CATEGORIZATION_START_DATE}")
            
            for (phone,) in phones_query:
                # Get all messages for this phone since start date
                messages = Message.query.filter(
                    Message.phone_number == phone,
                    Message.timestamp >= CATEGORIZATION_START_DATE
                ).order_by(Message.timestamp).all()
                
                if len(messages) < 2:
                    total_skipped_few_msgs += 1
                    logger.debug(f"  ⏭️ [CATEGORIZER] {phone}: only {len(messages)} msg(s) - skipping")
                    continue
                
                # Split into sessions based on time gaps
                sessions = split_into_sessions(messages)
                logger.debug(f"  📞 [CATEGORIZER] {phone}: {len(messages)} msgs → {len(sessions)} session(s)")
                
                for idx, session_msgs in enumerate(sessions):
                    # Permitir sesiones de 1 mensaje si tiene al menos un inbound
                    # (ej: respuesta solitaria a una campaña que quedó en sesión separada)
                    has_inbound = any(m.direction == 'inbound' for m in session_msgs)
                    if len(session_msgs) < 2 and not has_inbound:
                        total_skipped_few_msgs += 1
                        continue
                    
                    session_start = session_msgs[0].timestamp
                    session_end = session_msgs[-1].timestamp
                    
                    # Only categorize if session ended >15 min ago (inactive)
                    if session_end >= cutoff_time:
                        total_skipped_active += 1
                        logger.debug(f"  ⏳ [CATEGORIZER] {phone} session {idx+1}: still active (last msg {session_end}) - skipping")
                        continue
                    
                    # Check if this session was already categorized
                    existing = ConversationSession.query.filter(
                        ConversationSession.phone_number == phone,
                        ConversationSession.started_at == session_start,
                        ConversationSession.ended_at == session_end
                    ).first()
                    
                    if existing:
                        total_skipped_existing += 1
                        continue
                    
                    # Categorize this session
                    logger.info(f"  🤖 [CATEGORIZER] {phone} session {idx+1}: categorizing {len(session_msgs)} msgs ({session_start} → {session_end})")
                    categorize_conversation(
                        db, phone, session_msgs, topics,
                        session_start, session_end
                    )
                    total_categorized += 1
            
            logger.info(f"✅ [CATEGORIZER] Job complete: {total_phones} phones | {total_categorized} categorized | {total_skipped_existing} already done | {total_skipped_active} still active | {total_skipped_few_msgs} too few msgs")
                
        except Exception as e:
            logger.error(f"❌ [CATEGORIZER] Error in categorization job: {e}", exc_info=True)


def split_into_sessions(messages):
    """
    Split messages into separate sessions based on time gaps.
    If there's >30 min gap between messages, start a new session.
    
    EXCEPCIÓN: Si el mensaje anterior es un template/campaña outbound
    y el siguiente es inbound, NO separar (el usuario está respondiendo
    a la campaña, sin importar cuánto tiempo pasó).
    """
    if not messages:
        return []
    
    sessions = []
    current_session = [messages[0]]
    
    for i in range(1, len(messages)):
        prev_msg = messages[i - 1]
        curr_msg = messages[i]
        
        # Calculate time gap between messages
        gap = (curr_msg.timestamp - prev_msg.timestamp).total_seconds() / 60
        
        # Detectar si es una respuesta a template/campaña
        is_campaign_response = (
            prev_msg.direction == 'outbound'
            and prev_msg.message_type == 'template'
            and curr_msg.direction == 'inbound'
        )
        
        if gap >= SESSION_GAP_MINUTES and not is_campaign_response:
            # Start new session (pero NO si es respuesta a campaña)
            sessions.append(current_session)
            current_session = [curr_msg]
        else:
            # Continue current session
            current_session.append(curr_msg)
    
    # Add the last session
    if current_session:
        sessions.append(current_session)
    
    return sessions


def categorize_conversation(db, phone, messages, topics, started_at, ended_at):
    """Categorize a single conversation session using OpenAI."""
    from models import ConversationSession
    
    # Build conversation text
    conv_lines = []
    has_bot_response = False
    last_role = None

    for msg in messages:
        role = "Usuario" if msg.direction == "inbound" else "Bot"
        content = msg.content or f"[{msg.message_type}]"
        conv_lines.append(f"[{role}]: {content[:200]}")  # Limit content length

        if role == "Bot":
            has_bot_response = True
        last_role = role

    conversation_text = "\n".join(conv_lines[-20:])  # Limit to last 20 messages

    # Agregar nota si la última interacción fue del usuario sin respuesta
    if last_role == "Usuario":
        conversation_text += "\n\n[NOTA]: La conversación terminó con un mensaje del Usuario SIN respuesta del Bot."
    
    # Build topics text
    topics_text = ""
    for t in topics:
        keywords_str = ", ".join(t.keywords or [])
        topics_text += f"- {t.name}\n  Descripción: {t.description or 'Sin descripción'}\n  Palabras clave: {keywords_str}\n\n"
    
    # OpenAI prompt
    prompt = f"""Analiza esta conversación de WhatsApp entre un usuario y un bot de una caja de abogados y categorízala.

TEMAS DISPONIBLES:
{topics_text}

CONVERSACIÓN:
{conversation_text}

Responde SOLO con un JSON válido con este formato exacto:
{{
  "topic": "nombre exacto del tema (debe coincidir exactamente con uno de los nombres de arriba) o 'Otro' si no encaja",
  "rating": "buena|neutral|mala",
  "summary": "resumen de 1-2 oraciones cortas",
  "has_unanswered_questions": true/false,
  "needs_human_assistance": true/false
}}

Criterios para rating:
- buena: El usuario recibió información útil, ayuda completa o templates automáticos relevantes, y la conversación fue satisfactoria o positiva
- neutral: Conversación informativa pero sin impacto claro, solo saludos/confirmaciones, o interacción básica sin problemas
- mala: El usuario no obtuvo lo que buscaba, hubo confusión, frustración, quejas, el bot no pudo ayudar, o el usuario quedó insatisfecho

Criterios para has_unanswered_questions (analiza si hay PREGUNTAS REALES sin respuesta):
- true SOLO si:
  * El usuario hizo una PREGUNTA ESPECÍFICA (interrogación, solicitud de información) Y el bot NO respondió a esa pregunta
  * El bot dijo explícitamente "no tengo esa información" o "no puedo ayudarte con eso"
  * La conversación terminó con una pregunta del usuario sin ninguna respuesta del bot después
- false si:
  * Todas las preguntas fueron respondidas (incluso con templates automáticos)
  * El usuario solo hace comentarios, afirmaciones o exclamaciones (NO son preguntas)
  * El usuario solo saluda o se despide
  * El usuario informa algo sin esperar respuesta

Criterios para needs_human_assistance (SÉ MUY SELECTIVO, evita falsos positivos):
- true SOLO si se cumple AL MENOS UNO de estos casos GRAVES:
  * El usuario hizo una PREGUNTA ESPECÍFICA sobre temas complejos (planes de pago personalizados, casos especiales, trámites urgentes) Y el bot NO pudo responder adecuadamente
  * El usuario expresó QUEJA SERIA o frustración clara pidiendo solución
  * El usuario EXPLÍCITAMENTE pidió hablar con una persona, ser contactado, o que alguien lo llame
  * El bot dijo que no puede ayudar y sugirió contacto humano
  * Hay preguntas sin responder Y el tema es crítico (deudas, situaciones legales, urgencias)

- false si:
  * El usuario solo expresó emociones o exclamaciones pero fue atendido con información automática (templates/campañas)
  * El usuario solo saludó, se despidió, o dio las gracias
  * El usuario hizo un comentario informativo sin esperar acción específica
  * El usuario dijo que hará algo ("voy a ir", "llamaré después", etc.) sin pedir ayuda inmediata
  * La conversación fue respondida con templates informativos aunque sean genéricos (campañas, recordatorios automáticos)
  * El usuario preguntó algo básico y recibió template automático relevante

CONTEXTO IMPORTANTE:
- Los mensajes verdes son templates/campañas automáticas del sistema (NO del bot conversacional)
- Si un template automático responde adecuadamente al contexto del usuario, NO requiere asistencia humana
- Solo marca needs_human_assistance=true si el usuario realmente necesita interacción personalizada que el sistema automatizado no puede proporcionar

EJEMPLOS DE FALSOS POSITIVOS A EVITAR:
❌ "SOY JUBILADO!!!!" + template de obras sociales → needs_human_assistance=false (fue atendido con info relevante)
❌ "Ya aboné la semana pasada" → needs_human_assistance=false (es una afirmación, no pide ayuda)
❌ "Buenos días" → needs_human_assistance=false (solo saludo)
❌ "Voy a pedir un turno para regularizar" → needs_human_assistance=false (informa su plan, no pide ayuda)

EJEMPLOS DE VERDADEROS POSITIVOS:
✅ "Se podrá hacer un plan de pago?" + sin respuesta del bot → needs_human_assistance=true (pregunta específica sin respuesta)
✅ "Necesito hablar con alguien urgente" → needs_human_assistance=true (solicitud explícita)
✅ "El bot no me ayuda, esto es urgente" → needs_human_assistance=true (frustración + urgencia)"""

    try:
        response = client.chat.completions.create(
            model="gpt-5-nano",
            messages=[
                {"role": "system", "content": "Eres un analizador experto de conversaciones de atención al cliente. Tu trabajo es clasificar conversaciones con alta precisión, evitando falsos positivos. Sé muy selectivo al marcar conversaciones que requieren asistencia humana. Responde siempre en JSON válido."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=400
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # Clean JSON if wrapped in markdown
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        
        result = json.loads(result_text)
        
        # Find matching topic
        topic_id = None
        topic_name = result.get("topic", "Otro")
        for t in topics:
            if t.name.lower() == topic_name.lower():
                topic_id = t.id
                break
        
        needs_human = result.get("needs_human_assistance", False)

        # Create session record
        session = ConversationSession(
            phone_number=phone,
            topic_id=topic_id,
            rating=result.get("rating", "neutral"),
            started_at=started_at,
            ended_at=ended_at,
            message_count=len(messages),
            summary=result.get("summary", ""),
            auto_categorized=True,
            has_unanswered_questions=result.get("has_unanswered_questions", False),
            escalated_to_human=needs_human
        )

        db.session.add(session)

        # Si necesita asistencia humana, asignar la etiqueta al contacto existente
        if needs_human:
            from models import Contact, Tag
            # Normalizar número (tolerancia a '+' inicial)
            phone_normalized = phone.strip().lstrip('+')
            # Buscar contacto existente (NO crear uno nuevo para evitar duplicados)
            contact = Contact.query.filter_by(phone_number=phone_normalized).first()
            if not contact:
                contact = Contact.query.filter_by(phone_number='+' + phone_normalized).first()
            if contact:
                tag = Tag.query.filter_by(name='Asistencia Humana').first()
                if tag and tag not in contact.tags:
                    contact.tags.append(tag)
                    logger.info(f"Tag 'Asistencia Humana' assigned to existing contact {phone_normalized}")
            else:
                logger.warning(f"Contact {phone_normalized} not found in DB — tag not assigned (contact will get tag when n8n calls escalate endpoint)")

        db.session.commit()

        logger.info(f"Categorized session for {phone}: {topic_name} / {result.get('rating')} ({len(messages)} msgs) | human={needs_human}")
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OpenAI response: {e}")
    except Exception as e:
        logger.error(f"Error categorizing conversation: {e}")
