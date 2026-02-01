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
