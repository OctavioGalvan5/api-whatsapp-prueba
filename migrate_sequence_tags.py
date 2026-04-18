"""
Migración:
- Crea tabla followup_sequence_tags (many-to-many secuencia <-> etiquetas)
- Agrega columna add_tag_on_complete a followup_sequences
- Migra los tag_id existentes a la nueva tabla
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL_caja')

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

print("Creando tabla followup_sequence_tags...")
cur.execute("""
    CREATE TABLE IF NOT EXISTS followup_sequence_tags (
        sequence_id INTEGER NOT NULL REFERENCES followup_sequences(id) ON DELETE CASCADE,
        tag_id      INTEGER NOT NULL REFERENCES whatsapp_tags(id) ON DELETE CASCADE,
        PRIMARY KEY (sequence_id, tag_id)
    );
""")
print("✅ Tabla creada.")

print("Agregando columna add_tag_on_complete...")
cur.execute("""
    ALTER TABLE followup_sequences
    ADD COLUMN IF NOT EXISTS add_tag_on_complete BOOLEAN NOT NULL DEFAULT FALSE;
""")
print("✅ Columna agregada.")

print("Migrando tag_id existentes a followup_sequence_tags...")
cur.execute("""
    INSERT INTO followup_sequence_tags (sequence_id, tag_id)
    SELECT id, tag_id
    FROM followup_sequences
    WHERE tag_id IS NOT NULL
    ON CONFLICT DO NOTHING;
""")
cur.execute("SELECT COUNT(*) FROM followup_sequence_tags")
count = cur.fetchone()[0]
print(f"✅ {count} fila(s) migradas.")

cur.close()
conn.close()
print("✅ Migración completada.")
print()
print("NOTA: El campo tag_id en followup_sequences se mantiene por compatibilidad.")
print("Las secuencias nuevas usarán followup_sequence_tags.")
