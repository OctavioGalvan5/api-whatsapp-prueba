"""
Script de migración: Agregar ID único a contactos.

Este script migra la base de datos para usar un ID autoincremental como
clave primaria de contactos, en lugar del número de teléfono.

Ejecutar con: python migrate_contact_id.py

IMPORTANTE: Hacer backup de la base de datos antes de ejecutar.
"""

import sqlite3
import os
import shutil
from datetime import datetime

# Configuración
DB_PATH = 'instance/whatsapp_crm.db'
BACKUP_PATH = f'instance/whatsapp_crm_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'

def backup_database():
    """Crear backup de la base de datos."""
    if os.path.exists(DB_PATH):
        shutil.copy2(DB_PATH, BACKUP_PATH)
        print(f"✓ Backup creado: {BACKUP_PATH}")
        return True
    else:
        print(f"✗ Base de datos no encontrada: {DB_PATH}")
        return False

def check_if_migrated(conn):
    """Verificar si la migración ya fue aplicada."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(whatsapp_contacts)")
    columns = [col[1] for col in cursor.fetchall()]
    return 'id' in columns and columns[0] == 'id'

def migrate():
    """Ejecutar la migración."""

    # 1. Backup
    print("\n=== PASO 1: Backup ===")
    if not backup_database():
        return False

    # 2. Conectar a la base de datos
    print("\n=== PASO 2: Conectando a la base de datos ===")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = OFF")
    cursor = conn.cursor()

    try:
        # 3. Verificar si ya está migrada
        if check_if_migrated(conn):
            print("✓ La base de datos ya está migrada. No se requiere acción.")
            conn.close()
            return True

        print("→ Iniciando migración...")

        # 4. Crear nueva tabla de contactos con ID
        print("\n=== PASO 3: Creando nueva estructura de contactos ===")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_contacts_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_number VARCHAR(20) NOT NULL UNIQUE,
                name VARCHAR(100),
                notes TEXT,
                tags JSON DEFAULT '[]',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                first_name VARCHAR(100),
                last_name VARCHAR(100),
                custom_field_1 VARCHAR(255),
                custom_field_2 VARCHAR(255),
                custom_field_3 VARCHAR(255),
                custom_field_4 VARCHAR(255),
                custom_field_5 VARCHAR(255),
                custom_field_6 VARCHAR(255),
                custom_field_7 VARCHAR(255)
            )
        """)
        print("✓ Tabla whatsapp_contacts_new creada")

        # 5. Copiar datos de contactos existentes
        print("\n=== PASO 4: Migrando contactos existentes ===")
        cursor.execute("""
            INSERT INTO whatsapp_contacts_new
                (phone_number, name, notes, tags, created_at, first_name, last_name,
                 custom_field_1, custom_field_2, custom_field_3, custom_field_4,
                 custom_field_5, custom_field_6, custom_field_7)
            SELECT
                phone_number, name, notes, tags, created_at, first_name, last_name,
                custom_field_1, custom_field_2, custom_field_3, custom_field_4,
                custom_field_5, custom_field_6, custom_field_7
            FROM whatsapp_contacts
        """)
        contacts_migrated = cursor.rowcount
        print(f"✓ {contacts_migrated} contactos migrados")

        # 6. Crear nueva tabla de etiquetas de contactos
        print("\n=== PASO 5: Migrando relación de etiquetas ===")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_contact_tags_new (
                contact_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY (contact_id, tag_id),
                FOREIGN KEY (contact_id) REFERENCES whatsapp_contacts_new(id),
                FOREIGN KEY (tag_id) REFERENCES whatsapp_tags(id)
            )
        """)

        # Migrar etiquetas usando el mapeo phone -> id
        cursor.execute("""
            INSERT INTO whatsapp_contact_tags_new (contact_id, tag_id)
            SELECT cn.id, ct.tag_id
            FROM whatsapp_contact_tags ct
            JOIN whatsapp_contacts_new cn ON cn.phone_number = ct.contact_phone
        """)
        tags_migrated = cursor.rowcount
        print(f"✓ {tags_migrated} relaciones de etiquetas migradas")

        # 7. Agregar contact_id a campaign_logs (opcional, mantener contact_phone por compatibilidad)
        print("\n=== PASO 6: Actualizando logs de campañas ===")

        # Verificar si la columna contact_id ya existe
        cursor.execute("PRAGMA table_info(whatsapp_campaign_logs)")
        log_columns = [col[1] for col in cursor.fetchall()]

        if 'contact_id' not in log_columns:
            cursor.execute("ALTER TABLE whatsapp_campaign_logs ADD COLUMN contact_id INTEGER")
            print("✓ Columna contact_id agregada a campaign_logs")

            # Poblar contact_id basándose en contact_phone
            cursor.execute("""
                UPDATE whatsapp_campaign_logs
                SET contact_id = (
                    SELECT id FROM whatsapp_contacts_new
                    WHERE phone_number = whatsapp_campaign_logs.contact_phone
                )
            """)
            print("✓ contact_id poblado en campaign_logs")
        else:
            print("✓ contact_id ya existe en campaign_logs")

        # 8. Renombrar tablas
        print("\n=== PASO 7: Reemplazando tablas ===")

        # Eliminar tablas antiguas
        cursor.execute("DROP TABLE IF EXISTS whatsapp_contact_tags")
        cursor.execute("DROP TABLE IF EXISTS whatsapp_contacts")
        print("✓ Tablas antiguas eliminadas")

        # Renombrar nuevas tablas
        cursor.execute("ALTER TABLE whatsapp_contacts_new RENAME TO whatsapp_contacts")
        cursor.execute("ALTER TABLE whatsapp_contact_tags_new RENAME TO whatsapp_contact_tags")
        print("✓ Nuevas tablas renombradas")

        # 9. Crear índices
        print("\n=== PASO 8: Creando índices ===")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_contacts_phone ON whatsapp_contacts(phone_number)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_contact_tags_contact ON whatsapp_contact_tags(contact_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_contact_tags_tag ON whatsapp_contact_tags(tag_id)")
        print("✓ Índices creados")

        # 10. Commit
        conn.commit()
        print("\n=== MIGRACIÓN COMPLETADA ===")
        print(f"✓ {contacts_migrated} contactos migrados exitosamente")
        print(f"✓ {tags_migrated} relaciones de etiquetas migradas")
        print(f"✓ Backup disponible en: {BACKUP_PATH}")

        return True

    except Exception as e:
        conn.rollback()
        print(f"\n✗ ERROR durante la migración: {e}")
        print(f"→ La base de datos no fue modificada. Backup en: {BACKUP_PATH}")
        return False

    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()

def verify_migration():
    """Verificar que la migración fue exitosa."""
    print("\n=== VERIFICACIÓN ===")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Verificar estructura de contactos
    cursor.execute("PRAGMA table_info(whatsapp_contacts)")
    columns = cursor.fetchall()
    print("\nEstructura de whatsapp_contacts:")
    for col in columns:
        print(f"  - {col[1]} ({col[2]}){' PRIMARY KEY' if col[5] else ''}")

    # Contar registros
    cursor.execute("SELECT COUNT(*) FROM whatsapp_contacts")
    contact_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM whatsapp_contact_tags")
    tag_rel_count = cursor.fetchone()[0]

    print(f"\nRegistros:")
    print(f"  - Contactos: {contact_count}")
    print(f"  - Relaciones de etiquetas: {tag_rel_count}")

    # Mostrar ejemplo
    cursor.execute("SELECT id, phone_number, name FROM whatsapp_contacts LIMIT 3")
    examples = cursor.fetchall()
    if examples:
        print("\nEjemplos de contactos:")
        for ex in examples:
            print(f"  - ID: {ex[0]}, Tel: {ex[1]}, Nombre: {ex[2]}")

    conn.close()

if __name__ == "__main__":
    print("=" * 50)
    print("MIGRACIÓN: Agregar ID único a Contactos")
    print("=" * 50)

    # Confirmar
    print("\nEsta migración:")
    print("  1. Creará un backup de la base de datos")
    print("  2. Agregará un ID autoincremental a contactos")
    print("  3. Actualizará las relaciones de etiquetas")
    print("  4. Permitirá editar números de teléfono")

    confirm = input("\n¿Desea continuar? (s/n): ").strip().lower()

    if confirm == 's':
        if migrate():
            verify_migration()
            print("\n✓ Migración completada. Reinicie la aplicación.")
        else:
            print("\n✗ Migración fallida. Revise los errores arriba.")
    else:
        print("\nMigración cancelada.")
