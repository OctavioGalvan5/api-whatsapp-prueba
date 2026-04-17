"""
Migración: agrega columna read_at a whatsapp_messages
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL_caja')

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

print("Agregando columna read_at...")
cur.execute("""
    ALTER TABLE whatsapp_messages
    ADD COLUMN IF NOT EXISTS read_at TIMESTAMP DEFAULT NULL;
""")
print("✅ Columna read_at agregada.")

print("Creando índice...")
conn.set_isolation_level(0)  # AUTOCOMMIT a nivel de conexión para CONCURRENTLY
cur.execute("""
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_messages_read_at
    ON whatsapp_messages(read_at);
""")
print("✅ Índice creado.")

cur.close()
conn.close()
print("✅ Migración completada.")
