"""
Servicio para interactuar con la API de WhatsApp Business.
"""
import requests
import logging
import time
import os
import mimetypes
from config import Config

logger = logging.getLogger(__name__)

BASE_URL = "https://graph.facebook.com/v18.0"

# Cache en memoria para templates (TTL: 5 minutos)
_template_cache = {'data': None, 'expires_at': 0}
CACHE_TTL = 300


class WhatsAppAPI:
    """Cliente para la API de WhatsApp Business."""
    
    def __init__(self):
        self.token = Config.WHATSAPP_API_TOKEN
        self.phone_number_id = Config.WHATSAPP_PHONE_NUMBER_ID
        self.business_account_id = Config.WHATSAPP_BUSINESS_ACCOUNT_ID
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def is_configured(self):
        """Verifica si las credenciales están configuradas."""
        return all([self.token, self.business_account_id])

    def download_media(self, media_id):
        """
        Descarga un archivo multimedia de WhatsApp.
        Retorna la ruta relativa (ej: 'static/media/12345.jpg') o None si falla.
        """
        if not self.is_configured():
            logger.error("API no configurada para descargar media")
            return None
            
        # 1. Obtener URL de descarga
        url_info = f"{BASE_URL}/{media_id}"
        try:
            res_info = requests.get(url_info, headers=self.headers, timeout=10)
            res_info.raise_for_status()
            data = res_info.json()
            media_url = data.get("url")
            mime_type = data.get("mime_type")
        except Exception as e:
            logger.error(f"Error obteniendo info de media {media_id}: {e}")
            return None
            
        if not media_url:
            return None
            
        # 2. Determinar extensión
        ext = mimetypes.guess_extension(mime_type)
        if not ext:
            # Fallbacks comunes
            if 'image' in mime_type: ext = '.jpg'
            elif 'audio' in mime_type: ext = '.ogg'
            elif 'video' in mime_type: ext = '.mp4'
            elif 'pdf' in mime_type: ext = '.pdf'
            else: ext = '.bin'
            
        filename = f"{media_id}{ext}"
        # Asegurar que existe el directorio
        local_dir = os.path.join(os.getcwd(), "static", "media")
        if not os.path.exists(local_dir):
            os.makedirs(local_dir)
            
        local_path = os.path.join(local_dir, filename)
        
        # 3. Descargar contenido
        try:
            # Nota: Para descargar el binario, se usa la URL provista PERO con los headers de autorización
            res_media = requests.get(media_url, headers=self.headers, timeout=30)
            res_media.raise_for_status()
            
            with open(local_path, 'wb') as f:
                f.write(res_media.content)
                
            logger.info(f"✅ Media descargado: {local_path}")
            # Retornar path relativo para usar en frontend
            return f"static/media/{filename}"
            
        except Exception as e:
            logger.error(f"Error descargando binario media {media_id}: {e}")
            return None
    
    def get_templates(self):
        """Obtiene las plantillas de mensajes de la cuenta (con cache de 5 min)."""
        if not self.is_configured():
            return {"error": "WhatsApp API no configurada", "templates": []}

        # Retornar desde cache si está vigente
        if _template_cache['data'] is not None and time.time() < _template_cache['expires_at']:
            return _template_cache['data']

        url = f"{BASE_URL}/{self.business_account_id}/message_templates"
        params = {
            "fields": "name,status,category,language,components,quality_score",
            "limit": 100
        }

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            templates = []
            for t in data.get("data", []):
                templates.append({
                    "name": t.get("name"),
                    "status": t.get("status"),
                    "category": t.get("category"),
                    "language": t.get("language"),
                    "quality_score": t.get("quality_score"),
                    "components": t.get("components", [])
                })

            result = {"templates": templates, "count": len(templates)}

            # Guardar en cache
            _template_cache['data'] = result
            _template_cache['expires_at'] = time.time() + CACHE_TTL

            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"Error obteniendo templates: {e}")
            return {"error": str(e), "templates": []}
    
    def get_phone_numbers(self):
        """Obtiene los números de teléfono de la cuenta."""
        if not self.is_configured():
            return {"error": "WhatsApp API no configurada", "phone_numbers": []}
        
        url = f"{BASE_URL}/{self.business_account_id}/phone_numbers"
        params = {
            "fields": "display_phone_number,verified_name,quality_rating,messaging_limit_tier,status"
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            return {"phone_numbers": data.get("data", [])}
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error obteniendo números: {e}")
            return {"error": str(e), "phone_numbers": []}
    
    def get_business_profile(self):
        """Obtiene el perfil del negocio."""
        if not self.phone_number_id:
            return {"error": "Phone Number ID no configurado"}
        
        url = f"{BASE_URL}/{self.phone_number_id}/whatsapp_business_profile"
        params = {
            "fields": "about,address,description,email,profile_picture_url,websites,vertical"
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            return {"profile": data.get("data", [{}])[0] if data.get("data") else {}}
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error obteniendo perfil: {e}")
            return {"error": str(e)}
    
    def send_template_message(self, to_phone, template_name, language_code="es_AR", components=None):
        """
        Envía un mensaje usando una plantilla.
        
        Args:
            to_phone: Número de teléfono destino (con código de país, sin +)
            template_name: Nombre de la plantilla
            language_code: Código de idioma (default: es_AR)
            components: Lista de componentes para variables de la plantilla
        """
        if not self.phone_number_id:
            return {"error": "Phone Number ID no configurado"}
        
        url = f"{BASE_URL}/{self.phone_number_id}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code}
            }
        }
        
        if components:
            payload["template"]["components"] = components
        
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()

            logger.info(f"✅ Template enviado a {to_phone}: {template_name}")
            return {
                "success": True,
                "message_id": data.get("messages", [{}])[0].get("id"),
                "to": to_phone
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error enviando template: {e}")
            error_detail = ""
            if hasattr(e, 'response') and e.response:
                try:
                    error_detail = e.response.json()
                except:
                    error_detail = e.response.text
            return {"error": str(e), "detail": error_detail}
    
    def create_template(self, name, category, language, components):
        """
        Crea una nueva plantilla de mensaje.

        Args:
            name: Nombre de la plantilla (snake_case, sin espacios)
            category: Categoría (MARKETING, UTILITY, AUTHENTICATION)
            language: Código de idioma (es_AR, en_US, etc.)
            components: Lista de componentes (HEADER, BODY, FOOTER, BUTTONS)

        Returns:
            dict con success/error y los datos de la plantilla creada
        """
        if not self.is_configured():
            return {"error": "WhatsApp API no configurada"}

        url = f"{BASE_URL}/{self.business_account_id}/message_templates"

        payload = {
            "name": name,
            "category": category,
            "language": language,
            "components": components
        }

        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=15)
            response.raise_for_status()
            data = response.json()

            logger.info(f"✅ Template '{name}' creado exitosamente")

            # Invalidar cache para que se recarguen los templates
            _template_cache['data'] = None
            _template_cache['expires_at'] = 0

            return {
                "success": True,
                "id": data.get("id"),
                "status": data.get("status", "PENDING"),
                "category": data.get("category")
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Error creando template: {e}")
            error_detail = ""
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_json = e.response.json()
                    error_detail = error_json.get("error", {}).get("message", str(e))
                except:
                    error_detail = e.response.text
            return {"error": error_detail or str(e)}

    def send_text_message(self, to_phone, text):
        """
        Envía un mensaje de texto simple.

        Args:
            to_phone: Número de teléfono destino (con código de país, sin +)
            text: Texto del mensaje
        """
        if not self.phone_number_id:
            return {"error": "Phone Number ID no configurado"}
        
        url = f"{BASE_URL}/{self.phone_number_id}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "text",
            "text": {"body": text}
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()

            logger.info(f"✅ Mensaje enviado a {to_phone}")
            return {
                "success": True,
                "message_id": data.get("messages", [{}])[0].get("id"),
                "to": to_phone
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error enviando mensaje: {e}")
            return {"error": str(e)}


# Instancia global
whatsapp_api = WhatsAppAPI()
