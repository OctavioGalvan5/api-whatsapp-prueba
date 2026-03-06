# 🔧 Fix: Documentos Quedaban en "Procesando"

## 🔴 Problema Identificado

Los archivos subidos a la base de conocimiento RAG se vectorizaban correctamente en n8n, pero el status en la base de datos nunca se actualizaba de `processing` a `ready`, dejándolos permanentemente en estado "Procesando" en el dashboard.

## 🕵️ Causa Raíz

El workflow de n8n `RAG Vectorizer - MinIO.json` tenía un nodo llamado **"Update Status Ready"** que actualizaba el status directamente en PostgreSQL con SQL:

```sql
UPDATE rag_documents SET status = 'ready', updated_at = NOW() WHERE id = ...
```

**Problema:** Flask esperaba que n8n llamara al endpoint REST:
```
PUT /api/rag/documents/{doc_id}/status
Body: { "status": "ready" }
```

Pero n8n **nunca llamaba este endpoint**, por lo que Flask no se enteraba de que la vectorización había terminado.

## ✅ Solución Aplicada

### 1. Reemplazado SQL Directo por HTTP Request

**Antes (línea 736-756):**
```json
{
  "name": "Update Status Ready",
  "type": "n8n-nodes-base.postgres",
  "parameters": {
    "operation": "executeQuery",
    "query": "UPDATE rag_documents SET status = 'ready'..."
  }
}
```

**Después:**
```json
{
  "name": "Update Status Ready via API",
  "type": "n8n-nodes-base.httpRequest",
  "parameters": {
    "method": "PUT",
    "url": "={{ $('Set File Info').first().json.callback_url }}",
    "jsonBody": "={{ JSON.stringify({ status: 'ready' }) }}"
  }
}
```

### 2. Agregado Manejo de Errores

Se agregó un nuevo nodo **"Update Status Error via API"** (línea 879-905) que:
- Se ejecuta si la vectorización falla
- Llama al callback_url con `status: 'error'`
- Incluye el mensaje de error

## 🧪 Cómo Probar la Corrección

### Paso 1: Reimportar el Workflow en n8n

1. Ve a n8n
2. Abre el workflow **"RAG Vectorizer - MinIO"**
3. Haz click en "..." → "Import from File"
4. Selecciona el archivo actualizado: `RAG Vectorizer - MinIO.json`
5. Verifica que aparezca el nuevo nodo **"Update Status Ready via API"**

### Paso 2: Subir un Archivo de Prueba

1. Ve al Dashboard → Chatbot → Base de Conocimiento
2. Sube un archivo pequeño (PDF o TXT)
3. Observa que aparece como "Procesando" (spinner azul animado)

### Paso 3: Verificar en n8n

1. Ve a n8n → Executions
2. Busca la ejecución más reciente del workflow
3. Verifica que el nodo **"Update Status Ready via API"** se ejecutó correctamente
4. Debe mostrar:
   - Status: 200 OK
   - Response: `{ "success": true, "document": {...} }`

### Paso 4: Verificar en el Dashboard

Refresca la página del Dashboard. El documento debería mostrar:
- ✅ Badge verde: **"Vectorizado"**
- El spinner "Procesando" desaparece

## 🔍 Verificación Manual en Base de Datos

Si quieres verificar directamente en PostgreSQL:

```sql
-- Ver todos los documentos RAG
SELECT
    id,
    original_filename,
    status,
    error_message,
    created_at,
    updated_at
FROM rag_documents
ORDER BY created_at DESC
LIMIT 10;
```

**Resultado esperado:**
```
id | original_filename | status | error_message | updated_at
---+-------------------+--------+--------------+------------
5  | test.pdf          | ready  | NULL         | 2026-03-03 14:30:00
```

## 📊 Logs de Flask

Para ver los logs de Flask cuando n8n llama al callback:

```bash
# En la consola donde corre Flask
tail -f logs/app.log | grep "rag/documents"
```

**Log esperado:**
```
2026-03-03 14:30:00 INFO: PUT /api/rag/documents/5/status - Status code: 200
2026-03-03 14:30:00 INFO: Document 5 updated to status: ready
```

## 🐛 Si Sigue sin Funcionar

### Problema 1: n8n No Puede Alcanzar Flask
**Síntoma:** Error 504 o "Connection refused" en el nodo de n8n

**Solución:**
```bash
# Verifica que Config.FLASK_BASE_URL sea accesible desde n8n
# En config.py:
FLASK_BASE_URL = "https://dashboard-api.ogn8n2507.site"  # NO "localhost"
```

### Problema 2: Callback URL Incorrecta
**Síntoma:** n8n llama a URL equivocada

**Verificar en logs de n8n:**
```
callback_url debería ser:
https://dashboard-api.ogn8n2507.site/api/rag/documents/5/status

NO debería ser:
http://localhost:5000/api/rag/documents/5/status
```

### Problema 3: Error 401 Unauthorized
**Síntoma:** Flask rechaza la llamada de n8n

**Solución:** Ya está resuelto. El endpoint está en PUBLIC_PATHS (línea 89 de app.py):
```python
if request.path.startswith('/api/rag/documents/') and request.path.endswith('/status'):
    return None  # Permite sin auth
```

## 🎯 Archivos Modificados

1. ✅ `RAG Vectorizer - MinIO.json` - Workflow de n8n actualizado
2. ℹ️ `app.py` - Ya tenía el endpoint correcto (línea 4361-4376)
3. ℹ️ `models.py` - Modelo RagDocument ya era correcto

## 📝 Notas Adicionales

- **Documentos antiguos** que ya están en "processing" NO se actualizarán automáticamente
- Para corregirlos manualmente:
  ```sql
  -- Marcar como listos si ya están vectorizados
  UPDATE rag_documents
  SET status = 'ready', updated_at = NOW()
  WHERE status = 'processing'
    AND id IN (
      SELECT DISTINCT (metadata->>'file_id')::int
      FROM documents
      WHERE metadata->>'file_id' IS NOT NULL
    );
  ```

## ✅ Checklist de Verificación

- [x] Workflow actualizado con HTTP Request
- [x] Nodo de manejo de errores agregado
- [x] Callback URL se pasa correctamente desde Flask
- [x] Endpoint `/api/rag/documents/{id}/status` existe y funciona
- [x] Endpoint está en PUBLIC_PATHS (no requiere auth)
- [ ] Reimportar workflow en n8n
- [ ] Probar con archivo de prueba
- [ ] Verificar que status cambia a "ready"

---

**Fecha de corrección:** 2026-03-03
**Versión del fix:** 1.0
**Autor:** Claude Code
