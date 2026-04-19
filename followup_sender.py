"""
Follow-up Sender Service
Procesa enrollments pendientes y envía templates de WhatsApp
en los tiempos configurados.
"""
import logging
import threading
from datetime import datetime, timedelta
import pytz

logger = logging.getLogger(__name__)

TZ_AR = pytz.timezone('America/Argentina/Buenos_Aires')

_running_lock = threading.Lock()


def _maybe_add_seguimiento_enviado(db, contact, sequence, ContactTagHistory):
    """Si la secuencia tiene add_tag_on_complete, agrega la etiqueta 'Seguimiento enviado'."""
    logger.info(f"🔎 [FOLLOWUP] _maybe_add_seguimiento_enviado → secuencia='{sequence.name}' add_tag_on_complete={getattr(sequence, 'add_tag_on_complete', 'ATTR_MISSING')} contacto={contact.phone_number}")
    if not getattr(sequence, 'add_tag_on_complete', False):
        logger.info(f"   ↳ add_tag_on_complete es False/None — no se agrega etiqueta")
        return
    from models import Tag
    tag = Tag.query.filter_by(name='Seguimiento enviado').first()
    if not tag:
        logger.info(f"   ↳ Etiqueta 'Seguimiento enviado' no existe — creando...")
        tag = Tag(name='Seguimiento enviado', color='blue', is_active=True)
        db.session.add(tag)
        db.session.flush()
    else:
        logger.info(f"   ↳ Etiqueta 'Seguimiento enviado' existe (id={tag.id})")
    if tag not in contact.tags:
        contact.tags.append(tag)
        db.session.add(ContactTagHistory(
            contact_id=contact.id,
            tag_id=tag.id,
            tag_name_snapshot=tag.name,
            action='added',
            source='system',
            created_by='followup_sender'
        ))
        logger.info(f"🏷️ [FOLLOWUP] Etiqueta 'Seguimiento enviado' agregada a {contact.phone_number}")
    else:
        logger.info(f"   ↳ Contacto ya tiene la etiqueta 'Seguimiento enviado' — nada que hacer")


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
    if not _running_lock.acquire(blocking=False):
        logger.info("⏭️ [FOLLOWUP] Ya hay un ciclo corriendo — saltando")
        return
    try:
        _run_followup_sender_inner(app_context)
    finally:
        _running_lock.release()


def _run_followup_sender_inner(app_context):
    with app_context:
        from models import db, FollowUpEnrollment, FollowUpStep, FollowUpSequence, Contact
        from whatsapp_service import whatsapp_api

        try:
            now = datetime.utcnow()

            pending = FollowUpEnrollment.query.filter(
                FollowUpEnrollment.status == 'pending',
                FollowUpEnrollment.next_send_at <= now
            ).with_for_update(skip_locked=True).all()

            total_pending = FollowUpEnrollment.query.filter_by(status='pending').count()
            logger.info(f"🔍 [FOLLOWUP] Ciclo — {len(pending)} listos para enviar / {total_pending} pendientes en total")

            if not pending:
                return

            logger.info(f"📨 [FOLLOWUP] {len(pending)} enrollment(s) para procesar")

            for enrollment in pending:
                try:
                    _process_enrollment(db, enrollment, whatsapp_api, now)
                except Exception as e:
                    logger.error(f"❌ [FOLLOWUP] Error procesando enrollment {enrollment.id}: {e}", exc_info=True)
                    # Evitar loop infinito: si crashea, posponerlo 10 minutos
                    try:
                        enrollment.next_send_at = now + timedelta(minutes=10)
                        db.session.commit()
                    except:
                        db.session.rollback()

        except Exception as e:
            logger.error(f"❌ [FOLLOWUP] Error general: {e}", exc_info=True)



def _resolve_components(template_params, contact):
    """
    Convierte el mapeo guardado {"body-1": "first_name", "header-1": "name"}
    en el formato de components que espera la API de WhatsApp.
    """
    if not template_params:
        return None

    if isinstance(template_params, str):
        import json
        try:
            template_params = json.loads(template_params)
        except Exception:
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
    from models import db, FollowUpStep, FollowUpSequence

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
        from models import ContactTagHistory
        contact = enrollment.contact
        _maybe_add_seguimiento_enviado(db, contact, sequence, ContactTagHistory)
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

    logger.info(f"📬 [FOLLOWUP] Resultado envío paso {step.order} → {contact.phone_number}: {result}")
    sent_ok = result and (result.get('messages') or result.get('message_id') or result.get('success'))
    if sent_ok:
        logger.info(f"📤 =============================================")
        logger.info(f"📤 MENSAJE DE SEGUIMIENTO ENVIADO")
        logger.info(f"📤   Contacto  : {contact.name or contact.phone_number} ({contact.phone_number})")
        logger.info(f"📤   Secuencia : {sequence.name}")
        logger.info(f"📤   Paso      : {step.order} — template '{step.template_name}'")
        logger.info(f"📤 =============================================")
        # Guardar en DB para que aparezca en el dashboard
        try:
            from event_handlers import save_message
            from whatsapp_service import whatsapp_api as _wa

            # Intentar obtener el contenido real del template
            content = f"[Template: {step.template_name}]"
            try:
                tpl_data = _wa.get_templates()
                tpl = next((t for t in tpl_data.get('templates', []) if t['name'] == step.template_name), None)
                if tpl:
                    body_comp = next((c for c in tpl.get('components', []) if c.get('type', '').upper() == 'BODY'), None)
                    if body_comp:
                        body_text = body_comp.get('text', '')
                        # Reemplazar {{1}}, {{2}}... con los valores resueltos
                        body_params = []
                        for comp in (components or []):
                            if comp.get('type', '').lower() == 'body':
                                body_params = [p.get('text', '') for p in comp.get('parameters', [])]
                                break
                        for i, val in enumerate(body_params, 1):
                            body_text = body_text.replace(f'{{{{{i}}}}}', str(val))
                        content = body_text
            except Exception:
                pass  # Fallback al nombre del template

            wa_msg_id = result.get('message_id')
            save_message(
                wa_message_id=wa_msg_id,
                phone_number=contact.phone_number,
                direction='outbound',
                message_type='template',
                content=content,
                wa_name=None
            )
        except Exception as e:
            logger.warning(f"⚠️ [FOLLOWUP] No se pudo guardar mensaje en DB: {e}")
    else:
        logger.warning(f"⚠️ [FOLLOWUP] sent_ok=False — result={result}")

    # Si el paso tiene remove_tag_on_execute, quitar la etiqueta y finalizar
    if step.remove_tag_on_execute:
        from models import ContactTagHistory
        tags_to_remove = sequence.get_trigger_tags()
        
        for tag_to_remove in tags_to_remove:
            if tag_to_remove in contact.tags:
                contact.tags.remove(tag_to_remove)
                db.session.add(ContactTagHistory(
                    contact_id=contact.id,
                    tag_id=tag_to_remove.id,
                    tag_name_snapshot=tag_to_remove.name,
                    action='removed',
                    source='system',
                    created_by='followup_sender'
                ))
                logger.info(f"🏷️ [FOLLOWUP] Etiqueta '{tag_to_remove.name}' quitada de {contact.phone_number}")

        _maybe_add_seguimiento_enviado(db, contact, sequence, ContactTagHistory)
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
        from models import ContactTagHistory
        _maybe_add_seguimiento_enviado(db, contact, sequence, ContactTagHistory)
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
