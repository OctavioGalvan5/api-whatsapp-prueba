"""
Follow-up Sender Service
Procesa enrollments pendientes y envía templates de WhatsApp
en los tiempos configurados.
"""
import logging
from datetime import datetime, timedelta
import pytz

logger = logging.getLogger(__name__)

TZ_AR = pytz.timezone('America/Argentina/Buenos_Aires')


def _next_fixed_time(now_utc, weekday, time_str):
    """
    Dado el momento actual (UTC), retorna el próximo datetime UTC en que
    caiga el día de la semana `weekday` (0=Lunes…6=Domingo) a la hora `time_str` ("HH:MM")
    en zona horaria Argentina.
    Siempre es en el futuro (mínimo 1 minuto adelante).
    """
    try:
        h, m = map(int, time_str.split(':'))
    except Exception:
        h, m = 9, 0

    now_ar = now_utc.replace(tzinfo=pytz.utc).astimezone(TZ_AR)
    # Días hasta el próximo `weekday`
    days_ahead = (weekday - now_ar.weekday()) % 7
    candidate_ar = (now_ar + timedelta(days=days_ahead)).replace(hour=h, minute=m, second=0, microsecond=0)

    # Si el candidate es en el pasado o demasiado cerca, ir a la semana siguiente
    if candidate_ar <= now_ar + timedelta(minutes=1):
        candidate_ar += timedelta(weeks=1)

    return candidate_ar.astimezone(pytz.utc).replace(tzinfo=None)


def _next_window_start(now_utc, window_start_str, window_end_str, weekdays=None):
    """
    Retorna el próximo datetime UTC en que se puede enviar según la ventana
    horaria y los días permitidos (en hora Argentina).
    - window_start_str / window_end_str: "HH:MM" o None (sin restricción de hora)
    - weekdays: lista de ints 0-6 (0=Lunes) o None (todos los días)
    Retorna None si ahora mismo está dentro de la ventana permitida.
    """
    now_ar = now_utc.replace(tzinfo=pytz.utc).astimezone(TZ_AR)

    # Parsear horarios (None = sin restricción)
    wstart_h = wstart_m = None
    wend_h = wend_m = None
    if window_start_str and window_end_str:
        try:
            wstart_h, wstart_m = map(int, window_start_str.split(':'))
            wend_h, wend_m = map(int, window_end_str.split(':'))
        except Exception:
            pass

    # Verificar si el día actual está permitido y la hora está dentro del rango
    def is_allowed(dt_ar):
        if weekdays and dt_ar.weekday() not in weekdays:
            return False
        if wstart_h is not None:
            cur = dt_ar.hour * 60 + dt_ar.minute
            if not (wstart_h * 60 + wstart_m <= cur < wend_h * 60 + wend_m):
                return False
        return True

    if is_allowed(now_ar):
        return None  # Dentro de la ventana, enviar ahora

    # Buscar el próximo momento permitido (máximo 8 días adelante)
    open_h = wstart_h if wstart_h is not None else 0
    open_m = wstart_m if wstart_m is not None else 0

    candidate_ar = now_ar.replace(hour=open_h, minute=open_m, second=0, microsecond=0)
    # Si la hora de apertura de hoy ya pasó, ir al día siguiente
    if candidate_ar <= now_ar:
        candidate_ar += timedelta(days=1)

    for _ in range(8):
        if not weekdays or candidate_ar.weekday() in weekdays:
            return candidate_ar.astimezone(pytz.utc).replace(tzinfo=None)
        candidate_ar += timedelta(days=1)

    return None  # Fallback: no bloquear si no encontró día válido


