"""
Script de migración para agregar restricción única a CampaignLog.
"""
import os
import sys

# Agregar el directorio actual al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from sqlalchemy import text

def migrate():
    with app.app_context():
        print("Iniciando migración de CampaignLog...")
        
        try:
            # 1. Limpiar duplicados existentes si los hay (opcional pero recomendado)
            # Esto borrará los logs duplicados manteniendo solo el primero creado
            db.session.execute(text("""
                DELETE FROM whatsapp_campaign_logs 
                WHERE id NOT IN (
                    SELECT MIN(id) 
                    FROM whatsapp_campaign_logs 
                    GROUP BY campaign_id, contact_id
                )
            """))
            db.session.commit()
            print("Duplicados existentes eliminados (si los había).")

            # 2. Agregar el constraint único
            # Nota: El nombre del constraint debe coincidir con el definido en models.py
            db.session.execute(text("""
                ALTER TABLE whatsapp_campaign_logs 
                ADD CONSTRAINT uq_campaign_contact_log UNIQUE (campaign_id, contact_id)
            """))
            db.session.commit()
            print("Restricción UNIQUE agregada con éxito.")
            
        except Exception as e:
            db.session.rollback()
            print(f"Error durante la migración: {e}")
            print("Nota: Si el error es que la restricción ya existe, podés ignorarlo.")

if __name__ == "__main__":
    migrate()
