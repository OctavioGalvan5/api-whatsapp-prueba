import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "test_token")
    CHATWOOT_WEBHOOK_URL = os.getenv("CHATWOOT_WEBHOOK_URL")
    PORT = int(os.getenv("PORT", 5000))
    DATABASE_URL = os.getenv("DATABASE_URL")
    
    # Autenticación
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
    LOGIN_PASSWORD = os.getenv("LOGIN_PASSWORD", "admin")

    # WhatsApp Business API
    WHATSAPP_API_TOKEN = os.getenv("WHATSAPP_API_TOKEN")
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")

    # MinIO / S3 Storage
    MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT")
    MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
    MINIO_SECRET_KEY = os.getenv("SECRET_KEY_MINIO")
    MINIO_BUCKET = os.getenv("MINIO_BUCKET")
    MINIO_BUCKET_RAG = os.getenv("MINIO_BUCKET_RAG", "rag-documents")
    MINIO_USE_SSL = str(os.getenv("MINIO_USE_SSL", "false")).lower() == "true"

    # n8n Webhooks
    N8N_WEBHOOK_VECTORIZE = os.getenv("N8N_WEBHOOK_VECTORIZE")
    N8N_WEBHOOK_DELETE = os.getenv("N8N_WEBHOOK_DELETE")
    FLASK_BASE_URL = os.getenv("FLASK_BASE_URL", "http://localhost:3000")
    
    # n8n API (para controlar workflows)
    N8N_API_URL = os.getenv("N8N_API_URL")
    N8N_API_KEY = os.getenv("N8N_API_KEY")
