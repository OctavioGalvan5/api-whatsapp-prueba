"""
Script de migración para PostgreSQL: Agregar ID único a contactos.

Este script migra la base de datos para usar un ID autoincremental como
clave primaria de contactos, en lugar del número de teléfono.

Ejecutar con: python migrate_pg_contact_id.py

IMPORTANTE: El script es idempotente (puede ejecutarse múltiples veces sin problemas).
"""
from app import app, db
from sqlalchemy import text

def check_column_exists(table, column):
    """Verificar si una columna existe en una tabla."""
    result = db.session.execute(text(f"""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = '{table}' AND column_name = '{column}'
        );
    """))
    return result.scalar()

def check_constraint_exists(constraint_name):
    """Verificar si un constraint existe."""
    result = db.session.execute(text(f"""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE constraint_name = '{constraint_name}'
        );
    """))
    return result.scalar()

def get_primary_key_column(table):
    """Obtener la columna que es primary key de una tabla."""
    result = db.session.execute(text(f"""
        SELECT a.attname
        FROM pg_index i
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = '{table}'::regclass AND i.indisprimary;
    """))
    row = result.fetchone()
    return row[0] if row else None

def migrate_pg():
    with app.app_context():
        print("=" * 60)
        print("MIGRACIÓN PostgreSQL: ID único para Contactos")
        print("=" * 60)

        try:
            # ============================================
            # PASO 1: Agregar columna ID a whatsapp_contacts
            # ============================================
            print("\n[1/7] Verificando columna ID en whatsapp_contacts...")

            if not check_column_exists('whatsapp_contacts', 'id'):
                print("  → Creando secuencia y columna ID...")

                # Crear secuencia
                db.session.execute(text("""
                    CREATE SEQUENCE IF NOT EXISTS whatsapp_contacts_id_seq;
                """))

                # Agregar columna ID con valor default de la secuencia
                db.session.execute(text("""
                    ALTER TABLE whatsapp_contacts
                    ADD COLUMN id INTEGER DEFAULT nextval('whatsapp_contacts_id_seq');
                """))

                # Poblar IDs para registros existentes
                db.session.execute(text("""
                    UPDATE whatsapp_contacts
                    SET id = nextval('whatsapp_contacts_id_seq')
                    WHERE id IS NULL;
                """))

                # Hacer NOT NULL
                db.session.execute(text("""
                    ALTER TABLE whatsapp_contacts ALTER COLUMN id SET NOT NULL;
                """))

                db.session.commit()
                print("  ✓ Columna ID creada y poblada")
            else:
                print("  ✓ Columna ID ya existe")

            # ============================================
            # PASO 2: Cambiar Primary Key de contacts
            # ============================================
            print("\n[2/7] Actualizando Primary Key de whatsapp_contacts...")

            current_pk = get_primary_key_column('whatsapp_contacts')

            if current_pk != 'id':
                print(f"  → PK actual: {current_pk}, cambiando a 'id'...")

                # Eliminar PK existente
                db.session.execute(text("""
                    ALTER TABLE whatsapp_contacts DROP CONSTRAINT IF EXISTS whatsapp_contacts_pkey CASCADE;
                """))

                # Crear nueva PK en id
                db.session.execute(text("""
                    ALTER TABLE whatsapp_contacts ADD PRIMARY KEY (id);
                """))

                # Vincular secuencia a la columna
                db.session.execute(text("""
                    ALTER SEQUENCE whatsapp_contacts_id_seq OWNED BY whatsapp_contacts.id;
                """))

                db.session.commit()
                print("  ✓ Primary Key cambiada a 'id'")
            else:
                print("  ✓ Primary Key ya es 'id'")

            # ============================================
            # PASO 3: Agregar columna contact_id (ID externo editable)
            # ============================================
            print("\n[3/8] Verificando columna contact_id en whatsapp_contacts...")

            if not check_column_exists('whatsapp_contacts', 'contact_id'):
                print("  → Creando columna contact_id...")

                db.session.execute(text("""
                    ALTER TABLE whatsapp_contacts
                    ADD COLUMN contact_id VARCHAR(50);
                """))

                # Crear índice único para contact_id (permite NULL)
                db.session.execute(text("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_contact_id
                    ON whatsapp_contacts(contact_id)
                    WHERE contact_id IS NOT NULL;
                """))

                db.session.commit()
                print("  ✓ Columna contact_id creada con índice único")
            else:
                print("  ✓ Columna contact_id ya existe")

            # ============================================
            # PASO 4: Agregar constraint UNIQUE a phone_number
            # ============================================
            print("\n[4/8] Agregando constraint UNIQUE a phone_number...")

            if not check_constraint_exists('whatsapp_contacts_phone_number_key'):
                db.session.execute(text("""
                    ALTER TABLE whatsapp_contacts
                    ADD CONSTRAINT whatsapp_contacts_phone_number_key UNIQUE (phone_number);
                """))
                db.session.commit()
                print("  ✓ Constraint UNIQUE agregado")
            else:
                print("  ✓ Constraint UNIQUE ya existe")

            # ============================================
            # PASO 5: Agregar contact_id a whatsapp_contact_tags
            # ============================================
            print("\n[5/8] Migrando whatsapp_contact_tags...")

            if not check_column_exists('whatsapp_contact_tags', 'contact_id'):
                print("  → Agregando columna contact_id...")

                db.session.execute(text("""
                    ALTER TABLE whatsapp_contact_tags ADD COLUMN contact_id INTEGER;
                """))
                db.session.commit()
                print("  ✓ Columna contact_id agregada")
            else:
                print("  ✓ Columna contact_id ya existe")

            # Poblar contact_id basándose en contact_phone
            if check_column_exists('whatsapp_contact_tags', 'contact_phone'):
                print("  → Poblando contact_id desde contact_phone...")

                result = db.session.execute(text("""
                    UPDATE whatsapp_contact_tags t
                    SET contact_id = c.id
                    FROM whatsapp_contacts c
                    WHERE t.contact_phone = c.phone_number
                    AND t.contact_id IS NULL;
                """))
                db.session.commit()
                print(f"  ✓ {result.rowcount} registros actualizados")

                # Eliminar registros huérfanos
                result = db.session.execute(text("""
                    DELETE FROM whatsapp_contact_tags WHERE contact_id IS NULL;
                """))
                if result.rowcount > 0:
                    print(f"  → Eliminados {result.rowcount} registros huérfanos")
                db.session.commit()

            # ============================================
            # PASO 6: Actualizar PK y FK de contact_tags
            # ============================================
            print("\n[6/8] Actualizando constraints de whatsapp_contact_tags...")

            # Hacer contact_id NOT NULL
            try:
                db.session.execute(text("""
                    ALTER TABLE whatsapp_contact_tags ALTER COLUMN contact_id SET NOT NULL;
                """))
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                if "already" not in str(e).lower():
                    print(f"  Nota: {e}")

            # Eliminar PK antigua si existe
            try:
                db.session.execute(text("""
                    ALTER TABLE whatsapp_contact_tags DROP CONSTRAINT IF EXISTS whatsapp_contact_tags_pkey;
                """))
                db.session.commit()
            except:
                db.session.rollback()

            # Crear nueva PK
            if not check_constraint_exists('whatsapp_contact_tags_pkey'):
                try:
                    db.session.execute(text("""
                        ALTER TABLE whatsapp_contact_tags ADD PRIMARY KEY (contact_id, tag_id);
                    """))
                    db.session.commit()
                    print("  ✓ Nueva Primary Key (contact_id, tag_id) creada")
                except Exception as e:
                    db.session.rollback()
                    if "already exists" in str(e).lower():
                        print("  ✓ Primary Key ya existe")
                    else:
                        print(f"  Nota: {e}")

            # Agregar FK a contacts
            if not check_constraint_exists('fk_contact_tags_contact'):
                try:
                    db.session.execute(text("""
                        ALTER TABLE whatsapp_contact_tags
                        ADD CONSTRAINT fk_contact_tags_contact
                        FOREIGN KEY (contact_id) REFERENCES whatsapp_contacts(id) ON DELETE CASCADE;
                    """))
                    db.session.commit()
                    print("  ✓ Foreign Key a whatsapp_contacts creada")
                except Exception as e:
                    db.session.rollback()
                    if "already exists" in str(e).lower():
                        print("  ✓ Foreign Key ya existe")

            # Eliminar columna contact_phone
            if check_column_exists('whatsapp_contact_tags', 'contact_phone'):
                db.session.execute(text("""
                    ALTER TABLE whatsapp_contact_tags DROP COLUMN contact_phone;
                """))
                db.session.commit()
                print("  ✓ Columna contact_phone eliminada")

            # ============================================
            # PASO 7: Actualizar whatsapp_campaign_logs
            # ============================================
            print("\n[7/8] Actualizando whatsapp_campaign_logs...")

            if not check_column_exists('whatsapp_campaign_logs', 'contact_id'):
                db.session.execute(text("""
                    ALTER TABLE whatsapp_campaign_logs ADD COLUMN contact_id INTEGER;
                """))
                db.session.commit()
                print("  ✓ Columna contact_id agregada")
            else:
                print("  ✓ Columna contact_id ya existe")

            # Poblar contact_id
            result = db.session.execute(text("""
                UPDATE whatsapp_campaign_logs l
                SET contact_id = c.id
                FROM whatsapp_contacts c
                WHERE l.contact_phone = c.phone_number
                AND l.contact_id IS NULL;
            """))
            db.session.commit()
            if result.rowcount > 0:
                print(f"  ✓ {result.rowcount} registros actualizados")

            # Agregar FK a contacts (permite NULL para históricos sin match)
            if not check_constraint_exists('fk_campaign_logs_contact'):
                try:
                    db.session.execute(text("""
                        ALTER TABLE whatsapp_campaign_logs
                        ADD CONSTRAINT fk_campaign_logs_contact
                        FOREIGN KEY (contact_id) REFERENCES whatsapp_contacts(id) ON DELETE SET NULL;
                    """))
                    db.session.commit()
                    print("  ✓ Foreign Key a whatsapp_contacts creada")
                except Exception as e:
                    db.session.rollback()
                    if "already exists" in str(e).lower():
                        print("  ✓ Foreign Key ya existe")
                    else:
                        print(f"  Nota FK: {e}")

            # ============================================
            # PASO 8: Crear índices
            # ============================================
            print("\n[8/8] Creando índices...")

            try:
                db.session.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_contacts_phone ON whatsapp_contacts(phone_number);
                """))
                db.session.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_contact_tags_contact ON whatsapp_contact_tags(contact_id);
                """))
                db.session.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_campaign_logs_contact ON whatsapp_campaign_logs(contact_id);
                """))
                db.session.commit()
                print("  ✓ Índices creados")
            except Exception as e:
                db.session.rollback()
                print(f"  Nota índices: {e}")

            # ============================================
            # VERIFICACIÓN FINAL
            # ============================================
            print("\n" + "=" * 60)
            print("VERIFICACIÓN")
            print("=" * 60)

            # Contar registros
            contacts_count = db.session.execute(text("SELECT COUNT(*) FROM whatsapp_contacts")).scalar()
            tags_count = db.session.execute(text("SELECT COUNT(*) FROM whatsapp_contact_tags")).scalar()

            print(f"\n  Contactos: {contacts_count}")
            print(f"  Relaciones de etiquetas: {tags_count}")

            # Mostrar ejemplo
            result = db.session.execute(text("""
                SELECT id, contact_id, phone_number, name FROM whatsapp_contacts LIMIT 3;
            """))
            rows = result.fetchall()
            if rows:
                print("\n  Ejemplos de contactos:")
                for row in rows:
                    print(f"    ID: {row[0]}, ContactID: {row[1]}, Tel: {row[2]}, Nombre: {row[3]}")

            print("\n" + "=" * 60)
            print("✅ MIGRACIÓN COMPLETADA EXITOSAMENTE")
            print("=" * 60)
            print("\nPróximos pasos:")
            print("  1. Reinicia la aplicación")
            print("  2. Verifica que puedas editar contactos")
            print("  3. Prueba cambiar un número de teléfono desde el modal")

        except Exception as e:
            db.session.rollback()
            print(f"\n❌ ERROR EN MIGRACIÓN: {e}")
            import traceback
            traceback.print_exc()
            return False

        return True

if __name__ == "__main__":
    print("\nEste script migrará la base de datos PostgreSQL para:")
    print("  • Usar ID autoincremental como clave primaria de contactos")
    print("  • Agregar contact_id editable para integración con sistemas externos")
    print("  • Permitir editar números de teléfono sin perder datos")
    print("  • Actualizar las relaciones de etiquetas")
    print()

    confirm = input("¿Deseas continuar? (s/n): ").strip().lower()

    if confirm == 's':
        migrate_pg()
    else:
        print("Migración cancelada.")
