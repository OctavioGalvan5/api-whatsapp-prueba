"""Verificar catalogo de la nueva cuenta de WhatsApp."""
import requests, json, os
from dotenv import load_dotenv
load_dotenv(override=True)

ACCESS_TOKEN = os.getenv("WHATSAPP_API_TOKEN")
WABA_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
BASE_URL = "https://graph.facebook.com/v21.0"
headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}

print(f"WABA ID: {WABA_ID}")
print(f"Phone Number ID: {PHONE_NUMBER_ID}")
print(f"Token: {ACCESS_TOKEN[:20]}...\n")

# 1. Info del numero
print("=" * 60)
print("1. INFO DEL NUMERO")
print("=" * 60)
url = f"{BASE_URL}/{PHONE_NUMBER_ID}"
params = {"fields": "verified_name,display_phone_number,quality_rating,platform_type,name_status"}
r = requests.get(url, headers=headers, params=params)
data = r.json()
if "error" in data:
    print(f"  Error: {data['error'].get('message')}")
else:
    for k, v in data.items():
        if k != "id":
            print(f"  {k}: {v}")

# 2. Catalogos conectados al WABA
print("\n" + "=" * 60)
print("2. CATALOGOS CONECTADOS AL WABA")
print("=" * 60)
url = f"{BASE_URL}/{WABA_ID}/product_catalogs"
r = requests.get(url, headers=headers)
data = r.json()
if "error" in data:
    print(f"  Error: {data['error'].get('message')}")
else:
    catalogs = data.get("data", [])
    if not catalogs:
        print("  No hay catalogos conectados a este WABA")
    for c in catalogs:
        print(f"  Catalogo: {c.get('name', 'N/A')} (ID: {c.get('id')})")
        
        # Ver productos de cada catalogo
        url2 = f"{BASE_URL}/{c['id']}/products"
        params2 = {"fields": "id,name,price,retailer_id,availability,review_status,visibility"}
        r2 = requests.get(url2, headers=headers, params=params2)
        prods = r2.json().get("data", [])
        print(f"  Productos: {len(prods)}")
        for p in prods:
            status = p.get('review_status', 'pendiente') or 'pendiente'
            print(f"    - {p.get('name')} | {p.get('price','N/A')} | review: {status} | visible: {p.get('visibility','?')}")

# 3. Commerce settings
print("\n" + "=" * 60)
print("3. COMMERCE SETTINGS DEL NUMERO")
print("=" * 60)
url = f"{BASE_URL}/{PHONE_NUMBER_ID}/whatsapp_commerce_settings"
r = requests.get(url, headers=headers)
data = r.json()
if "error" in data:
    print(f"  Error: {data['error'].get('message')}")
else:
    settings = data.get("data", [])
    if not settings:
        print("  No hay commerce settings configurados")
    for s in settings:
        print(f"  ID: {s.get('id')}")
        print(f"  Catalogo visible: {s.get('is_catalog_visible')}")
        print(f"  Carrito habilitado: {s.get('is_cart_enabled')}")

print("\n" + "=" * 60)
print("COMPLETADO")
print("=" * 60)
