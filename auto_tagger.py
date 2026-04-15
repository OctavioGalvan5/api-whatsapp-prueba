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
            if ChatbotConfig.get('auto_tagger_enabled', 'true') != 'true':
                logger.info("⏸️ [AUTO_TAGGER] Deshabilitado — saltando")
                return

            rules = AutoTagRule.query.filter_by(is_active=True).all()
            if not rules:
                return

            logger.info(f"🏷️ [AUTO_TAGGER] {len(rules)} regla(s) activa(s)")
            now = datetime.utcnow()

            # Recolectar todos los teléfonos candidatos para cualquier regla
            # Si activated_at es None usamos epoch (considera todos los mensajes)
            _epoch = datetime(2000, 1, 1)
            earliest_start = min(r.activated_at or _epoch for r in rules)

            phones_q = db.session.query(Message.phone_number).filter(
                Message.phone_number.notin_(['unknown', 'outbound', '']),
                Message.timestamp >= earliest_start,
                Message.direction == 'inbound'
            ).distinct().all()

            logger.debug(f"[AUTO_TAGGER] {len(phones_q)} teléfono(s) candidatos (desde {earliest_start})")

            for (phone,) in phones_q:
                last_msg = Message.query.filter(
                    Message.phone_number == phone
                ).order_by(Message.timestamp.desc()).first()

                if not last_msg:
                    continue

                contact = Contact.query.filter_by(phone_number=phone).first()
                if not contact:
                    continue

                # Filtrar solo las reglas que aplican a este contacto en este momento
                pending_rules = []
                for rule in rules:
                    cutoff = now - timedelta(minutes=rule.inactivity_minutes)
                    if last_msg.timestamp >= cutoff:
                        logger.debug(f"[AUTO_TAGGER] {phone} regla={rule.id}: aún activo (último msg {last_msg.timestamp} >= cutoff {cutoff})")
                        continue
                    if rule.activated_at and last_msg.timestamp < rule.activated_at:
                        logger.debug(f"[AUTO_TAGGER] {phone} regla={rule.id}: fuera de rango")
                        continue
                    if any(t.id == rule.tag_id for t in contact.tags):
                        logger.debug(f"[AUTO_TAGGER] {phone} regla={rule.id}: ya tiene la etiqueta")
                        continue
                    cache_key = f"auto_tag_{rule.id}_{phone}_{last_msg.id}"
                    if ChatbotConfig.query.filter_by(key=cache_key).first():
                        logger.debug(f"[AUTO_TAGGER] {phone} regla={rule.id}: ya analizado (cache)")
                        continue
                    pending_rules.append(rule)

                if not pending_rules:
                    logger.debug(f"[AUTO_TAGGER] {phone}: sin reglas pendientes, saltando")
                    continue

                # Obtener los últimos 20 mensajes una sola vez
                messages = Message.query.filter(
                    Message.phone_number == phone
                ).order_by(Message.timestamp.desc()).limit(20).all()
                messages = list(reversed(messages))

                # UNA sola llamada a la IA con todas las condiciones pendientes
                conditions = {str(rule.id): rule.prompt_condition for rule in pending_rules}
                try:
                    results = analyze_conversation_batch(messages, conditions)
                except Exception as e:
                    logger.error(f"❌ [AUTO_TAGGER] Error IA para {phone}: {e}")
                    for rule in pending_rules:
                        _write_log(db, AutoTagLog, rule, contact, phone, 'error')
                    continue

                for rule in pending_rules:
                    rule_result = results.get(str(rule.id), False)

                    # Marcar como analizado
                    cache_key = f"auto_tag_{rule.id}_{phone}_{last_msg.id}"
                    db.session.add(ChatbotConfig(key=cache_key, value=str(rule_result)))
                    try:
                        db.session.commit()
                    except Exception:
                        db.session.rollback()

                    if rule_result:
                        tag = Tag.query.get(rule.tag_id)
                        if tag and tag not in contact.tags:
                            contact.tags.append(tag)
                            db.session.commit()
                            logger.info(f"🏷️ [AUTO_TAGGER] Tag '{tag.name}' asignado a {phone}")
                            _write_log(db, AutoTagLog, rule, contact, phone, 'tagged')
                            enroll_in_sequences(db, contact, rule.tag_id, FollowUpSequence, FollowUpEnrollment)
                    else:
                        _write_log(db, AutoTagLog, rule, contact, phone, 'skipped')

                logger.info(f"🏷️ [AUTO_TAGGER] {phone}: {len(pending_rules)} regla(s) evaluadas en 1 llamada")

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


def analyze_conversation_batch(messages, conditions):
    """
    Analiza la conversación contra múltiples condiciones en una sola llamada.
    conditions: dict {rule_id_str: prompt_condition}
    Retorna: dict {rule_id_str: True/False}
    """
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

    conditions_text = "\n".join(
        f'- "{rule_id}": {condition}' for rule_id, condition in conditions.items()
    )

    prompt = f"""Analizá la siguiente conversación de WhatsApp y respondé cada pregunta con SÍ o NO.

CONVERSACIÓN:
{conversation_text}{escalation_note}

PREGUNTAS (respondé cada una con SÍ o NO):
{conditions_text}

Respondé ÚNICAMENTE con un JSON válido con el mismo ID como clave y "SI" o "NO" como valor. Ejemplo:
{{"123": "SI", "456": "NO"}}"""

    response = client.chat.completions.create(
        model="gpt-5-nano",
        messages=[
            {"role": "system", "content": "Eres un analizador de conversaciones. Respondés únicamente con un JSON de SÍ/NO por cada pregunta."},
            {"role": "user", "content": prompt}
        ],
        max_completion_tokens=200
    )

    msg = response.choices[0].message
    logger.info(f"[AUTO_TAGGER] finish_reason={response.choices[0].finish_reason} content={repr(msg.content)} refusal={repr(getattr(msg,'refusal',None))}")
    raw = (msg.content or "").strip()
    try:
        import json
        # Extraer JSON si viene envuelto en markdown ```json ... ```
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        parsed = json.loads(raw)
        return {k: (str(v).upper().startswith("S")) for k, v in parsed.items()}
    except Exception:
        logger.warning(f"[AUTO_TAGGER] No se pudo parsear respuesta batch: {repr(raw)}")
        return {k: False for k in conditions}


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
            if existing.status == 'pending':
                continue  # Ya tiene un enrollment activo, no duplicar
            # Eliminar enrollment finalizado/cancelado para permitir re-enrollment
            db.session.delete(existing)
            try:
                db.session.flush()
            except Exception:
                db.session.rollback()
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
