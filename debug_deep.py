"""Debug profundo - verificar ownership del catalogo vs WABA."""
import requests, json, os
from dotenv import load_dotenv
load_dotenv(override=True)

ACCESS_TOKEN = os.getenv("WHATSAPP_API_TOKEN")
WABA_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
CATALOG_ID = "1990424264879603"
BASE_URL = "https://graph.facebook.com/v21.0"
headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}

# 1. Ver a que Business pertenece el WABA
print("1. Business owner del WABA:")
r = requests.get(f"{BASE_URL}/{WABA_ID}", headers=headers, 
    params={"fields": "id,name,on_behalf_of_business_info,account_review_status"})
print(f"  {json.dumps(r.json(), indent=2)}")

# 2. Ver a que Business pertenece el catalogo
print("\n2. Business owner del catalogo:")
r = requests.get(f"{BASE_URL}/{CATALOG_ID}", headers=headers,
    params={"fields": "id,name,business,product_count"})
print(f"  {json.dumps(r.json(), indent=2)}")

# 3. Verificar el commerce settings con catalog_id asociado
print("\n3. Commerce settings - intentar con catalog_id:")
r = requests.get(f"{BASE_URL}/{PHONE_NUMBER_ID}/whatsapp_commerce_settings",
    headers=headers, params={"fields": "id,is_cart_enabled,is_catalog_visible"})
commerce = r.json()
print(f"  {json.dumps(commerce, indent=2)}")

commerce_id = commerce.get("data", [{}])[0].get("id", "")
print(f"\n  Commerce ID: {commerce_id}")
print(f"  Catalog ID:  {CATALOG_ID}")
print(f"  Match: {'SI' if commerce_id == CATALOG_ID else 'NO'}")

# 4. Intentar vincular el catalog_id explicitamente al commerce settings
print("\n4. Forzando vinculacion catalog_id al commerce settings...")
r = requests.post(f"{BASE_URL}/{PHONE_NUMBER_ID}/whatsapp_commerce_settings",
    headers=headers, json={"catalog_id": CATALOG_ID, "is_catalog_visible": True, "is_cart_enabled": True})
print(f"  {json.dumps(r.json(), indent=2)}")

# 5. Re-verificar
print("\n5. Re-verificando commerce settings:")
r = requests.get(f"{BASE_URL}/{PHONE_NUMBER_ID}/whatsapp_commerce_settings",
    headers=headers, params={"fields": "id,is_cart_enabled,is_catalog_visible"})
print(f"  {json.dumps(r.json(), indent=2)}")

# 6. Probar envio
print("\n6. Intentando envio de producto...")
DEST = "5493872226660"
payload = {
    "messaging_product": "whatsapp",
    "to": DEST,
    "type": "interactive",
    "interactive": {
        "type": "product",
        "body": {"text": "Producto de prueba"},
        "action": {
            "catalog_id": CATALOG_ID,
            "product_retailer_id": "3lrmu32i5v"
        }
    }
}
r = requests.post(f"{BASE_URL}/{PHONE_NUMBER_ID}/messages", headers=headers, json=payload)
data = r.json()
if "error" in data:
    print(f"  Error: {data['error'].get('message')} (code: {data['error'].get('code')})")
    
    # Si falla, probar SIN catalog_id (usa el default del commerce settings)
    print("\n7. Probando SIN catalog_id (default del commerce)...")
    del payload["interactive"]["action"]["catalog_id"]
    r2 = requests.post(f"{BASE_URL}/{PHONE_NUMBER_ID}/messages", headers=headers, json=payload)
    data2 = r2.json()
    if "error" in data2:
        print(f"  Error: {data2['error'].get('message')} (code: {data2['error'].get('code')})")
        print(f"  Detail: {json.dumps(data2['error'], indent=2)}")
    else:
        print(f"  EXITO sin catalog_id!")
        print(f"  {json.dumps(data2, indent=2)}")
else:
    print(f"  EXITO! {json.dumps(data, indent=2)}")
