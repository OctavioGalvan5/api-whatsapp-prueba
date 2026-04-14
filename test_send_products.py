"""Probar envio de producto con la cuenta CountryLife Bot."""
import requests, json, os
from dotenv import load_dotenv
load_dotenv(override=True)

ACCESS_TOKEN = os.getenv("WHATSAPP_API_TOKEN")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
CATALOG_ID = "1990424264879603"
BASE_URL = "https://graph.facebook.com/v21.0"
headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}

# Numero destino (tiene que ser diferente al del negocio +54 9 387 533-2350)
DESTINATARIO = "5493872226660"

print(f"Cuenta: CountryLife Bot")
print(f"Phone: {PHONE_NUMBER_ID}")
print(f"Catalog: {CATALOG_ID}")
print(f"Destino: {DESTINATARIO}\n")

# Test 1: Texto normal
print("=" * 60)
print("TEST 1: Mensaje de texto")
print("=" * 60)
url = f"{BASE_URL}/{PHONE_NUMBER_ID}/messages"
payload = {
    "messaging_product": "whatsapp",
    "to": DESTINATARIO,
    "type": "text",
    "text": {"body": "Test CountryLife Bot - catalogo"}
}
r = requests.post(url, headers=headers, json=payload)
data = r.json()
if "error" in data:
    print(f"  Error: {data['error'].get('message')}")
else:
    print(f"  OK! ID: {data.get('messages', [{}])[0].get('id')}")

# Test 2: Producto individual
print("\n" + "=" * 60)
print("TEST 2: Producto individual")
print("=" * 60)
payload = {
    "messaging_product": "whatsapp",
    "to": DESTINATARIO,
    "type": "interactive",
    "interactive": {
        "type": "product",
        "body": {"text": "Mira este producto!"},
        "action": {
            "catalog_id": CATALOG_ID,
            "product_retailer_id": "3lrmu32i5v"
        }
    }
}
r = requests.post(url, headers=headers, json=payload)
data = r.json()
if "error" in data:
    print(f"  Error: {data['error'].get('message')}")
    print(f"  Code: {data['error'].get('code')}")
    print(f"  Detail: {json.dumps(data['error'], indent=2)}")
else:
    print(f"  EXITO! Producto enviado!")
    print(f"  ID: {data.get('messages', [{}])[0].get('id')}")

# Test 3: Lista de productos
print("\n" + "=" * 60)
print("TEST 3: Lista de productos")
print("=" * 60)
payload = {
    "messaging_product": "whatsapp",
    "to": DESTINATARIO,
    "type": "interactive",
    "interactive": {
        "type": "product_list",
        "header": {"type": "text", "text": "Productos"},
        "body": {"text": "Nuestros productos disponibles:"},
        "action": {
            "catalog_id": CATALOG_ID,
            "sections": [{
                "title": "Todos",
                "product_items": [
                    {"product_retailer_id": "3lrmu32i5v"},
                    {"product_retailer_id": "1j3phfqxw6"},
                    {"product_retailer_id": "0vgedz0bnv"},
                ]
            }]
        }
    }
}
r = requests.post(url, headers=headers, json=payload)
data = r.json()
if "error" in data:
    print(f"  Error: {data['error'].get('message')}")
    print(f"  Code: {data['error'].get('code')}")
else:
    print(f"  EXITO! Lista enviada!")
    print(f"  ID: {data.get('messages', [{}])[0].get('id')}")

print("\nCOMPLETADO")
