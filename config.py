import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "test_token")
    CHATWOOT_WEBHOOK_URL = os.getenv("CHATWOOT_WEBHOOK_URL")
    PORT = int(os.getenv("PORT", 5000))
    DATABASE_URL = os.getenv("DATABASE_URL")
