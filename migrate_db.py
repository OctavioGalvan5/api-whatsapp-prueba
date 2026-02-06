"""
Script para migrar la base de datos.
Crea las tablas nuevas sin afectar las existentes.

Ejecutar con: python migrate_db.py
"""
from app import app, db
from models import RagDocument, ChatbotConfig

def migrate():
    with app.app_context():
        print("🔄 Iniciando migración de base de datos...")

        # Crear todas las tablas que no existan
        db.create_all()

        print("✅ Tablas creadas/verificadas:")
        print("   - rag_documents")
        print("   - chatbot_config")

        # Inicializar configuración por defecto del chatbot si no existe
        if ChatbotConfig.get('enabled') is None:
            ChatbotConfig.set('enabled', 'true')
            print("✅ Configuración inicial del chatbot creada (enabled=true)")
        else:
            print("ℹ️  Configuración del chatbot ya existe")

        print("\n🎉 Migración completada exitosamente!")

if __name__ == "__main__":
    migrate()
