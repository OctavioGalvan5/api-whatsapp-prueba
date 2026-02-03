import os
import logging
from sqlalchemy import text
from app import app, db

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_constraint():
    with app.app_context():
        try:
            logger.info("Iniciando corrección de constraint UNIQUE en PostgreSQL...")
            
            # 1. Eliminar la constraint unique explícita si existe
            # El error reportado fue: violates unique constraint "uq_phone_number"
            logger.info("Intentando eliminar constraint 'uq_phone_number'...")
            try:
                db.session.execute(text("ALTER TABLE whatsapp_contacts DROP CONSTRAINT IF EXISTS uq_phone_number"))
                logger.info("Constraint 'uq_phone_number' eliminada (si existía).")
            except Exception as e:
                logger.warning(f"Advertencia al borrar constraint uq_phone_number: {e}")

            # 2. También intentamos borrar el índice unique implícito que crea SQLAlchemy a veces
            # El nombre por defecto suele ser whatsapp_contacts_phone_number_key o similar
            # Pero vamos a verificar si hay otros índices únicos
            
            logger.info("Intentando eliminar constraint 'whatsapp_contacts_phone_number_key' (nombre default PG)...")
            try:
                db.session.execute(text("ALTER TABLE whatsapp_contacts DROP CONSTRAINT IF EXISTS whatsapp_contacts_phone_number_key"))
                logger.info("Constraint 'whatsapp_contacts_phone_number_key' eliminada.")
            except Exception as e:
                logger.warning(f"Advertencia al borrar key default: {e}")

            # 3. Recrear el índice normal (NO UNICO) para performance
            logger.info("Recreando índice normal 'ix_contacts_phone'...")
            try:
                db.session.execute(text("DROP INDEX IF EXISTS ix_contacts_phone")) # Borrar viejo
                db.session.execute(text("DROP INDEX IF EXISTS ix_whatsapp_contacts_phone_number")) # Borrar posible nombre autogenerado
                
                db.session.execute(text("CREATE INDEX ix_contacts_phone ON whatsapp_contacts (phone_number)"))
                logger.info("Índice 'ix_contacts_phone' creado exitosamente.")
            except Exception as e:
                logger.error(f"Error gestionando índices: {e}")
                
            db.session.commit()
            logger.info("✅ Corrección completada exitosamente.")
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"❌ Error crítico durante la migración: {e}")

if __name__ == "__main__":
    fix_constraint()
