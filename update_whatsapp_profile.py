"""
Script para actualizar el perfil de WhatsApp Business via API
Actualiza descripción, dirección, categoría, sitio web, email, etc.
"""

import requests
import json

# Configuración
PHONE_NUMBER_ID = "TU_PHONE_NUMBER_ID"  # El ID del número de teléfono
ACCESS_TOKEN = "TU_ACCESS_TOKEN"  # Tu token de acceso

# URL del endpoint
url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/whatsapp_business_profile"

# Headers
headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

# ============================================
# FUNCIÓN 1: Actualizar descripción (About)
# ============================================
def update_description(description):
    """
    Actualiza la descripción del perfil de WhatsApp Business
    Máximo 256 caracteres
    """
    data = {
        "messaging_product": "whatsapp",
        "about": description
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        print("✅ Descripción actualizada correctamente")
        print(response.json())
    else:
        print(f"❌ Error al actualizar descripción: {response.status_code}")
        print(response.text)

    return response


# ============================================
# FUNCIÓN 2: Actualizar información completa
# ============================================
def update_full_profile(profile_data):
    """
    Actualiza múltiples campos del perfil a la vez

    Campos disponibles:
    - about: Descripción del negocio (máx 256 caracteres)
    - address: Dirección física
    - description: Descripción larga (máx 512 caracteres)
    - email: Email de contacto
    - vertical: Categoría del negocio
    - websites: Lista de sitios web (máx 2)
    """
    data = {
        "messaging_product": "whatsapp",
        **profile_data
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        print("✅ Perfil actualizado correctamente")
        print(json.dumps(response.json(), indent=2))
    else:
        print(f"❌ Error al actualizar perfil: {response.status_code}")
        print(response.text)

    return response


# ============================================
# FUNCIÓN 3: Obtener información actual del perfil
# ============================================
def get_current_profile():
    """
    Obtiene la información actual del perfil de WhatsApp Business
    """
    get_url = f"{url}?fields=about,address,description,email,profile_picture_url,websites,vertical"

    response = requests.get(get_url, headers=headers)

    if response.status_code == 200:
        print("✅ Información del perfil obtenida:")
        print(json.dumps(response.json(), indent=2))
        return response.json()
    else:
        print(f"❌ Error al obtener perfil: {response.status_code}")
        print(response.text)
        return None


# ============================================
# EJEMPLOS DE USO
# ============================================

if __name__ == "__main__":
    print("=" * 60)
    print("SCRIPT DE ACTUALIZACIÓN DE PERFIL DE WHATSAPP BUSINESS")
    print("=" * 60)
    print()

    # Ejemplo 1: Ver perfil actual
    print("1️⃣  Obteniendo perfil actual...")
    print("-" * 60)
    get_current_profile()
    print()

    # Ejemplo 2: Actualizar solo la descripción
    print("2️⃣  Actualizando descripción...")
    print("-" * 60)
    nueva_descripcion = "Caja de Abogados de Salta - Atención al afiliado. Consultas sobre beneficios, subsidios y trámites."
    # update_description(nueva_descripcion)  # Descomenta para ejecutar
    print()

    # Ejemplo 3: Actualizar información completa
    print("3️⃣  Ejemplo de actualización completa...")
    print("-" * 60)

    profile_complete = {
        "about": "Caja de Abogados de Salta - Asistencia a afiliados",
        "address": "Dirección de la delegación central, Salta Capital",
        "description": "Institución que brinda servicios y beneficios a abogados colegiados de la provincia de Salta. Ofrecemos subsidios, préstamos, seguro de vida y servicio de sepelio.",
        "email": "mesadeentrada@cajaabogadossalta.com.ar",
        "vertical": "PROF_SERVICES",  # Categoría: Servicios Profesionales
        "websites": [
            "https://www.cajaabogadossalta.com.ar"
        ]
    }

    # update_full_profile(profile_complete)  # Descomenta para ejecutar
    print()

    print("=" * 60)
    print("📌 NOTAS IMPORTANTES:")
    print("=" * 60)
    print("• El nombre del negocio NO se puede cambiar via API")
    print("• La foto de perfil NO se puede cambiar via API")
    print("• Para cambiar nombre/foto: usa Meta Business Manager")
    print("• La descripción tiene un máximo de 256 caracteres")
    print("• Puedes agregar hasta 2 sitios web")
    print()


# ============================================
# CATEGORÍAS DE NEGOCIO DISPONIBLES (vertical)
# ============================================
"""
Algunas categorías comunes:

- AUTO: Automotriz
- BEAUTY: Belleza
- APPAREL: Ropa y accesorios
- EDU: Educación
- ENTERTAIN: Entretenimiento
- EVENT_PLAN: Planificación de eventos
- FINANCE: Finanzas
- GROCERY: Supermercado
- GOVT: Gobierno
- HOTEL: Hotel
- HEALTH: Salud
- NONPROFIT: Sin fines de lucro
- PROF_SERVICES: Servicios profesionales ✅ (Recomendado para ustedes)
- RETAIL: Retail
- TRAVEL: Viajes
- RESTAURANT: Restaurante
- NOT_A_BIZ: No es un negocio
"""
