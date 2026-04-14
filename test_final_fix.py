"""
Verificacion final - conectar catalogo al business profile del telefono.
"""
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = "EAARKWBZAyoEIBRNRThC3kbgpZBiBHJDy4oyHuYRm2vOUx2syqi80bvx2vHdaGhCFmLRAKlxfrpu48Iikk5fqDbiY1gcAAUwX6NkqPJujFy95PRfhmXi4kOzuPg7C7BNrLRRuQkKZBQITHgOG41gFbTY4HhXTWde1zLqxNYhoa7r2oNJXTr9kFaz9TXqNQZDZD"

PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WABA_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
CATALOG_ID = "1990424264879603"
BASE_URL = "https://graph.facebook.com/v21.0"
DESTINATARIO = "5493874882011"

headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}


# 1. Verificar que catalogo tiene el phone number asociado
print("=" * 60)
print("1. Consultando catalogo del phone number")
print("=" * 60)

url = f"{BASE_URL}/{PHONE_NUMBER_ID}/whatsapp_commerce_settings"
params = {"fields": "id,is_cart_enabled,is_catalog_visible"}
r = requests.get(url, headers=headers, params=params)
print(f"  {json.dumps(r.json(), indent=2)}")


# 2. Desconectar commerce settings y reconectar con el catalogo correcto
print("\n" + "=" * 60)
print("2. Reconfigurando commerce settings con catalog_id")
print("=" * 60)

# Primero, actualizar con el catalog_id correcto usando UPDATE
url = f"{BASE_URL}/{PHONE_NUMBER_ID}/whatsapp_commerce_settings"
payload = {
    "catalog_id": CATALOG_ID,
    "is_catalog_visible": True,
    "is_cart_enabled": True,
}
r = requests.post(url, headers=headers, json=payload)
print(f"  POST result: {json.dumps(r.json(), indent=2)}")


# 3. Verificar de nuevo
print("\n" + "=" * 60)
print("3. Verificacion post-actualizacion")
print("=" * 60)

url = f"{BASE_URL}/{PHONE_NUMBER_ID}/whatsapp_commerce_settings"
params = {"fields": "id,is_cart_enabled,is_catalog_visible"}
r = requests.get(url, headers=headers, params=params)
data = r.json()
print(f"  {json.dumps(data, indent=2)}")

commerce_data = data.get("data", [])
if commerce_data:
    cid = commerce_data[0].get("id", "")
    print(f"\n  Commerce ID actual: {cid}")
    print(f"  Catalog ID esperado: {CATALOG_ID}")
    if cid == CATALOG_ID:
        print("  COINCIDEN!")
    else:
        print("  NO COINCIDEN - el commerce settings no usa nuestro catalog")


# 4. Verificar productos con el Commerce ID
print("\n" + "=" * 60)
print(f"4. Intentando acceder productos del Commerce ID")
print("=" * 60)

commerce_id = commerce_data[0].get("id", "") if commerce_data else ""
if commerce_id:
    url = f"{BASE_URL}/{commerce_id}/products"
    params = {"fields": "id,name,retailer_id"}
    r = requests.get(url, headers=headers, params=params)
    data = r.json()
    if "error" in data:
        print(f"  Error: {data['error'].get('message')}")
        print(f"  -> El Commerce ID no es un catalogo, es otro tipo de objeto")
    else:
        print(f"  Productos: {json.dumps(data, indent=2)}")


# 5. Probar envio con el WABA ID como catalog (algunos BSP usan esto)
print("\n" + "=" * 60)
print("5. Obteniendo el catalog que esta REALMENTE vinculado al phone")
print("=" * 60)

# Buscar catalogs del WABA
url = f"{BASE_URL}/{WABA_ID}/product_catalogs"
r = requests.get(url, headers=headers)
waba_catalogs = r.json()
print(f"  Catalogos WABA: {json.dumps(waba_catalogs, indent=2)}")

if waba_catalogs.get("data"):
    correct_catalog = waba_catalogs["data"][0]["id"]
    print(f"\n  Usando catalog_id del WABA: {correct_catalog}")
    
    # Intentar enviar con este ID
    print(f"\n  Enviando producto a {DESTINATARIO}...")
    url = f"{BASE_URL}/{PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": DESTINATARIO,
        "type": "interactive",
        "interactive": {
            "type": "product",
            "body": {
                "text": "Mira este producto!"
            },
            "action": {
                "catalog_id": correct_catalog,
                "product_retailer_id": "3lrmu32i5v"
            }
        }
    }
    r = requests.post(url, headers=headers, json=payload)
    data = r.json()
    if "error" in data:
        print(f"  Error: {data['error'].get('message')}")
        print(f"  Code: {data['error'].get('code')}")
        
        # Intentar con product ID en vez de retailer_id
        print("\n  Probando con product ID numerico en vez de retailer_id...")
        payload["interactive"]["action"]["product_retailer_id"] = "26413008211698462"
        r2 = requests.post(url, headers=headers, json=payload)
        data2 = r2.json()
        if "error" in data2:
            print(f"  Error: {data2['error'].get('message')}")
        else:
            print(f"  EXITO con product ID!")
            print(f"  {json.dumps(data2, indent=2)}")
    else:
        print(f"  EXITO!")
        print(f"  {json.dumps(data, indent=2)}")

print("\n" + "=" * 60)
print("COMPLETADO")
print("=" * 60)