def run_followup_sender(app_context):
    """Job principal — corre cada minuto desde el scheduler."""
    with app_context:
        from models import db, FollowUpEnrollment, FollowUpStep, FollowUpSequence, Contact
        from whatsapp_service import whatsapp_api

        try:
            now = datetime.utcnow()

            pending = FollowUpEnrollment.query.filter(
                FollowUpEnrollment.status == 'pending',
                FollowUpEnrollment.next_send_at <= now
            ).all()

            if not pending:
                return

            logger.info(f"📨 [FOLLOWUP] {len(pending)} enrollment(s) para procesar")

            for enrollment in pending:
                try:
                    _process_enrollment(db, enrollment, whatsapp_api, now)
                except Exception as e:
                    logger.error(f"❌ [FOLLOWUP] Error procesando enrollment {enrollment.id}: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"❌ [FOLLOWUP] Error general: {e}", exc_info=True)


def _resolve_components(template_params, contact):
    """
    Convierte el mapeo guardado {"body-1": "first_name", "header-1": "name"}
    en el formato de components que espera la API de WhatsApp:
    [
      {"type": "header", "parameters": [{"type": "text", "text": "valor"}]},
      {"type": "body",   "parameters": [{"type": "text", "text": "valor"}, ...]}
    ]
    """
    if not template_params:
        return None

    # Resolver campo del contacto a su valor real
    def get_value(field):
        mapping = {
            'first_name':    contact.first_name or contact.name or '',
            'last_name':     contact.last_name or '',
            'name':          contact.name or f"{contact.first_name or ''} {contact.last_name or ''}".strip(),
            'phone_number':  contact.phone_number or '',
            'notes':         contact.notes or '',
            'custom_field_1': contact.custom_field_1 or '',
            'custom_field_2': contact.custom_field_2 or '',
            'custom_field_3': contact.custom_field_3 or '',
            'custom_field_4': contact.custom_field_4 or '',
            'custom_field_5': contact.custom_field_5 or '',
            'custom_field_6': contact.custom_field_6 or '',
            'custom_field_7': contact.custom_field_7 or '',
        }
        return mapping.get(field, '')

    # Agrupar por componente y ordenar por índice
    grouped = {}  # {'body': [(1, val), (2, val)], 'header': [(1, val)]}
    for key, field in template_params.items():
        # key es "body-1", "header-1", etc.
        parts = key.split('-', 1)
        if len(parts) != 2:
            continue
        comp_type, idx = parts[0], parts[1]
        try:
            idx_int = int(idx)
        except ValueError:
            idx_int = 1
        grouped.setdefault(comp_type, []).append((idx_int, get_value(field)))

    if not grouped:
        return None

    components = []
    # Header primero, luego body
    for comp_type in ['header', 'body']:
        if comp_type not in grouped:
            continue
        params_sorted = sorted(grouped[comp_type], key=lambda x: x[0])
        components.append({
            'type': comp_type,
            'parameters': [{'type': 'text', 'text': val} for _, val in params_sorted]
        })

    return components if components else None


def _process_enrollment(db, enrollment, whatsapp_api, now):
    """Procesa un enrollment individual: envía el mensaje del paso actual."""
    from models import FollowUpStep, FollowUpSequence

    sequence = enrollment.sequence
    if not sequence or not sequence.is_active:
        enrollment.status = 'cancelled'
        enrollment.cancelled_at = now
        db.session.commit()
        return

    # Chequear ventana horaria de la secuencia
    next_open = _next_window_start(
        now,
        sequence.send_window_start,
        sequence.send_window_end,
        sequence.send_weekdays
    )
    if next_open is not None:
        enrollment.next_send_at = next_open
        db.session.commit()
        logger.info(f"🕐 [FOLLOWUP] Fuera de ventana — reprogramado para {next_open} UTC")
        return

    contact = enrollment.contact
    if not contact:
        enrollment.status = 'cancelled'
        db.session.commit()
        return

    step = FollowUpStep.query.filter_by(
        sequence_id=enrollment.sequence_id,
        order=enrollment.current_step
    ).first()

    if not step:
        enrollment.status = 'finished'
        db.session.commit()
        logger.info(f"✅ [FOLLOWUP] Secuencia '{sequence.name}' finalizada para {contact.phone_number}")
        return

    # Resolver variables del template con datos reales del contacto
    components = _resolve_components(step.template_params, contact)

    result = whatsapp_api.send_template_message(
        to_phone=contact.phone_number,
        template_name=step.template_name,
        language_code=step.template_language or 'es_AR',
        components=components
    )

    if result and result.get('messages'):
        logger.info(f"✅ [FOLLOWUP] Paso {step.order} enviado a {contact.phone_number} (secuencia: {sequence.name})")
    else:
        logger.warning(f"⚠️ [FOLLOWUP] Fallo enviando paso {step.order} a {contact.phone_number}: {result}")

    # Si el paso tiene remove_tag_on_execute, quitar la etiqueta y finalizar
    if step.remove_tag_on_execute:
        tag = sequence.tag
        if tag and tag in contact.tags:
            contact.tags.remove(tag)
            logger.info(f"🏷️ [FOLLOWUP] Etiqueta '{tag.name}' quitada de {contact.phone_number}")
        enrollment.status = 'finished'
        logger.info(f"✅ [FOLLOWUP] Secuencia '{sequence.name}' finalizada (remove_tag) para {contact.phone_number}")
        db.session.commit()
        return

    # Buscar siguiente paso
    next_step = FollowUpStep.query.filter_by(
        sequence_id=enrollment.sequence_id,
        order=enrollment.current_step + 1
    ).first()

    if next_step:
        enrollment.current_step += 1
        if (next_step.schedule_type or 'delay') == 'fixed_time' and next_step.scheduled_weekday is not None and next_step.scheduled_time:
            enrollment.next_send_at = _next_fixed_time(now, next_step.scheduled_weekday, next_step.scheduled_time)
        else:
            enrollment.next_send_at = now + timedelta(hours=next_step.delay_hours)
        logger.info(f"📅 [FOLLOWUP] Próximo paso ({next_step.order}) programado para {enrollment.next_send_at}")
    else:
        enrollment.status = 'finished'
        logger.info(f"✅ [FOLLOWUP] Secuencia completa para {contact.phone_number}")

    db.session.commit()


def cancel_enrollment_on_reply(phone_number, app_context=None):
    """
    Cancela todos los enrollments activos de un contacto cuando responde.
    Se llama desde event_handlers al recibir un mensaje inbound.
    """
    def _cancel():
        from models import db, Contact, FollowUpEnrollment
        now = datetime.utcnow()

        contact = Contact.query.filter_by(phone_number=phone_number).first()
        if not contact:
            return

        active = FollowUpEnrollment.query.filter_by(
            contact_id=contact.id,
            status='pending'
        ).all()

        if active:
            for e in active:
                e.status = 'cancelled'
                e.cancelled_at = now
            db.session.commit()
            logger.info(f"🛑 [FOLLOWUP] {len(active)} enrollment(s) cancelado(s) para {phone_number} (respondió)")

    if app_context:
        with app_context:
            _cancel()
    else:
        _cancel()
