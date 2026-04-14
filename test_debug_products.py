"""
Debug: probar el envio de producto con mas detalle.
"""
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = "EAARKWBZAyoEIBRNRThC3kbgpZBiBHJDy4oyHuYRm2vOUx2syqi80bvx2vHdaGhCFmLRAKlxfrpu48Iikk5fqDbiY1gcAAUwX6NkqPJujFy95PRfhmXi4kOzuPg7C7BNrLRRuQkKZBQITHgOG41gFbTY4HhXTWde1zLqxNYhoa7r2oNJXTr9kFaz9TXqNQZDZD"

PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
CATALOG_ID = "1990424264879603"
BASE_URL = f"https://graph.facebook.com/v21.0"

headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

# CAMBIA ESTE NUMERO - tiene que ser OTRO numero, no el del negocio
DESTINATARIO = "5493874882011"


def test1_verify_catalog_linked():
    """Verificar que los catalogos estan bien conectados"""
    print("=" * 60)
    print("TEST 1: Catalogos del WABA")
    print("=" * 60)
    
    waba_id = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
    url = f"{BASE_URL}/{waba_id}/product_catalogs"
    response = requests.get(url, headers=headers)
    data = response.json()
    print(f"  Catalogos vinculados: {json.dumps(data, indent=2)}")
    
    # Verificar si nuestro catalog_id esta en la lista
    catalogs = data.get("data", [])
    found = any(c.get("id") == CATALOG_ID for c in catalogs)
    print(f"\n  Catalogo {CATALOG_ID} vinculado al WABA: {'SI' if found else 'NO'}")
    return data


def test2_get_product_details():
    """Ver detalle exacto del producto que vamos a enviar"""
    print("\n" + "=" * 60)
    print("TEST 2: Detalle del producto a enviar")
    print("=" * 60)
    
    url = f"{BASE_URL}/{CATALOG_ID}/products"
    params = {"fields": "id,name,retailer_id,availability,review_status,visibility,errors"}
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    
    for p in data.get("data", []):
        print(f"\n  Nombre: {p.get('name')}")
        print(f"  retailer_id: {p.get('retailer_id')}")
        print(f"  availability: {p.get('availability')}")
        print(f"  review_status: {p.get('review_status', 'N/A')}")
        print(f"  visibility: {p.get('visibility', 'N/A')}")
        errors = p.get("errors", [])
        if errors:
            print(f"  ERRORES: {errors}")
    return data


def test3_send_text_first():
    """Enviar texto normal primero para verificar que el numero funciona"""
    print("\n" + "=" * 60)
    print(f"TEST 3: Enviar texto normal a {DESTINATARIO}")
    print("=" * 60)
    
    url = f"{BASE_URL}/{PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": DESTINATARIO,
        "type": "text",
        "text": {"body": "Test de conexion - probando catalogo"}
    }
    
    response = requests.post(url, headers=headers, json=payload)
    data = response.json()
    
    if "error" in data:
        print(f"  Error: {data['error'].get('message')}")
        print(f"  -> El numero destino puede no estar en ventana de 24hs")
    else:
        print(f"  Texto enviado OK!")
        print(f"  Message ID: {data.get('messages', [{}])[0].get('id')}")
    return data


def test4_send_product_minimal():
    """Enviar producto con payload minimo"""
    print("\n" + "=" * 60)
    print(f"TEST 4: Enviar producto (payload minimo)")
    print("=" * 60)
    
    url = f"{BASE_URL}/{PHONE_NUMBER_ID}/messages"
    
    # Payload lo mas simple posible
    payload = {
        "messaging_product": "whatsapp",
        "to": DESTINATARIO,
        "type": "interactive",
        "interactive": {
            "type": "product",
            "body": {
                "text": "Mira este producto"
            },
            "action": {
                "catalog_id": CATALOG_ID,
                "product_retailer_id": "3lrmu32i5v"
            }
        }
    }
    
    response = requests.post(url, headers=headers, json=payload)
    data = response.json()
    
    if "error" in data:
        print(f"  Error: {data['error'].get('message')}")
        print(f"  Codigo: {data['error'].get('code')}")
        error_data = data['error'].get('error_data', {})
        print(f"  Details: {error_data.get('details', 'N/A')}")
        print(f"  Full: {json.dumps(data['error'], indent=2)}")
    else:
        print(f"  EXITO! Producto enviado!")
        print(f"  Message ID: {data.get('messages', [{}])[0].get('id')}")
    return data


def test5_send_product_list_minimal():
    """Enviar lista de productos con payload minimo"""
    print("\n" + "=" * 60)
    print(f"TEST 5: Enviar lista de productos (payload minimo)")
    print("=" * 60)
    
    url = f"{BASE_URL}/{PHONE_NUMBER_ID}/messages"
    
    payload = {
        "messaging_product": "whatsapp",
        "to": DESTINATARIO,
        "type": "interactive",
        "interactive": {
            "type": "product_list",
            "header": {
                "type": "text",
                "text": "Productos"
            },
            "body": {
                "text": "Mira nuestros productos"
            },
            "action": {
                "catalog_id": CATALOG_ID,
                "sections": [
                    {
                        "title": "Todos",
                        "product_items": [
                            {"product_retailer_id": "3lrmu32i5v"}
                        ]
                    }
                ]
            }
        }
    }
    
    response = requests.post(url, headers=headers, json=payload)
    data = response.json()
    
    if "error" in data:
        print(f"  Error: {data['error'].get('message')}")
        print(f"  Full: {json.dumps(data['error'], indent=2)}")
    else:
        print(f"  EXITO! Lista de productos enviada!")
        print(f"  Message ID: {data.get('messages', [{}])[0].get('id')}")
    return data


if __name__ == "__main__":
    print(f"\nDestinatario: {DESTINATARIO}")
    print(f"Catalog ID: {CATALOG_ID}")
    print(f"Phone Number ID: {PHONE_NUMBER_ID}\n")
    
    test1_verify_catalog_linked()
    test2_get_product_details()
    test3_send_text_first()
    test4_send_product_minimal()
    test5_send_product_list_minimal()
    
    print("\n" + "=" * 60)
    print("COMPLETADO")
    print("=" * 60)
