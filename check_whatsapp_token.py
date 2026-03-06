"""
Script para verificar el estado del token de WhatsApp Business API
y diagnosticar problemas de conexión
"""

import requests
from config import Config

def check_token_validity():
    """Verifica si el token de acceso es válido."""

    print("=" * 60)
    print("DIAGNÓSTICO DE TOKEN DE WHATSAPP BUSINESS API")
    print("=" * 60)
    print()

    # Verificar configuración
    print("[1] Verificando configuracion...")
    print(f"   PHONE_NUMBER_ID: {Config.WHATSAPP_PHONE_NUMBER_ID}")
    print(f"   TOKEN (primeros 20 chars): {Config.WHATSAPP_API_TOKEN[:20]}..." if Config.WHATSAPP_API_TOKEN else "   TOKEN: No configurado")
    print()

    if not Config.WHATSAPP_API_TOKEN:
        print("[X] ERROR: No hay token configurado")
        return False

    # Probar endpoint debug_token para verificar validez
    print("[2] Verificando validez del token...")
    debug_url = f"https://graph.facebook.com/v22.0/debug_token"
    params = {
        "input_token": Config.WHATSAPP_API_TOKEN,
        "access_token": Config.WHATSAPP_API_TOKEN
    }

    try:
        response = requests.get(debug_url, params=params, timeout=10)
        data = response.json()

        if "data" in data:
            token_data = data["data"]
            print(f"   [OK] Token valido")
            print(f"   App ID: {token_data.get('app_id')}")
            print(f"   Tipo: {token_data.get('type')}")
            print(f"   Valido: {token_data.get('is_valid')}")

            # Verificar expiración
            if token_data.get('expires_at'):
                import datetime
                expires_at = datetime.datetime.fromtimestamp(token_data['expires_at'])
                print(f"   Expira: {expires_at}")

                if datetime.datetime.now() > expires_at:
                    print("   [!] ADVERTENCIA: El token ha expirado")
            else:
                print("   [OK] Token permanente (no expira)")

            print()
            return token_data.get('is_valid', False)
        elif "error" in data:
            print(f"   [X] Error verificando token: {data['error'].get('message')}")
            print()
            return False
    except Exception as e:
        print(f"   [X] Error de conexion: {e}")
        print()
        return False

    # Probar endpoint de perfil
    print("[3] Probando endpoint de perfil de negocio...")
    profile_url = f"https://graph.facebook.com/v22.0/{Config.WHATSAPP_PHONE_NUMBER_ID}/whatsapp_business_profile"
    headers = {"Authorization": f"Bearer {Config.WHATSAPP_API_TOKEN}"}
    params = {"fields": "about,address,description,email,vertical"}

    try:
        response = requests.get(profile_url, headers=headers, params=params, timeout=10)
        data = response.json()

        if "data" in data and len(data["data"]) > 0:
            print("   [OK] Perfil obtenido correctamente")
            profile = data["data"][0]
            print(f"   About: {profile.get('about', 'No configurado')}")
            print(f"   Email: {profile.get('email', 'No configurado')}")
            print(f"   Vertical: {profile.get('vertical', 'No configurado')}")
            print()
            return True
        elif "error" in data:
            error = data["error"]
            print(f"   [X] Error: {error.get('message')}")
            print(f"   Codigo: {error.get('code')}")
            print(f"   Tipo: {error.get('type')}")

            # Mensajes de ayuda según el error
            if error.get('code') == 190:
                print()
                print("   [!] SOLUCION: Tu token ha expirado o es invalido.")
                print("      Necesitas generar un nuevo token de acceso.")
            elif error.get('code') == 100:
                print()
                print("   [!] SOLUCION: El PHONE_NUMBER_ID es incorrecto.")

            print()
            return False
    except Exception as e:
        print(f"   [X] Error de conexion: {e}")
        print()
        return False

def show_token_instructions():
    """Muestra instrucciones para obtener un nuevo token."""
    print()
    print("=" * 60)
    print("CÓMO OBTENER UN NUEVO TOKEN DE ACCESO")
    print("=" * 60)
    print()
    print("1. Ve a Meta Business Suite:")
    print("   https://business.facebook.com/")
    print()
    print("2. Navega a:")
    print("   WhatsApp > Herramientas > API de WhatsApp")
    print()
    print("3. Opciones para obtener token:")
    print()
    print("   OPCIÓN A - Token Temporal (24 horas):")
    print("   - En la sección de configuración de la API")
    print("   - Copia el 'Token de acceso temporal'")
    print("   - ⚠️  Este token expira en 24 horas")
    print()
    print("   OPCIÓN B - Token Permanente (RECOMENDADO):")
    print("   - Ve a la sección 'Configuración del sistema'")
    print("   - Crea una 'App de sistema' o usa una existente")
    print("   - Genera un token de acceso permanente con permisos:")
    print("     • whatsapp_business_management")
    print("     • whatsapp_business_messaging")
    print("   - Este token NO expira")
    print()
    print("4. Actualizar el token en tu proyecto:")
    print("   - Abre el archivo .env")
    print("   - Actualiza WHATSAPP_API_TOKEN con el nuevo valor")
    print("   - Reinicia la aplicación Flask")
    print()
    print("=" * 60)
    print()

if __name__ == "__main__":
    is_valid = check_token_validity()

    if not is_valid:
        show_token_instructions()
        print("[X] El token necesita ser actualizado")
        exit(1)
    else:
        print("[OK] Todo funcionando correctamente")
        print()
        exit(0)
