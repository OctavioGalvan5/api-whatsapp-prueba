"""
Migración: Agregar campos para detección de asistencia humana.
- is_system en whatsapp_tags (tags del sistema no se pueden eliminar)
- has_unanswered_questions en conversation_sessions
- escalated_to_human en conversation_sessions

Usa psycopg2 directo para evitar problemas con SQLAlchemy al importar app
(la columna is_system no existe aún cuando app.py intenta hacer query).
"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    print("ERROR: DATABASE_URL no configurada en .env")
    exit(1)


def migrate():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    try:
        # 1. Agregar columna is_system a whatsapp_tags
        cur.execute("""
            ALTER TABLE whatsapp_tags
            ADD COLUMN IF NOT EXISTS is_system BOOLEAN DEFAULT FALSE NOT NULL;
        """)
        print("✅ Columna 'is_system' agregada a whatsapp_tags")

        # 2. Agregar columna has_unanswered_questions a conversation_sessions
        cur.execute("""
            ALTER TABLE conversation_sessions
            ADD COLUMN IF NOT EXISTS has_unanswered_questions BOOLEAN DEFAULT FALSE NOT NULL;
        """)
        print("✅ Columna 'has_unanswered_questions' agregada a conversation_sessions")

        # 3. Agregar columna escalated_to_human a conversation_sessions
        cur.execute("""
            ALTER TABLE conversation_sessions
            ADD COLUMN IF NOT EXISTS escalated_to_human BOOLEAN DEFAULT FALSE NOT NULL;
        """)
        print("✅ Columna 'escalated_to_human' agregada a conversation_sessions")

        # 4. Crear tag del sistema "Asistencia Humana" si no existe
        cur.execute("""
            INSERT INTO whatsapp_tags (name, color, is_system, is_active)
            VALUES ('Asistencia Humana', 'red', TRUE, TRUE)
            ON CONFLICT (name) DO UPDATE SET is_system = TRUE;
        """)
        print("✅ Tag del sistema 'Asistencia Humana' creado/actualizado")

        print("\n🎉 Migración completada exitosamente")

    except Exception as e:
        print(f"❌ Error en migración: {e}")
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    migrate()
