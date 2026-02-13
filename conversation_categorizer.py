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


def run_categorization(app_context):
    """Main categorization job - runs periodically."""
    if not client:
        return
    
    with app_context:
        from models import db, Message, ConversationTopic, ConversationSession
        
        try:
            # Find all topics for prompt
            topics = ConversationTopic.query.all()
            if not topics:
                logger.debug("No topics configured - skipping categorization")
                return
            
            cutoff_time = datetime.utcnow() - timedelta(minutes=INACTIVITY_MINUTES)
            
            # Get distinct phone numbers with activity since start date
            phones_query = db.session.query(
                Message.phone_number
            ).filter(
                Message.phone_number.notin_(['unknown', 'outbound', '']),
                Message.timestamp >= CATEGORIZATION_START_DATE
            ).distinct().all()
            
            for (phone,) in phones_query:
                # Get all messages for this phone since start date
                messages = Message.query.filter(
                    Message.phone_number == phone,
                    Message.timestamp >= CATEGORIZATION_START_DATE
                ).order_by(Message.timestamp).all()
                
                if len(messages) < 2:
                    continue
                
                # Split into sessions based on time gaps
                sessions = split_into_sessions(messages)
                
                for session_msgs in sessions:
                    if len(session_msgs) < 2:
                        continue
                    
                    session_start = session_msgs[0].timestamp
                    session_end = session_msgs[-1].timestamp
                    
                    # Only categorize if session ended >15 min ago (inactive)
                    if session_end >= cutoff_time:
                        continue  # Still active, skip
                    
                    # Check if this session was already categorized
                    existing = ConversationSession.query.filter(
                        ConversationSession.phone_number == phone,
                        ConversationSession.started_at == session_start,
                        ConversationSession.ended_at == session_end
                    ).first()
                    
                    if existing:
                        continue  # Already categorized
                    
                    # Categorize this session
                    categorize_conversation(
                        db, phone, session_msgs, topics,
                        session_start, session_end
                    )
                
        except Exception as e:
            logger.error(f"Error in categorization job: {e}")


def split_into_sessions(messages):
    """
    Split messages into separate sessions based on time gaps.
    If there's >30 min gap between messages, start a new session.
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
        
        if gap >= SESSION_GAP_MINUTES:
            # Start new session
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
    for msg in messages:
        role = "Usuario" if msg.direction == "inbound" else "Bot"
        content = msg.content or f"[{msg.message_type}]"
        conv_lines.append(f"[{role}]: {content[:200]}")  # Limit content length
    
    conversation_text = "\n".join(conv_lines[-20:])  # Limit to last 20 messages
    
    # Build topics text
    topics_text = ""
    for t in topics:
        keywords_str = ", ".join(t.keywords or [])
        topics_text += f"- {t.name}\n  Descripción: {t.description or 'Sin descripción'}\n  Palabras clave: {keywords_str}\n\n"
    
    # OpenAI prompt
    prompt = f"""Analiza esta conversación de chat y categorízala.

TEMAS DISPONIBLES:
{topics_text}

CONVERSACIÓN:
{conversation_text}

Responde SOLO con un JSON válido con este formato exacto:
{{
  "topic": "nombre exacto del tema (debe coincidir exactamente con uno de los nombres de arriba) o 'Otro' si no encaja",
  "rating": "excelente|buena|neutral|mala|problematica",
  "summary": "resumen de 1-2 oraciones cortas",
  "has_unanswered_questions": true/false,
  "needs_human_assistance": true/false
}}

Criterios para rating:
- excelente: El usuario recibió ayuda completa y quedó satisfecho
- buena: El usuario recibió información útil
- neutral: Conversación fue informativa pero sin impacto claro
- mala: El usuario no obtuvo lo que buscaba o hubo problemas
- problematica: Quejas, insultos, o usuario muy frustrado

Criterios para has_unanswered_questions:
- true: El usuario hizo preguntas que el bot no pudo responder, o el bot dijo explícitamente que no encontró información
- false: Todas las preguntas fueron respondidas adecuadamente

Criterios para needs_human_assistance:
- true: El usuario necesita atención humana (consulta compleja, queja seria, el bot no pudo ayudar repetidamente, o el usuario pidió hablar con una persona)
- false: La conversación se resolvió satisfactoriamente con el bot"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres un analizador de conversaciones. Responde siempre en JSON válido."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=300
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
            # Buscar contacto existente (NO crear uno nuevo para evitar duplicados)
            contact = Contact.query.filter_by(phone_number=phone).first()
            if contact:
                tag = Tag.query.filter_by(name='Asistencia Humana').first()
                if tag and tag not in contact.tags:
                    contact.tags.append(tag)
                    logger.info(f"Tag 'Asistencia Humana' assigned to existing contact {phone}")
            else:
                logger.warning(f"Contact {phone} not found in DB — tag not assigned (contact will get tag when n8n calls escalate endpoint)")

        db.session.commit()

        logger.info(f"Categorized session for {phone}: {topic_name} / {result.get('rating')} ({len(messages)} msgs) | human={needs_human}")
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OpenAI response: {e}")
    except Exception as e:
        logger.error(f"Error categorizing conversation: {e}")
