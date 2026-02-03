from app import app, db, Contact
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_duplicate():
    with app.app_context():
        try:
            phone = "5491100000000"
            logger.info(f"Probando insertar duplicados para {phone}...")
            
            # Limpiar prueba anterior
            db.session.query(Contact).filter_by(phone_number=phone).delete()
            db.session.commit()
            
            # 1. Insertar primer contacto
            c1 = Contact(phone_number=phone, name="Test 1")
            db.session.add(c1)
            db.session.commit()
            logger.info(f"✅ Primer contacto insertado: ID {c1.id}")
            
            # 2. Insertar segundo contacto con MISMO teléfono
            c2 = Contact(phone_number=phone, name="Test 2")
            db.session.add(c2)
            db.session.commit()
            logger.info(f"✅ Segundo contacto insertado: ID {c2.id}")
            
            if c1.id != c2.id:
                logger.info("🎉 ÉXITO: Se permitieron duplicados correctamente.")
            else:
                logger.error("❌ ERROR: Los IDs son iguales (no debería pasar).")

        except Exception as e:
            db.session.rollback()
            logger.error(f"❌ FALLÓ VERIFICACIÓN: {e}")

if __name__ == "__main__":
    verify_duplicate()
