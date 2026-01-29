# WhatsApp Webhook Middleware

Este proyecto actúa como un intermediario entre la API de WhatsApp Business (Meta) y Chatwoot.
Captura **todos** los eventos (mensajes, lecturas, errores) para tu uso propio, y luego los reenvía a Chatwoot para que su inbox siga funcionando.

## Estructura

- `app.py`: Servidor Flask.
- `event_handlers.py`: Lógica para procesar eventos (logs, futuro DB) y reenviar a Chatwoot.
- `config.py`: Manejo de configuración.

## Configuración Local

1. Copia el archivo de entorno:
   ```bash
   cp .env.example .env
   ```
2. Edita `.env` con tus datos:
   - `VERIFY_TOKEN`: Un string secreto que tú inventas (ej: "token_seguro_123").
   - `CHATWOOT_WEBHOOK_URL`: La URL que te da Chatwoot para la integración de WhatsApp.

3. Instala dependencias y corre:
   ```bash
   pip install -r requirements.txt
   python app.py
   ```

## Despliegue en Dokploy

1. **Crear Aplicación**: En tu dashboard de Dokploy, crea una nueva "Application".
2. **Source**: Conecta este repositorio (GitHub/GitLab).
3. **Build Type**: Dockerfile (ya incluido en el repo).
4. **Environment Variables**:
   Añade las siguientes variables en la sección "Environment" de Dokploy:
   - `VERIFY_TOKEN`: (Tu token inventado)
   - `CHATWOOT_WEBHOOK_URL`: (La URL de Chatwoot)
   - `PORT`: 5000
5. **Deploy**: Haz clic en Deploy.

## Configuración en Meta (WhatsApp Business)

Una vez desplegado en Dokploy y que tengas tu dominio (ej: `https://api-whatsapp.midominio.com`):

1. Ve a [developers.facebook.com](https://developers.facebook.com) > Tu App > WhatsApp > Configuration.
2. En la sección **Webhook**:
   - **Callback URL**: `https://api-whatsapp.midominio.com/webhook`
   - **Verify Token**: El mismo `VERIFY_TOKEN` que pusiste en Dokploy.
3. Haz clic en "Verify and Save".
4. En **Webhook Fields**, haz clic en "Manage" y suscríbete a TODO (messages, message_template_status_update, etc.).

## Logs

Para ver los mensajes leídos o errores:
- Ve a la sección de **Logs** de tu aplicación en Dokploy.
- Verás entradas como `👁️‍🗨️ ¡El usuario X LEYÓ el mensaje!` o `❌ ERROR DE ENVÍO`.
