"""
Servicio para interactuar con la API de WhatsApp Business.
"""
import requests
import logging
from config import Config

logger = logging.getLogger(__name__)

BASE_URL = "https://graph.facebook.com/v18.0"


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
    
    def get_templates(self):
        """Obtiene las plantillas de mensajes de la cuenta."""
        if not self.is_configured():
            return {"error": "WhatsApp API no configurada", "templates": []}
        
        url = f"{BASE_URL}/{self.business_account_id}/message_templates"
        params = {
            "fields": "name,status,category,language,components,quality_score",
            "limit": 100
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
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
            
            return {"templates": templates, "count": len(templates)}
            
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
            response = requests.get(url, headers=self.headers, params=params)
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
            response = requests.get(url, headers=self.headers, params=params)
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
            response = requests.post(url, headers=self.headers, json=payload)
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
            response = requests.post(url, headers=self.headers, json=payload)
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
