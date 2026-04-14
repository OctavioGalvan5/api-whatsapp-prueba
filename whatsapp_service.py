"""
Servicio para interactuar con la API de WhatsApp Business.
"""
import requests
import logging
import json
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

BASE_URL = "https://graph.facebook.com/v22.0"

# Cache en memoria para templates (TTL: 30 minutos — templates cambian rara vez)
_template_cache = {'data': None, 'expires_at': 0}
CACHE_TTL = 1800

# Cliente MinIO/S3
_s3_client = None

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


def ensure_bucket_exists_generic(bucket_name):
    """Verifica que un bucket existe, lo crea si no, y configura acceso público."""
    try:
        s3 = get_s3_client()

        # Intentar verificar si el bucket existe
        try:
            s3.head_bucket(Bucket=bucket_name)
            logger.info(f"✅ Bucket '{bucket_name}' verificado")
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code in ['404', 'NoSuchBucket']:
                # Bucket no existe, crearlo
                logger.info(f"📦 Creando bucket '{bucket_name}'...")
                s3.create_bucket(Bucket=bucket_name)
                logger.info(f"✅ Bucket '{bucket_name}' creado exitosamente")
            else:
                raise

        # Configurar política pública
        set_bucket_public_policy(s3, bucket_name)
        return True
    except Exception as e:
        logger.error(f"Error verificando/creando bucket '{bucket_name}': {str(e)}")
        return False


# Cache para evitar verificar buckets múltiples veces
_buckets_verified = set()


def ensure_bucket_exists():
    """Verifica que el bucket de media existe."""
    global _buckets_verified
    bucket = Config.MINIO_BUCKET
    if bucket in _buckets_verified:
        return True

    if ensure_bucket_exists_generic(bucket):
        _buckets_verified.add(bucket)
        return True
    return False


def ensure_rag_bucket_exists():
    """Verifica que el bucket de RAG documents existe."""
    global _buckets_verified
    bucket = Config.MINIO_BUCKET_RAG
    if bucket in _buckets_verified:
        return True

    if ensure_bucket_exists_generic(bucket):
        _buckets_verified.add(bucket)
        return True
    return False


