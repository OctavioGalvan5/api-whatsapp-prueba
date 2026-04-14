# Plan: Sistema de Órdenes + Catálogo

---

## Base de datos — tablas nuevas

### `catalog_products`
| Campo | Tipo | Descripción |
|-------|------|-------------|
| retailer_id | PK | ID del producto en el catálogo |
| wa_product_id | string | ID interno de Meta |
| catalog_id | string | Auto-detectado, guardado en ChatbotConfig |
| name | string | Nombre del producto |
| description | string | Descripción |
| price | decimal | Precio |
| currency | string | Moneda (ej: ARS) |
| availability | enum | in_stock / out_of_stock |
| image_url | string | URL de la imagen |
| synced_at | datetime | Última sincronización con Meta |

### `orders`
| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | PK | Numeración global #0001, #0002... |
| contact_id | FK | Referencia a whatsapp_contacts |
| phone_number | string | Teléfono del contacto |
| source | enum | whatsapp / manual |
| wa_message_id | string | Nullable, solo si vino de WhatsApp |
| status | enum | pendiente / confirmado / pendiente_envio / enviado / entregado / cancelado |
| payment_status | enum | sin_pagar / pagado / reembolsado |
| payment_method | enum | efectivo / transferencia / mercadopago / tarjeta / otro |
| total | decimal | Total de la orden — se calcula automáticamente de order_items pero es editable manualmente |
| currency | string | Moneda |
| shipping_address | text | Dirección de envío — Nullable, editable manualmente |
| notes | text | Notas internas |
| seen_at | datetime | Nullable — se setea al abrir por primera vez |
| seen_by | FK | CrmUser que la vio por primera vez |
| created_at | datetime | Fecha/hora de creación |
| updated_at | datetime | Fecha/hora de última edición |
| created_by | FK | CrmUser que la creó |
| last_edited_by | FK | CrmUser que la editó por última vez |
| terminated_at | datetime | Fecha/hora de terminación manual |
| terminated_by | FK | CrmUser que usó el botón "Terminar orden" |

### `order_items`
| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | PK | |
| order_id | FK | Referencia a orders |
| retailer_id | string | ID del producto |
| product_name | string | Snapshot del nombre al momento del pedido |
| quantity | int | Cantidad |
| unit_price | decimal | Precio unitario |
| currency | string | Moneda |

---

## Nuevos permisos en CrmUser

| Permiso | Acceso |
|---------|--------|
| orders | Ver /orders + botón "Crear orden" en chat |
| catalog | Ver/editar /catalog |

Se agregan al modal de admin igual que los permisos existentes.

---

## Catálogo — auto-detección

Al entrar a `/catalog` por primera vez:
1. Llama `GET /{WHATSAPP_BUSINESS_ACCOUNT_ID}/product_catalogs` con el token ya configurado
2. Si hay 1 catálogo → guarda `catalog_id` en `ChatbotConfig` y sincroniza automáticamente
3. Si hay varios → muestra selector para elegir cuál usar
4. Si falla la API → espera el primer pedido entrante (el `catalog_id` viene en el mensaje de orden)
5. Último fallback → input manual

**Sync automático cada 5 minutos** + botón "Sincronizar ahora" manual.

---

## Página `/catalog` (permiso: catalog)

- Tabla con: imagen, nombre, precio, disponibilidad
- Editar producto inline → sincroniza cambio con Meta API
- Crear producto → se crea en Meta + tabla local
- Eliminar producto → se elimina en Meta + tabla local
- Indicador "Última sync hace X min"
- Botón "Sincronizar ahora"

---

## Lógica de etiquetas automáticas

Las etiquetas "Con pedido" y "Comprador" se crean automáticamente si no existen en el sistema.

| Evento | "Con pedido" | "Comprador" |
|--------|-------------|-------------|
| Llega orden de WhatsApp | + agregar | + agregar |
| Se crea orden manual desde CRM | + agregar | + agregar |
| Se marca `entregado` | quitar SOLO si no quedan órdenes activas | permanente |
| Se marca `cancelado` | quitar SOLO si no quedan órdenes activas | permanente |
| Botón "Terminar orden" | quitar SOLO si no quedan órdenes activas | permanente |

