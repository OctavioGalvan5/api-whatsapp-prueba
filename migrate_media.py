from app import app, db
from sqlalchemy import text

def migrate_media_columns():
    """Agrega columnas media_id, media_url y caption a la tabla whatsapp_messages."""
    with app.app_context():
        # Verificar si las columnas ya existen
        with db.engine.connect() as conn:
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='whatsapp_messages'"))
            columns = [row[0] for row in result.fetchall()]
            
            if 'media_id' not in columns:
                print("Agregando columna media_id...")
                conn.execute(text("ALTER TABLE whatsapp_messages ADD COLUMN media_id VARCHAR(100)"))
            
            if 'media_url' not in columns:
                print("Agregando columna media_url...")
                conn.execute(text("ALTER TABLE whatsapp_messages ADD COLUMN media_url VARCHAR(255)"))
                
            if 'caption' not in columns:
                print("Agregando columna caption...")
                conn.execute(text("ALTER TABLE whatsapp_messages ADD COLUMN caption TEXT"))
                
            conn.commit()
            print("Migración de media completada.")

if __name__ == '__main__':
    migrate_media_columns()
