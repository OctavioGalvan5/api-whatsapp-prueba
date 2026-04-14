"""
Script para verificar y vincular el catálogo al número de teléfono específico.
"""
import requests
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


def check_phone_commerce_settings():
    """Verificar la configuracion de comercio del numero de telefono"""
    print("=" * 60)
    print("1. VERIFICANDO COMMERCE SETTINGS DEL TELEFONO")
    print("=" * 60)
    
    url = f"{BASE_URL}/{PHONE_NUMBER_ID}/whatsapp_commerce_settings"
    
    response = requests.get(url, headers=headers)
    data = response.json()
    
    if "error" in data:
        print(f"\n  Error: {data['error'].get('message', 'Error desconocido')}")
        print(f"  Codigo: {data['error'].get('code', 'N/A')}")
        print(f"  -> Esto puede significar que NO hay catalogo vinculado al numero.")
    else:
        print(f"\n  Respuesta: {data}")
    
    return data


def enable_cart_on_phone():
    """Habilitar el carrito y vincular catalogo al numero de telefono"""
    print("\n" + "=" * 60)
    print("2. HABILITANDO CATALOGO EN EL NUMERO DE TELEFONO")
    print("=" * 60)
    
    url = f"{BASE_URL}/{PHONE_NUMBER_ID}/whatsapp_commerce_settings"
    
    payload = {
        "is_catalog_visible": True,
        "is_cart_enabled": True,
    }
    
    response = requests.post(url, headers=headers, json=payload)
    data = response.json()
    
    if "error" in data:
        print(f"\n  Error: {data['error'].get('message', 'Error desconocido')}")
        print(f"  Codigo: {data['error'].get('code', 'N/A')}")
    else:
        print(f"\n  Respuesta: {data}")
        if data.get("success"):
            print("  -> Catalogo habilitado exitosamente en el numero!")
    
    return data


def verify_after():
    """Verificar estado despues de habilitar"""
    print("\n" + "=" * 60)
    print("3. VERIFICACION FINAL")
    print("=" * 60)
    
    url = f"{BASE_URL}/{PHONE_NUMBER_ID}/whatsapp_commerce_settings"
    response = requests.get(url, headers=headers)
    data = response.json()
    
    if "error" in data:
        print(f"\n  Error: {data['error'].get('message')}")
    else:
        print(f"\n  Respuesta completa: {data}")
        commerce = data.get("data", [{}])
        if commerce:
            for setting in commerce:
                print(f"  Catalogo visible: {setting.get('is_catalog_visible', 'N/A')}")
                print(f"  Carrito habilitado: {setting.get('is_cart_enabled', 'N/A')}")
                print(f"  Catalogo ID: {setting.get('id', 'N/A')}")
    
    return data


if __name__ == "__main__":
    print(f"\nPhone Number ID: {PHONE_NUMBER_ID}")
    print(f"WABA ID: {WABA_ID}")
    print(f"Catalog ID: {CATALOG_ID}\n")
    
    # Paso 1: Verificar estado actual
    check_phone_commerce_settings()
    
    # Paso 2: Habilitar catalogo en el telefono
    enable_cart_on_phone()
    
    # Paso 3: Verificar despues
    verify_after()
    
    print("\n" + "=" * 60)
    print("COMPLETADO")
    print("=" * 60)
