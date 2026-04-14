"""
Diagnostico completo del catalogo - verificar por que no se ve en el celular.
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


def check_phone_profile():
    """Ver perfil de negocio del numero"""
    print("=" * 60)
    print("1. PERFIL DE NEGOCIO DEL NUMERO")
    print("=" * 60)
    
    url = f"{BASE_URL}/{PHONE_NUMBER_ID}"
    params = {
        "fields": "verified_name,display_phone_number,quality_rating,platform_type,name_status,is_official_business_account"
    }
    
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    
    if "error" in data:
        print(f"  Error: {data['error'].get('message')}")
    else:
        print(f"  Nombre verificado: {data.get('verified_name', 'N/A')}")
        print(f"  Telefono: {data.get('display_phone_number', 'N/A')}")
        print(f"  Calidad: {data.get('quality_rating', 'N/A')}")
        print(f"  Plataforma: {data.get('platform_type', 'N/A')}")
        print(f"  Estado nombre: {data.get('name_status', 'N/A')}")
        print(f"  Cuenta oficial: {data.get('is_official_business_account', 'N/A')}")
    return data


def check_catalog_status():
    """Verificar estado y compliance del catalogo"""
    print("\n" + "=" * 60)
    print("2. ESTADO DEL CATALOGO")
    print("=" * 60)
    
    url = f"{BASE_URL}/{CATALOG_ID}"
    params = {
        "fields": "id,name,product_count,vertical,is_catalog_segment,da_display_settings"
    }
    
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    
    if "error" in data:
        print(f"  Error: {data['error'].get('message')}")
    else:
        for key, value in data.items():
            print(f"  {key}: {value}")
    return data


def check_products_compliance():
    """Ver si los productos tienen problemas de compliance"""
    print("\n" + "=" * 60)
    print("3. PRODUCTOS - ESTADO DE APROBACION")
    print("=" * 60)
    
    url = f"{BASE_URL}/{CATALOG_ID}/products"
    params = {
        "fields": "id,name,review_status,review_rejection_reasons,visibility,errors",
    }
    
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    
    if "error" in data:
        print(f"  Error: {data['error'].get('message')}")
    else:
        products = data.get("data", [])
        for p in products:
            print(f"\n  Producto: {p.get('name', 'N/A')}")
            print(f"    ID: {p.get('id')}")
            print(f"    Review status: {p.get('review_status', 'N/A')}")
            print(f"    Visibilidad: {p.get('visibility', 'N/A')}")
            rejection = p.get('review_rejection_reasons', [])
            if rejection:
                print(f"    RECHAZADO: {rejection}")
            errors = p.get('errors', [])
            if errors:
                print(f"    ERRORES: {errors}")
    return data


def check_waba_compliance():
    """Verificar estado del WABA"""
    print("\n" + "=" * 60)
    print("4. ESTADO DEL WABA")
    print("=" * 60)
    
    url = f"{BASE_URL}/{WABA_ID}"
    params = {
        "fields": "id,name,account_review_status,message_template_namespace,on_behalf_of_business_info"
    }
    
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    
    if "error" in data:
        print(f"  Error: {data['error'].get('message')}")
    else:
        for key, value in data.items():
            print(f"  {key}: {value}")
    return data


def check_commerce_settings_detail():
    """Ver commerce settings con mas detalle"""
    print("\n" + "=" * 60)
    print("5. COMMERCE SETTINGS (DETALLE)")
    print("=" * 60)
    
    url = f"{BASE_URL}/{PHONE_NUMBER_ID}/whatsapp_commerce_settings"
    params = {
        "fields": "is_cart_enabled,is_catalog_visible,id"
    }
    
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    
    if "error" in data:
        print(f"  Error: {data['error'].get('message')}")
    else:
        settings = data.get("data", [])
        for s in settings:
            print(f"  ID: {s.get('id')}")
            print(f"  Catalogo visible: {s.get('is_catalog_visible')}")
            print(f"  Carrito habilitado: {s.get('is_cart_enabled')}")
            
            # Importante: ver si el ID del commerce coincide con el catalog
            commerce_id = s.get('id')
            if commerce_id != CATALOG_ID:
                print(f"\n  !! ATENCION: El Commerce ID ({commerce_id}) NO coincide con tu Catalog ID ({CATALOG_ID})")
                print(f"  -> Puede que haya OTRO catalogo vinculado al numero")
    return data


if __name__ == "__main__":
    print("\nDIAGNOSTICO COMPLETO DEL CATALOGO")
    print("=" * 60)
    
    check_phone_profile()
    check_catalog_status()
    check_products_compliance()
    check_waba_compliance()
    check_commerce_settings_detail()
    
    print("\n" + "=" * 60)
    print("NOTAS IMPORTANTES:")
    print("=" * 60)
    print("""
  - Si platform_type es 'CLOUD_API', el catalogo NO se ve
    desde la app WhatsApp Business del celular. Solo se ve
    cuando un CLIENTE abre tu perfil desde su WhatsApp normal.
    
  - Para probarlo: pedi a alguien que te mande un mensaje
    desde OTRO numero, luego que toque tu nombre de negocio
    en el chat -> ahi deberia ver el catalogo.
    
  - Si los productos tienen review_status distinto de 'approved',
    Meta aun no los aprobo y no seran visibles.
    
  - Tambien podes enviar productos via mensaje interactivo
    (Single Product / Multi Product message) usando la API.
""")
