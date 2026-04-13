"""
Auto Tagger Service
Analiza conversaciones inactivas y asigna etiquetas automáticamente
basándose en reglas configuradas (prompt SÍ/NO + IA).
"""
import os
import logging
from datetime import datetime, timedelta
from openai import OpenAI

logger = logging.getLogger(__name__)

client = None
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)
else:
    logger.warning("OPENAI_API_KEY not set - auto tagger disabled")


def run_auto_tagger(app_context):
    """Job principal — corre periódicamente desde el scheduler."""
    if not client:
        logger.warning("⚠️ [AUTO_TAGGER] OpenAI client not initialized - skipping")
        return

    with app_context:
        from models import db, Message, Contact, AutoTagRule, AutoTagLog, FollowUpSequence, FollowUpEnrollment, ChatbotConfig, Tag

        try:
            # Chequear si el auto tagger está habilitado
            if ChatbotConfig.get('auto_tagger_enabled', 'true') != 'true':
                logger.info("⏸️ [AUTO_TAGGER] Deshabilitado — saltando")
                return

            rules = AutoTagRule.query.filter_by(is_active=True).all()
            if not rules:
                return

            logger.info(f"🏷️ [AUTO_TAGGER] {len(rules)} regla(s) activa(s)")

            for rule in rules:
                cutoff = datetime.utcnow() - timedelta(minutes=rule.inactivity_minutes)

                # Solo considerar mensajes recibidos DESPUÉS de la última activación de la regla
                start_date = rule.activated_at or datetime.utcnow()
                phones_q = db.session.query(Message.phone_number).filter(
                    Message.phone_number.notin_(['unknown', 'outbound', '']),
                    Message.timestamp >= start_date,
                    Message.direction == 'inbound'
                ).distinct().all()

                for (phone,) in phones_q:
                    last_msg = Message.query.filter(
                        Message.phone_number == phone
                    ).order_by(Message.timestamp.desc()).first()

                    if not last_msg or last_msg.timestamp >= cutoff:
                        continue

                    contact = Contact.query.filter_by(phone_number=phone).first()
                    if not contact:
                        continue

                    # ¿Ya tiene esta etiqueta?
                    if any(t.id == rule.tag_id for t in contact.tags):
                        continue

                    # ¿Ya fue analizado para esta regla en esta sesión?
                    cache_key = f"auto_tag_{rule.id}_{phone}_{last_msg.id}"
                    already_analyzed = ChatbotConfig.query.filter_by(key=cache_key).first()
                    if already_analyzed:
                        continue

                    # Obtener últimos 20 mensajes
                    messages = Message.query.filter(
                        Message.phone_number == phone
                    ).order_by(Message.timestamp.desc()).limit(20).all()
                    messages = list(reversed(messages))

                    # Analizar con IA
                    try:
                        result = analyze_conversation(messages, rule.prompt_condition)
                    except Exception as e:
                        logger.error(f"❌ [AUTO_TAGGER] Error IA para {phone}: {e}")
                        _write_log(db, AutoTagLog, rule, contact, phone, 'error')
                        continue

                    # Marcar como analizado
                    db.session.add(ChatbotConfig(key=cache_key, value=str(result)))
                    try:
                        db.session.commit()
                    except Exception:
                        db.session.rollback()

                    if result:
                        tag = Tag.query.get(rule.tag_id)
                        if tag and tag not in contact.tags:
                            contact.tags.append(tag)
                            db.session.commit()
                            logger.info(f"🏷️ [AUTO_TAGGER] Tag '{tag.name}' asignado a {phone}")
                            _write_log(db, AutoTagLog, rule, contact, phone, 'tagged')
                            enroll_in_sequences(db, contact, rule.tag_id, FollowUpSequence, FollowUpEnrollment)
                    else:
                        _write_log(db, AutoTagLog, rule, contact, phone, 'skipped')

        except Exception as e:
            logger.error(f"❌ [AUTO_TAGGER] Error: {e}", exc_info=True)


def _write_log(db, AutoTagLog, rule, contact, phone, result):
    """Guarda un registro de análisis en la BD."""
    try:
        log = AutoTagLog(
            rule_id=rule.id,
            contact_id=contact.id if contact else None,
            phone_number=phone,
            tag_id=rule.tag_id,
            result=result
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning(f"No se pudo guardar log de auto-tagger: {e}")


def analyze_conversation(messages, prompt_condition):
    """Analiza la conversación y retorna True/False."""
    conv_lines = []
    for msg in messages:
        role = "Usuario" if msg.direction == "inbound" else "Bot"
        content = msg.content or f"[{msg.message_type}]"
        conv_lines.append(f"[{role}]: {content[:300]}")

    conversation_text = "\n".join(conv_lines)

    escalated = any(
        msg.direction == 'outbound' and msg.content and '[ESCALAR_HUMANO]' in msg.content
        for msg in messages
    )
    escalation_note = "\n\n[NOTA]: En esta conversación el cliente fue derivado a un humano." if escalated else ""

    prompt = f"""Analizá la siguiente conversación de WhatsApp y respondé la pregunta con una sola palabra: SÍ o NO.

CONVERSACIÓN:
{conversation_text}{escalation_note}

PREGUNTA: {prompt_condition}

Respondé únicamente con SÍ o NO."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Eres un analizador de conversaciones. Respondés únicamente con SÍ o NO."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1,
        max_tokens=5
    )
    answer = response.choices[0].message.content.strip().upper()
    return answer.startswith("SÍ") or answer.startswith("SI")


def enroll_in_sequences(db, contact, tag_id, FollowUpSequence, FollowUpEnrollment):
    """Enrola al contacto en todas las secuencias activas que usen el tag dado."""
    sequences = FollowUpSequence.query.filter_by(tag_id=tag_id, is_active=True).all()
    for seq in sequences:
        if not seq.steps:
            continue

        existing = FollowUpEnrollment.query.filter_by(
            contact_id=contact.id,
            sequence_id=seq.id
        ).first()
        if existing:
            continue

        first_step = seq.steps[0]
        now = datetime.utcnow()
        if (first_step.schedule_type or 'delay') == 'fixed_time' and first_step.scheduled_weekday is not None and first_step.scheduled_time:
            from followup_sender import _next_fixed_time
            next_send_at = _next_fixed_time(now, first_step.scheduled_weekday, first_step.scheduled_time)
        else:
            next_send_at = now + timedelta(hours=first_step.delay_hours)

        enrollment = FollowUpEnrollment(
            contact_id=contact.id,
            sequence_id=seq.id,
            current_step=1,
            status='pending',
            next_send_at=next_send_at
        )
        db.session.add(enrollment)
        try:
            db.session.commit()
            logger.info(f"📋 [AUTO_TAGGER] {contact.phone_number} enrollado en '{seq.name}' (paso 1 → {next_send_at})")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error enrollando contacto: {e}")
