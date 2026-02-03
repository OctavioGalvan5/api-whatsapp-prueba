"""
Script de verificación: Crear contactos duplicados por teléfono pero distinto ID.
"""
from app import app, db, Contact
import random

def verify():
    with app.app_context():
        # Generar un teléfono aleatorio para probar
        phone = f"54911{random.randint(10000000, 99999999)}"
        id_a = f"TEST-A-{random.randint(1000, 9999)}"
        id_b = f"TEST-B-{random.randint(1000, 9999)}"
        
        print(f"Probando con Teléfono: {phone}")
        print(f"ID A: {id_a}")
        print(f"ID B: {id_b}")
        
        # 1. Crear Contacto A
        c1 = Contact(phone_number=phone, contact_id=id_a, name="Test User A")
        db.session.add(c1)
        db.session.commit()
        print(f"✓ Contacto A creado: ID={c1.id}")
        
        # 2. Crear Contacto B (mismo teléfono, distinto ID)
        try:
            c2 = Contact(phone_number=phone, contact_id=id_b, name="Test User B")
            db.session.add(c2)
            db.session.commit()
            print(f"✓ Contacto B creado: ID={c2.id}")
            
            # Verificar en DB
            count = Contact.query.filter_by(phone_number=phone).count()
            if count == 2:
                print("✓ ÉXITO: Se encontraron 2 contactos con el mismo número.")
            else:
                print(f"✗ FALLO: Se encontraron {count} contactos (se esperaban 2).")
                
        except Exception as e:
            print(f"✗ FALLO: Error al crear segundo contacto: {e}")
            
if __name__ == "__main__":
    verify()