**Estados activos** (orden en curso): `pendiente`, `confirmado`, `pendiente_envio`, `enviado`

**Estados terminales** (orden cerrada): `entregado`, `cancelado`, `terminado`

### Regla para quitar "Con pedido"
```
Al cerrar una orden:
    ¿tiene otras órdenes en estado activo?
        SÍ → no tocar "Con pedido"
        NO → quitar "Con pedido"
```

---

## Página `/orders` (permiso: orders)

### Filtros disponibles
- **Estado:** pendiente | confirmado | pendiente_envio | enviado | entregado | cancelado | terminado
- **Pago:** sin_pagar | pagado | reembolsado
- **Método de pago:** efectivo | transferencia | mercadopago | tarjeta | otro
- **Fecha:** desde / hasta
- **Contacto:** búsqueda por nombre o teléfono
- **Vistas:** todas | solo no vistas | solo vistas

### Columnas de la tabla
- #orden, contacto, fecha/hora, productos (resumen), total, estado, estado de pago, última edición por, punto azul si no vista

### Panel de detalle (al hacer click en una orden)
- Todos los campos editables
- Lista de productos con cantidades y precios unitarios
- Botón **"Terminar orden"** → cierra la orden en el estado que está + evalúa quitar "Con pedido"
- Auditoría completa: creado por / editado por / visto por / fecha-hora de cada evento

### Visibilidad
Respeta el sistema de etiquetas del CRM. Si el usuario no tiene acceso a "Comprador" o "Con pedido", no ve esas órdenes.

---

## Notificaciones (badge + toast)

### Badge en sidebar
```
🛍 Órdenes  [3]
```
- Cuenta todas las órdenes donde `seen_at IS NULL` (manuales + WhatsApp)
- Se actualiza cada 30 segundos con polling
- Al abrir el detalle de una orden → `seen_at = ahora`, `seen_by = usuario actual`

### Toast notification
```
📦 Nueva orden de Juan Pérez
    Remera Blanca x2 — $30.000
    [Ver orden →]
```
- Solo para órdenes de WhatsApp (source = 'whatsapp')
- Aparece cuando el usuario está en la app y llega una orden nueva
- Implementado con polling (mismo patrón que mensajes nuevos en el dashboard)

---

## En el chat — dashboard

### Burbuja de orden entrante de WhatsApp
```
📦 Pedido #0042
─────────────────────────
• Remera Blanca x2    $30.000
• Buzo Negro x1       $25.000
─────────────────────────
Total: $55.000 ARS        [Ver pedido →]
```
- El nombre del producto se resuelve contra la tabla `catalog_products`
- Si no se encuentra el producto → muestra el `retailer_id` como fallback

### Botón "Crear orden" en toolbar del chat
- Solo visible para usuarios con permiso `orders`
- Abre un modal con:
  - Buscador de productos del catálogo local
  - Seleccionar productos + cantidades
  - Elegir método de pago + estado inicial de la orden
- Al confirmar:
  - Se crea la orden en `/orders`
  - Se aplican etiquetas automáticas ("Con pedido" + "Comprador")
  - `seen_at = NULL` (aparece en el badge)

---

## Navbar

- Agregar **"Órdenes"** al sidebar con ícono `shopping_bag` + badge de no vistas
- Agregar **"Catálogo"** al sidebar con ícono `inventory_2`
- Ambos respetan permisos del usuario

---

## Orden de implementación

1. **BD** — tablas `catalog_products`, `orders`, `order_items` + nuevos permisos en modelos + `create_database.sql`
2. **Catálogo** — auto-detección + sync automático + métodos en `whatsapp_service.py` + página `/catalog`
3. **Órdenes** — modelos, lógica de etiquetas, API endpoints
4. **Página `/orders`** — lista con filtros + panel de detalle + botón "Terminar orden"
5. **Notificaciones** — badge en sidebar + toast de nueva orden
6. **Chat** — burbuja especial de orden + modal "Crear orden"
7. **Navbar + permisos** — agregar items al sidebar + actualizar admin_users.html

---

## Fuera del alcance por ahora

- Descuentos por orden
- Reportes de ventas en /analytics
