import logging
from sqlalchemy import text, inspect
from app import app, db

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# probando
def add_column_if_not_exists(table_name, column_name, column_type):
    """Agrega una columna a una tabla si no existe."""
    with app.app_context():
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns(table_name)]
        
        if column_name not in columns:
            logger.info(f"Agregando columna '{column_name}' a la tabla '{table_name}'...")
            try:
                # Determinar el dialecto para la sintaxis correcta si es necesario
                # Por simplicidad asumimos PostgreSQL/SQLite compatible para ADD COLUMN
                with db.engine.connect() as conn:
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
                    conn.commit()
                logger.info(f"✅ Columna '{column_name}' agregada exitosamente.")
            except Exception as e:
                logger.error(f"❌ Error agregando columna '{column_name}': {e}")
        else:
            logger.info(f"ℹ️ La columna '{column_name}' ya existe en '{table_name}'.")

if __name__ == "__main__":
    logger.info("Iniciando migración de base de datos...")
    
    # Agregar columnas a whatsapp_campaigns
    add_column_if_not_exists('whatsapp_campaigns', 'scheduled_at', 'TIMESTAMP')
    add_column_if_not_exists('whatsapp_campaigns', 'variables', 'JSON')
    
    logger.info("Migración completada.")
