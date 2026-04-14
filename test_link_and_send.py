"""
Vincular el catalogo correcto al numero de telefono y reintentar enviar productos.
"""
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv("WHATSAPP_API_TOKEN")
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


def step1_connect_catalog_to_waba():
    """Asegurarse que el catalogo esta conectado al WABA"""
    print("=" * 60)
    print("PASO 1: Conectar catalogo al WABA")
    print("=" * 60)
    
    url = f"{BASE_URL}/{WABA_ID}/product_catalogs"
    payload = {"catalog_id": CATALOG_ID}
    
    response = requests.post(url, headers=headers, json=payload)
    data = response.json()
    print(f"  Respuesta: {json.dumps(data, indent=2)}")
    return data


def step2_set_commerce_settings():
    """Configurar el catalogo en el numero de telefono con catalog_id explicito"""
    print("\n" + "=" * 60)
    print("PASO 2: Vincular catalogo al numero de telefono")
    print("=" * 60)
    
    url = f"{BASE_URL}/{PHONE_NUMBER_ID}/whatsapp_commerce_settings"
    
    # Intentar con catalog_id explicito
    payload = {
        "is_catalog_visible": True,
        "is_cart_enabled": True,
        "catalog_id": CATALOG_ID,
    }
    
    response = requests.post(url, headers=headers, json=payload)
    data = response.json()
    print(f"  Respuesta: {json.dumps(data, indent=2)}")
    return data


def step3_verify():
    """Verificar que quedo bien"""
    print("\n" + "=" * 60)
    print("PASO 3: Verificar configuracion")
    print("=" * 60)
    
    url = f"{BASE_URL}/{PHONE_NUMBER_ID}/whatsapp_commerce_settings"
    response = requests.get(url, headers=headers)
    data = response.json()
    print(f"  Commerce settings: {json.dumps(data, indent=2)}")
    return data


def step4_send_single_product():
    """Intentar enviar un producto"""
    print("\n" + "=" * 60)
    print(f"PASO 4: Enviando producto a {DESTINATARIO}")
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
        print(f"\n  Error: {data['error'].get('message')}")
        print(f"  Detalle: {json.dumps(data['error'], indent=2)}")
    else:
        print(f"\n  EXITO! Mensaje enviado!")
        print(f"  Message ID: {data.get('messages', [{}])[0].get('id', 'N/A')}")
    
    return data


def step5_send_product_list():
    """Intentar enviar lista de productos"""
    print("\n" + "=" * 60)
    print(f"PASO 5: Enviando lista de productos a {DESTINATARIO}")
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
                "text": "Estos son los productos disponibles:"
            },
            "footer": {
                "text": "Estudio Juridico Toyos y Espin"
            },
            "action": {
                "catalog_id": CATALOG_ID,
                "sections": [
                    {
                        "title": "Productos",
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
        print(f"\n  Error: {data['error'].get('message')}")
        print(f"  Detalle: {json.dumps(data['error'], indent=2)}")
    else:
        print(f"\n  EXITO! Lista de productos enviada!")
        print(f"  Message ID: {data.get('messages', [{}])[0].get('id', 'N/A')}")
    
    return data


if __name__ == "__main__":
    print(f"\nCatalog ID: {CATALOG_ID}")
    print(f"Phone Number ID: {PHONE_NUMBER_ID}")
    print(f"Destinatario: {DESTINATARIO}\n")
    
    step1_connect_catalog_to_waba()
    step2_set_commerce_settings()
    step3_verify()
    step4_send_single_product()
    step5_send_product_list()
    
    print("\n" + "=" * 60)
    print("COMPLETADO")
    print("=" * 60)
