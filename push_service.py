import json
import logging
from pywebpush import webpush, WebPushException
from config import Config

logger = logging.getLogger(__name__)


def send_push_to_all(title, body, url="/dashboard"):
    """Envía una notificación Web Push a todas las suscripciones guardadas."""
    from models import PushSubscription
    from app import app

    if not Config.VAPID_PRIVATE_KEY or not Config.VAPID_PUBLIC_KEY:
        logger.warning("VAPID keys no configuradas, no se puede enviar push.")
        return

    payload = json.dumps({"title": title, "body": body, "url": url})
    vapid_claims = {"sub": f"mailto:{Config.VAPID_EMAIL}"}

    with app.app_context():
        subs = PushSubscription.query.all()
        dead = []
        for sub in subs:
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                    },
                    data=payload,
                    vapid_private_key=Config.VAPID_PRIVATE_KEY,
                    vapid_claims=vapid_claims,
                )
            except WebPushException as e:
                status = e.response.status_code if e.response is not None else 0
                if status in (404, 410):
                    # Suscripción expirada o inválida — limpiar
                    dead.append(sub.id)
                else:
                    logger.warning(f"Push fallido para sub {sub.id}: {e}")
            except Exception as e:
                logger.warning(f"Push error sub {sub.id}: {e}")

        if dead:
            from models import db
            PushSubscription.query.filter(PushSubscription.id.in_(dead)).delete(synchronize_session=False)
            db.session.commit()
