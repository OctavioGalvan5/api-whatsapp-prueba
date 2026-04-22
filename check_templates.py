"""
Script para ver el estado de todas las templates de WhatsApp.
Uso: python check_templates.py
"""
import requests
import os
import sys
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

TOKEN = os.getenv("WHATSAPP_API_TOKEN")
BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")

if not TOKEN or not BUSINESS_ACCOUNT_ID:
    print("❌ Faltan variables WHATSAPP_API_TOKEN o WHATSAPP_BUSINESS_ACCOUNT_ID en el .env")
    exit(1)

url = f"https://graph.facebook.com/v22.0/{BUSINESS_ACCOUNT_ID}/message_templates"
headers = {"Authorization": f"Bearer {TOKEN}"}
params = {"limit": 100, "fields": "name,status,language,components,rejected_reason,quality_score"}

response = requests.get(url, headers=headers, params=params)
data = response.json()

if "error" in data:
    print(f"❌ Error de Meta: {data['error']}")
    exit(1)

templates = data.get("data", [])
print(f"\n{'='*60}")
print(f"  {len(templates)} templates encontradas")
print(f"{'='*60}\n")

STATUS_ICON = {
    "APPROVED": "[OK]",
    "PENDING": "[PENDIENTE]",
    "REJECTED": "[RECHAZADA]",
    "PAUSED": "[PAUSADA]",
    "DISABLED": "[DESHABILITADA]",
}

for t in sorted(templates, key=lambda x: x.get("status", "")):
    status = t.get("status", "?")
    icon = STATUS_ICON.get(status, "❓")
    lang = t.get("language", "?")
    name = t.get("name", "?")
    rejected = t.get("rejected_reason", "")

    print(f"{icon} [{status}] {name}  (lang: {lang})")
    if rejected:
        print(f"     -> Razon rechazo: {rejected}")
    # Mostrar body
    for comp in t.get("components", []):
        if comp.get("type") == "BODY":
            print(f"     Body: {comp.get('text','')}")

print()