def init_all_buckets():
    """Inicializa todos los buckets necesarios al arrancar la app."""
    logger.info("🗂️ Inicializando buckets de MinIO...")
    ensure_bucket_exists()
    ensure_rag_bucket_exists()
    logger.info("✅ Buckets inicializados")


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
            logger.info(f"📤 Enviando template '{template_name}' a {to_phone} con components: {json.dumps(components) if components else 'None'}")
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
            logger.error(f"Error enviando template '{template_name}' a {to_phone}: {e}")
            error_detail = ""
            if hasattr(e, 'response') and e.response:
                try:
                    error_detail = e.response.json()
                    logger.error(f"📛 Detalle del error de Meta: {json.dumps(error_detail)}")
                except:
                    error_detail = e.response.text
                    logger.error(f"📛 Respuesta de Meta: {error_detail}")
            logger.error(f"📦 Payload enviado: {json.dumps(payload)}")
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
            "allow_category_change": True,
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
            error_detail = ""
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_json = e.response.json()
                    error_obj = error_json.get("error", {})
                    # Preferir error_user_msg (mensaje amigable en español) sobre message (genérico)
                    error_detail = error_obj.get("error_user_msg") or error_obj.get("message", str(e))
                    logger.error(f"Error creando template: {e} | Detalle Meta: {error_json}")
                except:
                    error_detail = e.response.text
                    logger.error(f"Error creando template: {e} | Response: {error_detail}")
            else:
                logger.error(f"Error creando template: {e}")
            return {"error": error_detail or str(e)}

    def upload_media(self, file_bytes, mime_type, filename):
        """
        Sube un archivo a WhatsApp para poder enviarlo como mensaje.
        
        Args:
            file_bytes: Bytes del archivo
            mime_type: Tipo MIME del archivo (e.g. 'image/jpeg')
            filename: Nombre del archivo
            
        Returns:
            dict con media_id o error
        """
        if not self.phone_number_id:
            return {"error": "Phone Number ID no configurado"}
        
        url = f"{BASE_URL}/{self.phone_number_id}/media"
        
        # WhatsApp API requiere multipart/form-data para subir media
        # No usar self.headers porque tiene Content-Type: application/json
        headers = {
            "Authorization": f"Bearer {self.token}"
        }
        
        files = {
            'file': (filename, file_bytes, mime_type)
        }
        data = {
            'messaging_product': 'whatsapp',
            'type': mime_type
        }
        
        try:
            logger.info(f"📤 Subiendo media a WhatsApp: {filename} ({mime_type}, {len(file_bytes)} bytes)")
            response = requests.post(url, headers=headers, files=files, data=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            media_id = result.get("id")
            logger.info(f"✅ Media subido a WhatsApp: media_id={media_id}")
            return {"success": True, "media_id": media_id}
            
        except requests.exceptions.RequestException as e:
            error_detail = ""
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    logger.error(f"Error subiendo media: {e} | Detalle: {error_detail}")
                except:
                    error_detail = e.response.text
                    logger.error(f"Error subiendo media: {e} | Response: {error_detail}")
            else:
                logger.error(f"Error subiendo media: {e}")
            return {"error": str(e), "detail": error_detail}
    
    def send_media_message(self, to_phone, media_type, media_id, caption=None, filename=None):
        """
        Envía un mensaje multimedia usando un media_id previamente subido.
        
        Args:
            to_phone: Número de teléfono destino (con código de país, sin +)
            media_type: Tipo de media ('image', 'document', 'video', 'audio')
            media_id: ID del media subido a WhatsApp
            caption: Texto opcional que acompaña al media
            filename: Nombre del archivo (solo para documents)
        """
        if not self.phone_number_id:
            return {"error": "Phone Number ID no configurado"}
        
        url = f"{BASE_URL}/{self.phone_number_id}/messages"
        
        media_object = {"id": media_id}
        
        # caption solo es válido para image, video y document
        if caption and media_type in ('image', 'video', 'document'):
            media_object["caption"] = caption
        
        # filename solo es válido para document
        if filename and media_type == 'document':
            media_object["filename"] = filename
        
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": media_type,
            media_type: media_object
        }
        
        try:
            logger.info(f"📤 Enviando {media_type} a {to_phone} (media_id={media_id})")
            response = requests.post(url, headers=self.headers, json=payload, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            logger.info(f"✅ {media_type} enviado a {to_phone}")
            return {
                "success": True,
                "message_id": data.get("messages", [{}])[0].get("id"),
                "to": to_phone
            }
            
        except requests.exceptions.RequestException as e:
            error_detail = ""
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    logger.error(f"Error enviando {media_type}: {e} | Detalle: {error_detail}")
                except:
                    error_detail = e.response.text
                    logger.error(f"Error enviando {media_type}: {e} | Response: {error_detail}")
            else:
                logger.error(f"Error enviando {media_type}: {e}")
            return {"error": str(e), "detail": error_detail}
    
    def upload_to_minio(self, file_bytes, mime_type, filename):
        """
        Sube un archivo a MinIO para almacenamiento persistente.
        Retorna la URL pública o None si falla.
        """
        try:
            s3 = get_s3_client()
            bucket = Config.MINIO_BUCKET
            ensure_bucket_exists()
            
            s3.put_object(
                Bucket=bucket,
                Key=filename,
                Body=file_bytes,
                ContentType=mime_type
            )
            
            public_url = get_minio_public_url(filename)
            logger.info(f"✅ Archivo subido a MinIO: {public_url} ({len(file_bytes)} bytes)")
            return public_url
            
        except Exception as e:
            logger.error(f"Error subiendo a MinIO: {str(e)}")
            # Fallback: guardar localmente
            base_dir = os.path.dirname(os.path.abspath(__file__))
            local_dir = os.path.join(base_dir, "static", "media")
            if not os.path.exists(local_dir):
                os.makedirs(local_dir)
            local_path = os.path.join(local_dir, filename)
            with open(local_path, 'wb') as f:
                f.write(file_bytes)
            logger.warning(f"⚠️ Fallback a almacenamiento local: {local_path}")
            return f"static/media/{filename}"

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

    def get_business_profile(self):
        """
        Obtiene la información actual del perfil de WhatsApp Business.

        Returns:
            dict: Información del perfil o error
        """
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

            # La API devuelve {"data": [profile_object]}
            if "data" in data and len(data["data"]) > 0:
                profile = data["data"][0]
                logger.info("✅ Perfil de WhatsApp Business obtenido")
                return {"success": True, "profile": profile}
            else:
                return {"error": "No se pudo obtener el perfil"}

        except requests.exceptions.RequestException as e:
            logger.error(f"Error obteniendo perfil de negocio: {e}")
            return {"error": str(e)}

    def update_business_profile(self, profile_data):
        """
        Actualiza el perfil de WhatsApp Business.

        Args:
            profile_data: Dict con los campos a actualizar
                - about: Descripción (máx 256 caracteres)
                - address: Dirección física
                - description: Descripción larga (máx 512 caracteres)
                - email: Email de contacto
                - vertical: Categoría del negocio (ej: PROF_SERVICES)
                - websites: Lista de URLs (máx 2)

        Returns:
            dict: Resultado de la operación
        """
        if not self.phone_number_id:
            return {"error": "Phone Number ID no configurado"}

        url = f"{BASE_URL}/{self.phone_number_id}/whatsapp_business_profile"

        # Construir payload
        payload = {"messaging_product": "whatsapp"}

        # Agregar solo los campos que vienen en profile_data
        allowed_fields = ["about", "address", "description", "email", "vertical", "websites"]
        for field in allowed_fields:
            if field in profile_data and profile_data[field]:
                payload[field] = profile_data[field]

        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()

            logger.info("✅ Perfil de WhatsApp Business actualizado")
            return {"success": True, "data": data}

        except requests.exceptions.RequestException as e:
            logger.error(f"Error actualizando perfil de negocio: {e}")
            error_msg = str(e)

            # Intentar extraer mensaje de error de la API
            try:
                if hasattr(e, 'response') and e.response is not None:
                    error_data = e.response.json()
                    if 'error' in error_data:
                        error_msg = error_data['error'].get('message', error_msg)
            except:
                pass

            return {"error": error_msg}


    # ==================== CATALOG API ====================

    def get_catalogs(self):
        """Lista los catálogos del WABA."""
        if not self.is_configured():
            return {"error": "WhatsApp API no configurada"}
        url = f"{BASE_URL}/{self.business_account_id}/product_catalogs"
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            return {"success": True, "catalogs": response.json().get("data", [])}
        except requests.exceptions.RequestException as e:
            logger.error(f"Error obteniendo catálogos: {e}")
            return {"error": str(e)}

    def sync_catalog_products(self, catalog_id):
        """
        Trae todos los productos de un catálogo desde Meta y los sincroniza en local.
        Retorna la lista de productos raw de la API.
        """
        if not self.is_configured():
            return {"error": "WhatsApp API no configurada"}
        url = f"{BASE_URL}/{catalog_id}/products"
        params = {
            "fields": "retailer_id,name,description,price,currency,availability,image_url",
            "limit": 500,
        }
        products = []
        while url:
            try:
                response = requests.get(url, headers=self.headers, params=params, timeout=20)
                response.raise_for_status()
                data = response.json()
                products.extend(data.get("data", []))
                next_page = data.get("paging", {}).get("next")
                url = next_page
                params = {}  # next ya trae los params
            except requests.exceptions.RequestException as e:
                logger.error(f"Error sincronizando productos: {e}")
                return {"error": str(e)}
        return {"success": True, "products": products}

    def create_catalog_product(self, catalog_id, retailer_id, name, price, currency, description=None, availability='in_stock'):
        """Crea un producto en el catálogo de Meta."""
        if not self.is_configured():
            return {"error": "WhatsApp API no configurada"}
        url = f"{BASE_URL}/{catalog_id}/products"
        payload = {
            "retailer_id": retailer_id,
            "name": name,
            "price": int(float(price) * 100),  # Meta usa centavos
            "currency": currency,
            "availability": availability,
        }
        if description:
            payload["description"] = description
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=15)
            response.raise_for_status()
            return {"success": True, "data": response.json()}
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creando producto en Meta: {e}")
            detail = ""
            if hasattr(e, 'response') and e.response is not None:
                try:
                    detail = e.response.json().get("error", {}).get("message", "")
                except Exception:
                    pass
            return {"error": detail or str(e)}

    def update_catalog_product(self, product_id, name=None, price=None, currency=None, description=None, availability=None):
        """Actualiza un producto en Meta."""
        if not self.is_configured():
            return {"error": "WhatsApp API no configurada"}
        url = f"{BASE_URL}/{product_id}"
        payload = {}
        if name is not None:
            payload["name"] = name
        if price is not None:
            payload["price"] = int(float(price) * 100)
        if currency is not None:
            payload["currency"] = currency
        if description is not None:
            payload["description"] = description
        if availability is not None:
            payload["availability"] = availability
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=15)
            response.raise_for_status()
            return {"success": True}
        except requests.exceptions.RequestException as e:
            logger.error(f"Error actualizando producto en Meta: {e}")
            detail = ""
            if hasattr(e, 'response') and e.response is not None:
                try:
                    detail = e.response.json().get("error", {}).get("message", "")
                except Exception:
                    pass
            return {"error": detail or str(e)}

    def delete_catalog_product(self, product_id):
        """Elimina un producto de Meta."""
        if not self.is_configured():
            return {"error": "WhatsApp API no configurada"}
        url = f"{BASE_URL}/{product_id}"
        try:
            response = requests.delete(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            return {"success": True}
        except requests.exceptions.RequestException as e:
            logger.error(f"Error eliminando producto en Meta: {e}")
            return {"error": str(e)}


# Instancia global
whatsapp_api = WhatsAppAPI()
