# Plan: IA que Envía Archivos/Formularios

## Objetivo

Permitir que la IA del chatbot (n8n) envíe archivos (PDFs, formularios, etc.) cuando el usuario los solicita.

## Arquitectura

```
Usuario: "Necesito el formulario de inscripción"
    ↓
n8n → IA detecta pedido de archivo
    ↓
IA responde: "Te envío el formulario. [ARCHIVO:inscripcion.pdf]"
    ↓
n8n parsea [ARCHIVO:...] → llama POST /api/whatsapp/send-document
    ↓
App busca archivo en catálogo → lo baja de MinIO → lo sube a WhatsApp → lo envía
    ↓
Usuario recibe texto + PDF adjunto
```

## Cambios Necesarios

### 1. Base de Datos — Nueva tabla `bot_documents`

```sql
CREATE TABLE IF NOT EXISTS bot_documents (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,      -- Nombre interno (ej: "inscripcion_matricula")
    display_name VARCHAR(200) NOT NULL,      -- Nombre visible (ej: "Formulario de Inscripción")
    description TEXT,                         -- Descripción para que la IA entienda cuándo usarlo
    keywords TEXT,                            -- Palabras clave separadas por coma
    filename VARCHAR(255) NOT NULL,           -- Nombre del archivo en MinIO
    mime_type VARCHAR(100) DEFAULT 'application/pdf',
    file_size INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2. Backend (`models.py`)

- Nuevo modelo `BotDocument` con los campos de arriba

### 3. Backend (`app.py`) — 3 endpoints nuevos

- `GET /api/bot-documents` — Lista documentos disponibles (para dashboard y para el prompt de la IA)
- `POST /api/bot-documents` — Sube nuevo documento (archivo + metadata)
- `POST /api/whatsapp/send-document` — Envía un documento a un teléfono por nombre. Usado por n8n

### 4. Frontend — Nueva página `/bot-documents`

Página simple en el dashboard para gestionar documentos:
- Lista de documentos con nombre, descripción, palabras clave
- Botón para subir nuevo documento (drag & drop o file picker)
- Botón para eliminar documento
- Indicador de estado (activo/inactivo)

### 5. Configuración n8n

#### Modificar el prompt de la IA:

Agregar al system prompt:

```
Tenés acceso a los siguientes documentos que podés enviar al usuario.
Cuando el tema de la conversación requiera un formulario o documento, 
incluí exactamente este formato en tu respuesta: [ARCHIVO:nombre_del_archivo]

Documentos disponibles:
- inscripcion_matricula: Formulario de inscripción de matrícula nueva
- actualizacion_datos: Para cambio de domicilio, teléfono o datos personales
- solicitud_baja: Para solicitar baja de matrícula
```

> La lista de documentos puede generarse dinámicamente llamando a 
> `GET /api/bot-documents` desde n8n antes de pasarle el prompt a la IA.

#### Agregar nodo después de la respuesta de la IA:

1. **Nodo "IF"**: Verificar si la respuesta contiene `[ARCHIVO:`
2. **Nodo "Code"**: Extraer el nombre del archivo con regex
3. **Nodo "HTTP Request"**: `POST /api/whatsapp/send-document` con `{ "to": phone, "document_name": nombre }`
4. **Nodo "Code"**: Limpiar la respuesta de texto (quitar el `[ARCHIVO:...]` antes de enviarla)

## Sin Cambios

- **`whatsapp_service.py`**: Ya tiene `upload_media()` y `send_media_message()` del feature anterior
- **Tabla `whatsapp_messages`**: Ya tiene `media_url`, `caption`, `message_type`

## Verificación

1. Subir un PDF de prueba desde la página `/bot-documents`
2. Verificar que aparece en la lista
3. Desde n8n, enviar un mensaje al chatbot pidiendo ese documento
4. Verificar que la IA responde con el texto + el documento adjunto
5. Verificar que el documento aparece en el historial del dashboard
