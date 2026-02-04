"""
Servicio para interactuar con la API de WhatsApp Business.
"""
import requests
import logging
import time
import os
import mimetypes
import urllib3
import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError
from config import Config

# Suprimir warnings de SSL para certificados self-signed (MinIO)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

BASE_URL = "https://graph.facebook.com/v18.0"

# Cache en memoria para templates (TTL: 5 minutos)
_template_cache = {'data': None, 'expires_at': 0}
CACHE_TTL = 300

# Cliente MinIO/S3
_s3_client = None
_bucket_verified = False

def get_s3_client():
    """Obtiene o crea el cliente S3 para MinIO."""
    global _s3_client
    if _s3_client is None:
        endpoint = Config.MINIO_ENDPOINT
        protocol = "https" if Config.MINIO_USE_SSL else "http"
        endpoint_url = f"{protocol}://{endpoint}"

        _s3_client = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=Config.MINIO_ACCESS_KEY,
            aws_secret_access_key=Config.MINIO_SECRET_KEY,
            config=BotoConfig(signature_version='s3v4'),
            region_name='us-east-1',
            verify=False  # Deshabilitar verificación SSL para certificados self-signed
        )
        logger.info(f"✅ Cliente MinIO inicializado: {endpoint_url}")
    return _s3_client


def set_bucket_public_policy(s3, bucket):
    """Configura el bucket para acceso público de lectura."""
    import json
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": "*"},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket}/*"]
            }
        ]
    }
    try:
        s3.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))
        logger.info(f"✅ Política pública configurada para bucket '{bucket}'")
    except Exception as e:
        logger.warning(f"⚠️ No se pudo configurar política pública: {str(e)}")


def ensure_bucket_exists():
    """Verifica que el bucket existe, lo crea si no, y configura acceso público."""
    global _bucket_verified
    if _bucket_verified:
        return True

    try:
        s3 = get_s3_client()
        bucket = Config.MINIO_BUCKET
        created = False

        # Intentar verificar si el bucket existe
        try:
            s3.head_bucket(Bucket=bucket)
            logger.info(f"✅ Bucket '{bucket}' verificado")
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code in ['404', 'NoSuchBucket']:
                # Bucket no existe, crearlo
                logger.info(f"📦 Creando bucket '{bucket}'...")
                s3.create_bucket(Bucket=bucket)
                logger.info(f"✅ Bucket '{bucket}' creado exitosamente")
                created = True
            else:
                raise

        # Configurar política pública (siempre intentar, por si no está configurada)
        set_bucket_public_policy(s3, bucket)

        _bucket_verified = True
        return True
    except Exception as e:
        logger.error(f"Error verificando/creando bucket: {str(e)}")
        return False


def get_minio_public_url(filename):
    """
    Genera la URL para un archivo en MinIO.
    Usa el proxy /media/<filename> para evitar problemas de SSL y mixed content.
    """
    # Usar el proxy interno en lugar de URL directa a MinIO
    # Esto evita problemas de certificados SSL y mixed content
    return f"/media/{filename}"


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
        Descarga un archivo multimedia de WhatsApp y lo sube a MinIO.
        Retorna la URL pública del archivo en MinIO o None si falla.
        """
        try:
            if not self.is_configured():
                logger.error("API no configurada para descargar media")
                return None

            logger.info(f"⬇️ Iniciando descarga media_id: {media_id}")

            # 1. Obtener URL de descarga desde WhatsApp
            url_info = f"{BASE_URL}/{media_id}"
            res_info = requests.get(url_info, headers=self.headers, timeout=10)

            if res_info.status_code != 200:
                logger.error(f"Error info media {media_id}: {res_info.status_code} - {res_info.text}")
                return None

            data = res_info.json()
            media_url = data.get("url")
            mime_type = data.get("mime_type", "application/octet-stream")

            logger.info(f"Media info OK. Mime: {mime_type}, URL: {media_url}")

            if not media_url:
                logger.error("No URL found in media info")
                return None

            # 2. Determinar extensión (normalizar para consistencia)
            ext = mimetypes.guess_extension(mime_type)

            # Normalizar extensiones de audio a .ogg (mimetypes puede retornar .oga en algunos sistemas)
            if ext in ['.oga', '.opus']:
                ext = '.ogg'

            # Fallbacks si mimetypes no reconoce el tipo
            if not ext:
                if 'audio' in mime_type: ext = '.ogg'
                elif 'image' in mime_type: ext = '.jpg'
                elif 'video' in mime_type: ext = '.mp4'
                elif 'pdf' in mime_type: ext = '.pdf'
                else: ext = '.bin'

            filename = f"{media_id}{ext}"

            # 3. Descargar contenido de WhatsApp
            logger.info(f"Descargando contenido de WhatsApp...")
            res_media = requests.get(media_url, headers=self.headers, timeout=30)

            if res_media.status_code != 200:
                logger.error(f"Error descargando binario: {res_media.status_code}")
                return None

            if len(res_media.content) == 0:
                logger.error(f"Error: Archivo descargado tiene 0 bytes")
                return None

            # 4. Subir a MinIO
            try:
                s3 = get_s3_client()
                bucket = Config.MINIO_BUCKET

                # Asegurar que el bucket existe
                ensure_bucket_exists()

                s3.put_object(
                    Bucket=bucket,
                    Key=filename,
                    Body=res_media.content,
                    ContentType=mime_type
                )

                public_url = get_minio_public_url(filename)
                logger.info(f"✅ Media subido a MinIO: {public_url} ({len(res_media.content)} bytes)")

                return public_url

            except Exception as e:
                logger.error(f"Error subiendo a MinIO: {str(e)}")
                # Fallback: guardar localmente si MinIO falla
                base_dir = os.path.dirname(os.path.abspath(__file__))
                local_dir = os.path.join(base_dir, "static", "media")
                if not os.path.exists(local_dir):
                    os.makedirs(local_dir)
                local_path = os.path.join(local_dir, filename)
                with open(local_path, 'wb') as f:
                    f.write(res_media.content)
                logger.warning(f"⚠️ Fallback a almacenamiento local: {local_path}")
                return f"static/media/{filename}"

        except Exception as e:
            logger.error(f"EXCEPTION descargando media {media_id}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
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
