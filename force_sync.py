"""
Ultimo intento: Borrar productos y recrearlos via Batch API para forzar re-indexacion.
Si eso no funciona, crear un catalogo nuevo desde la API.
"""
import requests, json, os, time
from dotenv import load_dotenv
load_dotenv(override=True)

TOKEN = os.getenv("WHATSAPP_API_TOKEN")
WABA = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
PHONE = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
CATALOG_ID = "1990424264879603"
BASE = "https://graph.facebook.com/v21.0"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
DEST = "5493872226660"

productos = [
    {
        "retailer_id": "matamosquitos-001",
        "data": {
            "name": "Matamosquitos Premium",
            "description": "Mata mosquitos de alta calidad",
            "availability": "in stock",
            "price": 1500000,
            "currency": "ARS",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Mosquito_Zapper.jpg/640px-Mosquito_Zapper.jpg",
            "url": "https://countrylife.online/",
            "category": "home"
        }
    },
    {
        "retailer_id": "desengrasante-001",
        "data": {
            "name": "Desengrasante Potente",
            "description": "Desengrasante industrial de alta potencia",
            "availability": "in stock",
            "price": 100000,
            "currency": "ARS",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/85/Smiley.svg/200px-Smiley.svg.png",
            "url": "https://countrylife.online/",
            "category": "home"
        }
    }
]


def step1_delete_old_products():
    """Borrar productos viejos"""
    print("PASO 1: Borrando productos viejos...")
    
    batch = [
        {"method": "DELETE", "retailer_id": "3lrmu32i5v"},
        {"method": "DELETE", "retailer_id": "1j3phfqxw6"},
        {"method": "DELETE", "retailer_id": "0vgedz0bnv"},
    ]
    
    r = requests.post(f"{BASE}/{CATALOG_ID}/batch", headers=H,
        data={"requests": json.dumps(batch), "item_type": "PRODUCT_ITEM"})
    print(f"  {json.dumps(r.json(), indent=2)}")
    return r.json()


def step2_create_new_products():
    """Crear productos nuevos"""
    print("\nPASO 2: Creando productos nuevos...")
    
    batch = []
    for p in productos:
        batch.append({
            "method": "CREATE",
            "retailer_id": p["retailer_id"],
            "data": p["data"]
        })
    
    r = requests.post(f"{BASE}/{CATALOG_ID}/batch", headers=H,
        data={"requests": json.dumps(batch), "item_type": "PRODUCT_ITEM"})
    print(f"  {json.dumps(r.json(), indent=2)}")
    return r.json()


def step3_verify():
    """Verificar productos"""
    print("\nPASO 3: Verificando productos (esperando 5 seg)...")
    time.sleep(5)
    
    r = requests.get(f"{BASE}/{CATALOG_ID}/products", headers=H,
        params={"fields": "id,name,retailer_id,price,availability,review_status"})
    data = r.json()
    prods = data.get("data", [])
    print(f"  Productos: {len(prods)}")
    for p in prods:
        print(f"    - {p.get('name')} | {p.get('retailer_id')} | {p.get('availability')} | review: {p.get('review_status', '?')}")
    return prods


def step4_test_send(prods):
    """Intentar enviar"""
    if not prods:
        print("\nNo hay productos para enviar")
        return
    
    retailer_id = prods[0].get("retailer_id", productos[0]["retailer_id"])
    print(f"\nPASO 4: Enviando producto '{retailer_id}' a {DEST}...")
    
    payload = {
        "messaging_product": "whatsapp",
        "to": DEST,
        "type": "interactive",
        "interactive": {
            "type": "product",
            "body": {"text": "Mira este producto!"},
            "action": {
                "catalog_id": CATALOG_ID,
                "product_retailer_id": retailer_id
            }
        }
    }
    r = requests.post(f"{BASE}/{PHONE}/messages", headers=H, json=payload)
    data = r.json()
    if "error" in data:
        print(f"  Error: {data['error'].get('message')} (code: {data['error'].get('code')})")
        print(f"  -> Todavia no sincronizo. Meta necesita mas tiempo.")
    else:
        print(f"  EXITO! ID: {data.get('messages', [{}])[0].get('id')}")


if __name__ == "__main__":
    print(f"Catalog: {CATALOG_ID}")
    print(f"Phone: {PHONE}")
    print(f"WABA: {WABA}\n")
    
    step1_delete_old_products()
    step2_create_new_products()
    prods = step3_verify()
    step4_test_send(prods)
    
    print("\n" + "=" * 60)
    print("Si sigue sin funcionar, es cuestion de esperar.")
    print("Meta sincroniza catalogos en hasta 1-24 horas.")
    print("=" * 60)
