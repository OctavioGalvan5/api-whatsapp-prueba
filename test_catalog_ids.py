"""
Probar envio con ambos catalog IDs para ver cual funciona.
"""
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = "EAARKWBZAyoEIBRNRThC3kbgpZBiBHJDy4oyHuYRm2vOUx2syqi80bvx2vHdaGhCFmLRAKlxfrpu48Iikk5fqDbiY1gcAAUwX6NkqPJujFy95PRfhmXi4kOzuPg7C7BNrLRRuQkKZBQITHgOG41gFbTY4HhXTWde1zLqxNYhoa7r2oNJXTr9kFaz9TXqNQZDZD"

PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
BASE_URL = "https://graph.facebook.com/v21.0"

headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

DESTINATARIO = "5493874882011"
CATALOG_REAL = "1990424264879603"
COMMERCE_ID = "923538424005964"


def send_product_with_catalog(catalog_id, label):
    print(f"\n{'=' * 60}")
    print(f"Probando con {label}: {catalog_id}")
    print("=" * 60)
    
    url = f"{BASE_URL}/{PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": DESTINATARIO,
        "type": "interactive",
        "interactive": {
            "type": "product",
            "body": {
                "text": f"Producto de prueba (catalog: {label})"
            },
            "action": {
                "catalog_id": catalog_id,
                "product_retailer_id": "3lrmu32i5v"
            }
        }
    }
    
    response = requests.post(url, headers=headers, json=payload)
    data = response.json()
    
    if "error" in data:
        print(f"  ERROR: {data['error'].get('message')}")
        print(f"  Codigo: {data['error'].get('code')}")
    else:
        print(f"  EXITO! Producto enviado!")
        print(f"  Message ID: {data.get('messages', [{}])[0].get('id')}")
    return data


def check_phone_number_catalog():
    """Ver si hay un catalog_id asociado directamente al phone number"""
    print("=" * 60)
    print("Verificando Phone Number Business Profile")
    print("=" * 60)
    
    url = f"{BASE_URL}/{PHONE_NUMBER_ID}"
    params = {"fields": "id,display_phone_number,verified_name,business_profile"}
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    print(f"  {json.dumps(data, indent=2)}")
    return data


if __name__ == "__main__":
    check_phone_number_catalog()
    
    # Probar con el catalog real
    send_product_with_catalog(CATALOG_REAL, "CATALOG_REAL")
    
    # Probar con el commerce settings ID
    send_product_with_catalog(COMMERCE_ID, "COMMERCE_ID")
    
    print("\n" + "=" * 60)
    print("COMPLETADO")
    print("=" * 60)
