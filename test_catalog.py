"""
Script de prueba para obtener productos del catálogo de WhatsApp Business
via Meta Graph API.
"""
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

# Configuración
CATALOG_ID = "1990424264879603"
ACCESS_TOKEN = os.getenv("WHATSAPP_API_TOKEN")
WABA_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
GRAPH_API_VERSION = "v21.0"
BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}


def get_catalog_products():
    """Obtener todos los productos del catálogo"""
    print("=" * 60)
    print("📦 OBTENIENDO PRODUCTOS DEL CATÁLOGO")
    print("=" * 60)
    
    url = f"{BASE_URL}/{CATALOG_ID}/products"
    params = {
        "fields": "id,name,description,price,currency,image_url,url,retailer_id,availability",
    }
    
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    
    if "error" in data:
        print(f"\n❌ Error: {data['error'].get('message', 'Error desconocido')}")
        print(f"   Código: {data['error'].get('code', 'N/A')}")
        print(f"   Tipo: {data['error'].get('type', 'N/A')}")
        return None
    
    products = data.get("data", [])
    print(f"\n✅ Se encontraron {len(products)} producto(s)\n")
    
    for i, product in enumerate(products, 1):
        print(f"  ── Producto #{i} ──")
        print(f"  ID:           {product.get('id', 'N/A')}")
        print(f"  Nombre:       {product.get('name', 'N/A')}")
        print(f"  Descripción:  {product.get('description', 'N/A')}")
        print(f"  Precio:       {product.get('price', 'N/A')} {product.get('currency', '')}")
        print(f"  Retailer ID:  {product.get('retailer_id', 'N/A')}")
        print(f"  Disponible:   {product.get('availability', 'N/A')}")
        print(f"  Imagen URL:   {product.get('image_url', 'N/A')}")
        print(f"  URL:          {product.get('url', 'N/A')}")
        print()
    
    # Paginación
    paging = data.get("paging", {})
    if paging.get("next"):
        print(f"  📄 Hay más productos (paginación disponible)")
    
    return data


def get_catalog_info():
    """Obtener información general del catálogo"""
    print("=" * 60)
    print("ℹ️  INFORMACIÓN DEL CATÁLOGO")
    print("=" * 60)
    
    url = f"{BASE_URL}/{CATALOG_ID}"
    params = {
        "fields": "id,name,product_count,vertical",
    }
    
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    
    if "error" in data:
        print(f"\n❌ Error: {data['error'].get('message', 'Error desconocido')}")
        print(f"   Código: {data['error'].get('code', 'N/A')}")
        print(f"   Tipo: {data['error'].get('type', 'N/A')}")
        return None
    
    print(f"\n  Catálogo ID:       {data.get('id', 'N/A')}")
    print(f"  Nombre:            {data.get('name', 'N/A')}")
    print(f"  Cant. Productos:   {data.get('product_count', 'N/A')}")
    print(f"  Vertical:          {data.get('vertical', 'N/A')}")
    print()
    
    return data


def get_connected_catalogs():
    """Obtener catálogos conectados al WABA"""
    print("=" * 60)
    print("🔗 CATÁLOGOS CONECTADOS AL WABA")
    print("=" * 60)
    
    url = f"{BASE_URL}/{WABA_ID}/product_catalogs"
    
    response = requests.get(url, headers=headers)
    data = response.json()
    
    if "error" in data:
        print(f"\n❌ Error: {data['error'].get('message', 'Error desconocido')}")
        print(f"   Código: {data['error'].get('code', 'N/A')}")
        print(f"   Tipo: {data['error'].get('type', 'N/A')}")
        return None
    
    catalogs = data.get("data", [])
    print(f"\n✅ Se encontraron {len(catalogs)} catálogo(s) conectado(s)\n")
    
    for i, catalog in enumerate(catalogs, 1):
        print(f"  ── Catálogo #{i} ──")
        print(f"  ID:     {catalog.get('id', 'N/A')}")
        print(f"  Nombre: {catalog.get('name', 'N/A')}")
        print()
    
    return data


if __name__ == "__main__":
    print("\n🚀 TEST DE API DE CATÁLOGO - WhatsApp Business\n")
    
    # 1. Info del catálogo
    get_catalog_info()
    
    # 2. Catálogos conectados al WABA
    get_connected_catalogs()
    
    # 3. Productos del catálogo
    get_catalog_products()
    
    print("=" * 60)
    print("✅ Test completado")
    print("=" * 60)
