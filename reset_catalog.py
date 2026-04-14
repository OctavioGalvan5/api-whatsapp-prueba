"""
Desconectar y reconectar el catalogo al WABA para forzar re-sync.
"""
import requests
import json
import os
import time
from dotenv import load_dotenv
load_dotenv()

ACCESS_TOKEN = "EAARKWBZAyoEIBRNRThC3kbgpZBiBHJDy4oyHuYRm2vOUx2syqi80bvx2vHdaGhCFmLRAKlxfrpu48Iikk5fqDbiY1gcAAUwX6NkqPJujFy95PRfhmXi4kOzuPg7C7BNrLRRuQkKZBQITHgOG41gFbTY4HhXTWde1zLqxNYhoa7r2oNJXTr9kFaz9TXqNQZDZD"
WABA_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
CATALOG_ID = "1990424264879603"
BASE_URL = "https://graph.facebook.com/v21.0"

headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

# PASO 1: Desconectar catalogo del WABA
print("PASO 1: Desconectando catalogo del WABA...")
url = f"{BASE_URL}/{WABA_ID}/product_catalogs"
r = requests.delete(url, headers=headers, json={"catalog_id": CATALOG_ID})
print(f"  Resultado: {json.dumps(r.json(), indent=2)}")

# Esperar un poco
print("\nEsperando 10 segundos...")
time.sleep(10)

# PASO 2: Verificar que se desconecto
print("\nPASO 2: Verificando desconexion...")
url = f"{BASE_URL}/{WABA_ID}/product_catalogs"
r = requests.get(url, headers=headers)
print(f"  Catalogos: {json.dumps(r.json(), indent=2)}")

# PASO 3: Reconectar catalogo al WABA
print("\nPASO 3: Reconectando catalogo al WABA...")
url = f"{BASE_URL}/{WABA_ID}/product_catalogs"
r = requests.post(url, headers=headers, json={"catalog_id": CATALOG_ID})
print(f"  Resultado: {json.dumps(r.json(), indent=2)}")

# PASO 4: Reconfigurar commerce settings
print("\nPASO 4: Reconfigurando commerce settings en el numero...")
url = f"{BASE_URL}/{PHONE_NUMBER_ID}/whatsapp_commerce_settings"
payload = {
    "catalog_id": CATALOG_ID,
    "is_catalog_visible": True,
    "is_cart_enabled": True,
}
r = requests.post(url, headers=headers, json=payload)
print(f"  Resultado: {json.dumps(r.json(), indent=2)}")

# PASO 5: Verificar estado final
print("\nPASO 5: Estado final...")
url = f"{BASE_URL}/{WABA_ID}/product_catalogs"
r = requests.get(url, headers=headers)
print(f"  Catalogos WABA: {json.dumps(r.json(), indent=2)}")

url = f"{BASE_URL}/{PHONE_NUMBER_ID}/whatsapp_commerce_settings"
r = requests.get(url, headers=headers)
print(f"  Commerce settings: {json.dumps(r.json(), indent=2)}")

print("\nListo! El catalogo fue reconectado. Espera unos minutos para que se sincronice.")
