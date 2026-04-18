"""
Migración: crea tabla contact_tag_history
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL_caja')

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

print("Creando tabla contact_tag_history...")
cur.execute("""
    CREATE TABLE IF NOT EXISTS contact_tag_history (
        id SERIAL PRIMARY KEY,
        contact_id INTEGER NOT NULL REFERENCES whatsapp_contacts(id) ON DELETE CASCADE,
        tag_id INTEGER REFERENCES whatsapp_tags(id) ON DELETE SET NULL,
        tag_name_snapshot VARCHAR(50) NOT NULL,
        action VARCHAR(10) NOT NULL,
        source VARCHAR(20) NOT NULL,
        created_by VARCHAR(100),
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
""")
print("✅ Tabla creada.")

print("Creando índices...")
cur.execute("CREATE INDEX IF NOT EXISTS idx_tag_history_contact ON contact_tag_history(contact_id);")
cur.execute("CREATE INDEX IF NOT EXISTS idx_tag_history_created ON contact_tag_history(created_at);")
print("✅ Índices creados.")

cur.close()
conn.close()
print("✅ Migración completada.")
