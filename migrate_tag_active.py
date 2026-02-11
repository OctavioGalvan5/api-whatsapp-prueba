"""
Migración: Agregar campo is_active a la tabla whatsapp_tags.
Permite deshabilitar etiquetas sin eliminarlas.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db

def migrate():
    with app.app_context():
        # Agregar columna is_active si no existe
        db.session.execute(db.text("""
            ALTER TABLE whatsapp_tags 
            ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE NOT NULL;
        """))
        db.session.commit()
        print("✅ Migración completada: columna 'is_active' agregada a whatsapp_tags")

if __name__ == '__main__':
    migrate()
