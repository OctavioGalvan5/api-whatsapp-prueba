"""
Script de migración: Permitir teléfonos duplicados.
Elimina la restricción UNIQUE del campo phone_number en whatsapp_contacts.

Ejecutar con: python migrate_phone_unique.py
"""

import sqlite3
import os
        print(f"[X] Base de datos no encontrada: {DB_PATH}")
        return False

def migrate():
    print("\n=== MIGRACIÓN: REMOVER UNIQUE DE PHONE_NUMBER ===")
    
    # 1. Backup
    if not backup_database():
        return False
        
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = OFF")
    cursor = conn.cursor()
    
    try:
        # Detectar columnas actuales
        cursor.execute("PRAGMA table_info(whatsapp_contacts)")
        columns_info = cursor.fetchall()
        column_names = [c[1] for c in columns_info]
        
        print(f"Columnas detectadas: {column_names}")
        
        # 2. Renombrar tabla actual
        cursor.execute("DROP TABLE IF EXISTS whatsapp_contacts_old_unique") # Limpieza previa por si acaso
        cursor.execute("ALTER TABLE whatsapp_contacts RENAME TO whatsapp_contacts_old_unique")
        print("✓ Tabla renombrada a whatsapp_contacts_old_unique")
        
        # 3. Crear nueva tabla SIN unique en phone_number
        # Nota: Mantenemos la estructura pero removemos UNIQUE de phone_number
        cursor.execute("""
            CREATE TABLE whatsapp_contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_number VARCHAR(20) NOT NULL, -- UNIQUE REMOVIDO
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
                custom_field_7 VARCHAR(255),
                contact_id VARCHAR(50) -- Agregamos explícitamente si no estaba en el create original migrado
            )
        """)
        
        # Verificar si contact_id existe en la vieja (por si acaso la migración anterior varió)
        has_contact_id = 'contact_id' in column_names
        
        # Construir query de copiado dinámico
        cols_to_copy = [c for c in column_names if c != 'id'] # id es autoincrement, mejor preservar si se puede, pero insertando explícito
        cols_str = ", ".join(cols_to_copy)
        
        # Si la tabla vieja tieen ID, lo copiamos para preservar IDs
        if 'id' in column_names:
            cols_str = "id, " + cols_str
            
        print(f"Copiando columnas: {cols_str}")
        
        cursor.execute(f"""
            INSERT INTO whatsapp_contacts ({cols_str})
            SELECT {cols_str}
            FROM whatsapp_contacts_old_unique
        """)
        
        rows = cursor.rowcount
        print(f"✓ {rows} contactos migrados a la nueva tabla")
        
        # 4. Recrear índices (sin unique en phone)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_contacts_phone ON whatsapp_contacts(phone_number)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_contacts_contact_id ON whatsapp_contacts(contact_id)")
        print("✓ Índices recreados (no únicos)")
        
        # 5. Eliminar tabla vieja
        cursor.execute("DROP TABLE whatsapp_contacts_old_unique")
        print("✓ Tabla vieja eliminada")
        
        conn.commit()
        print("\n✓ MIGRACIÓN EXITOSA")
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"\n✗ Error: {e}")
        return False
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()

if __name__ == "__main__":
    migrate()
