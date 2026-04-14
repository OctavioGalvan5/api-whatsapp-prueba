"""
Reintentar vinculacion y envio de productos con el token con permisos de catalogo.
"""
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

# Token con permisos de catalogo
ACCESS_TOKEN = "EAARKWBZAyoEIBRNRThC3kbgpZBiBHJDy4oyHuYRm2vOUx2syqi80bvx2vHdaGhCFmLRAKlxfrpu48Iikk5fqDbiY1gcAAUwX6NkqPJujFy95PRfhmXi4kOzuPg7C7BNrLRRuQkKZBQITHgOG41gFbTY4HhXTWde1zLqxNYhoa7r2oNJXTr9kFaz9TXqNQZDZD"

WABA_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
CATALOG_ID = "1990424264879603"
GRAPH_API_VERSION = "v21.0"
BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

DESTINATARIO = "5493872226660"


def step1_verify_token_permissions():
    """Verificar que permisos tiene este token"""
    print("=" * 60)
    print("PASO 1: Verificar permisos del token")
    print("=" * 60)
    
    url = f"{BASE_URL}/debug_token"
    params = {"input_token": ACCESS_TOKEN, "access_token": ACCESS_TOKEN}
    
    response = requests.get(url, params=params)
    data = response.json()
    
    if "error" in data:
        print(f"  Error: {data['error'].get('message')}")
    else:
        token_data = data.get("data", {})
        scopes = token_data.get("scopes", [])
        print(f"  Scopes: {', '.join(scopes)}")
        print(f"  App ID: {token_data.get('app_id', 'N/A')}")
        print(f"  Tipo: {token_data.get('type', 'N/A')}")
        print(f"  Valido: {token_data.get('is_valid', 'N/A')}")
    return data


def step2_connect_catalog_to_waba():
    """Conectar catalogo al WABA"""
    print("\n" + "=" * 60)
    print("PASO 2: Conectar catalogo al WABA")
    print("=" * 60)
    
    url = f"{BASE_URL}/{WABA_ID}/product_catalogs"
    payload = {"catalog_id": CATALOG_ID}
    
    response = requests.post(url, headers=headers, json=payload)
    data = response.json()
    
    if "error" in data:
        print(f"  Error: {data['error'].get('message')}")
        print(f"  Detalle: {data['error'].get('error_user_msg', '')}")
    else:
        print(f"  Respuesta: {json.dumps(data, indent=2)}")
    return data


def step3_set_commerce_settings():
    """Vincular catalogo al numero"""
    print("\n" + "=" * 60)
    print("PASO 3: Configurar catalogo en el numero de telefono")
    print("=" * 60)
    
    url = f"{BASE_URL}/{PHONE_NUMBER_ID}/whatsapp_commerce_settings"
    payload = {
        "is_catalog_visible": True,
        "is_cart_enabled": True,
        "catalog_id": CATALOG_ID,
    }
    
    response = requests.post(url, headers=headers, json=payload)
    data = response.json()
    print(f"  Respuesta: {json.dumps(data, indent=2)}")
    return data


def step4_verify_commerce():
    """Verificar commerce settings"""
    print("\n" + "=" * 60)
    print("PASO 4: Verificar configuracion")
    print("=" * 60)
    
    url = f"{BASE_URL}/{PHONE_NUMBER_ID}/whatsapp_commerce_settings"
    response = requests.get(url, headers=headers)
    data = response.json()
    print(f"  Commerce settings: {json.dumps(data, indent=2)}")
    return data


def step5_send_single_product():
    """Enviar un producto"""
    print("\n" + "=" * 60)
    print(f"PASO 5: Enviando producto individual a {DESTINATARIO}")
    print("=" * 60)
    
    url = f"{BASE_URL}/{PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": DESTINATARIO,
        "type": "interactive",
        "interactive": {
            "type": "product",
            "body": {
                "text": "Mira este producto que tenemos disponible!"
            },
            "footer": {
                "text": "Toca para ver detalles"
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
        print(f"  Detalle: {json.dumps(data['error'], indent=2)}")
    else:
        print(f"  EXITO! Mensaje enviado!")
        print(f"  Message ID: {data.get('messages', [{}])[0].get('id', 'N/A')}")
    return data


def step6_send_product_list():
    """Enviar lista de productos"""
    print("\n" + "=" * 60)
    print(f"PASO 6: Enviando lista de productos a {DESTINATARIO}")
    print("=" * 60)
    
    url = f"{BASE_URL}/{PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": DESTINATARIO,
        "type": "interactive",
        "interactive": {
            "type": "product_list",
            "header": {
                "type": "text",
                "text": "Nuestros Productos"
            },
            "body": {
                "text": "Estos son los productos disponibles. Toca para ver detalles."
            },
            "footer": {
                "text": "Estudio Juridico Toyos y Espin"
            },
            "action": {
                "catalog_id": CATALOG_ID,
                "sections": [
                    {
                        "title": "Productos Disponibles",
                        "product_items": [
                            {"product_retailer_id": "3lrmu32i5v"},
                            {"product_retailer_id": "1j3phfqxw6"},
                            {"product_retailer_id": "0vgedz0bnv"},
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
        print(f"  Detalle: {json.dumps(data['error'], indent=2)}")
    else:
        print(f"  EXITO! Lista de productos enviada!")
        print(f"  Message ID: {data.get('messages', [{}])[0].get('id', 'N/A')}")
    return data


if __name__ == "__main__":
    print(f"\nCatalog ID: {CATALOG_ID}")
    print(f"Phone Number ID: {PHONE_NUMBER_ID}")
    print(f"WABA ID: {WABA_ID}")
    print(f"Destinatario: {DESTINATARIO}\n")
    
    step1_verify_token_permissions()
    step2_connect_catalog_to_waba()
    step3_set_commerce_settings()
    step4_verify_commerce()
    step5_send_single_product()
    step6_send_product_list()
    
    print("\n" + "=" * 60)
    print("COMPLETADO")
    print("=" * 60)
