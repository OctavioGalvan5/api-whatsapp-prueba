"""
Script de migración para PostgreSQL: Permitir teléfonos duplicados.
Elimina el constraint UNIQUE del campo phone_number en whatsapp_contacts.

Ejecutar con: python migrate_pg_phone_unique.py
"""
from app import app, db
from sqlalchemy import text

def check_constraint_exists(constraint_name):
    """Verificar si un constraint existe."""
    result = db.session.execute(text(f"""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE constraint_name = '{constraint_name}'
        );
    """))
    return result.scalar()

def migrate_pg():
    with app.app_context():
        print("=" * 60)
        print("MIGRACIÓN PostgreSQL: Remover UNIQUE de Teléfono")
        print("=" * 60)

        try:
            print("\n[1/1] Removiendo constraint UNIQUE de phone_number...")
            
            # Nombre del constraint creado por migrate_pg_contact_id.py
            constraint_name = 'whatsapp_contacts_phone_number_key'
            
            if check_constraint_exists(constraint_name):
                print(f"  → Constraint '{constraint_name}' encontrado. Eliminando...")
                
                db.session.execute(text(f"""
                    ALTER TABLE whatsapp_contacts
                    DROP CONSTRAINT {constraint_name};
                """))
                db.session.commit()
                print("  ✓ Constraint eliminado exitosamente")
            else:
                print(f"  ✓ El constraint '{constraint_name}' no existe (o tiene otro nombre)")
                
                # Intentar buscar otros constraints unique en phone_number
                print("  → Buscando otros constraints unique posibles...")
                # Consulta para encontrar constraints unique en la columna phone_number
                result = db.session.execute(text("""
                    SELECT con.conname
                    FROM pg_constraint con
                    JOIN pg_class rel ON rel.oid = con.conrelid
                    JOIN pg_namespace nsp ON nsp.oid = connamespace
                    JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = ANY(con.conkey)
                    WHERE rel.relname = 'whatsapp_contacts'
                    AND att.attname = 'phone_number'
                    AND con.contype = 'u';
                """))
                rows = result.fetchall()
                for row in rows:
                    c_name = row[0]
                    print(f"  → Encontrado constraint adicional: {c_name}. Eliminando...")
                    db.session.execute(text(f"""
                        ALTER TABLE whatsapp_contacts
                        DROP CONSTRAINT {c_name};
                    """))
                
                if rows:
                    db.session.commit()
                    print(f"  ✓ {len(rows)} constraints adicionales eliminados")
                else:
                    print("  ✓ No se encontraron otros constraints unique")

            # MIGRACIÓN COMPLETADA
            print("\n" + "=" * 60)
            print("✅ MIGRACIÓN COMPLETADA EXITOSAMENTE")
            print("=" * 60)

        except Exception as e:
            db.session.rollback()
            print(f"\n❌ ERROR EN MIGRACIÓN: {e}")
            import traceback
            traceback.print_exc()
            return False

        return True

if __name__ == "__main__":
    migrate_pg()
