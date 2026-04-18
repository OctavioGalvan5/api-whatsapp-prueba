# Reglas Auto Tagger — CountryLife CRM
Actualizado: 2026-04-18

---

## REGLAS EXISTENTES — MODIFICADAS

---

### 1. Asistencia Humana
**Antes:**
> ¿El cliente fue derivado a un humano, recibió toda la información necesaria (precio, formas de pago y envío), pero no se concretó la venta?

**Después:**
> ¿En la conversación el bot derivó al cliente a hablar con una persona humana, o lo invitó a contactar por otro medio (teléfono, sucursal, WhatsApp de vendedor, etc.), y el cliente no realizó una compra?

**Por qué cambió:** La condición original exigía "toda la información necesaria" antes de asignar la etiqueta, lo que era incorrecto. El criterio clave para esta etiqueta es simplemente si hubo una derivación a humano, no qué info recibió el cliente.

---

### 2. Pedido para más adelante
**Antes:**
> ¿El cliente recibió toda la información necesaria (precio, formas de pago y envío), pero decidió postergar la compra para más adelante sin concretarla?

**Después:**
> ¿El cliente expresó explícitamente que quiere comprar pero en otro momento? Por ejemplo: "después", "más adelante", "la semana que viene", "cuando tenga plata", "te aviso", "lo pienso", etc. La conversación terminó sin concretarse la venta.

**Por qué cambió:** No importa si el bot dio toda la info o no — lo que define esta etiqueta es la intención explícita del cliente de postergar. Ahora el criterio es solo la frase del cliente.

---

### 3. Venta por cerrar
**Antes:**
> ¿El cliente mostró intención de compra, recibió toda la información (precio, formas de pago y envío), pero no concretó la venta ni finalizó la compra?

**Después:**
> ¿El cliente mostró interés claro en comprar (pidió precio de un producto específico, preguntó cómo pagar, preguntó por el envío, o dijo que lo quiere), el bot respondió con información sobre el producto o precio, pero la compra no se concretó? Respondé SI solo si el cliente mostró intención activa, no si solo hizo una consulta general.

**Por qué cambió:** "Toda la información" era demasiado estricto. Ahora el foco está en la INTENCIÓN del cliente (no en qué información recibió). También se aclara la diferencia con "Consultó producto".

---

### 4. Mensajes Insta, Face, what
**Antes:**
> ¿El cliente recibió información necesaria (por ejemplo precio, formas de pago, envío, etc), pero no respondió más y no se concretó la venta?

**Después:**
> ¿El bot proporcionó información sobre algún producto (precio, descripción, beneficios, combos o modos de uso) y el cliente dejó de responder, o solo respondió con algo como "gracias", "ok", "dale", sin realizar ninguna compra? Respondé SI aunque el bot no haya mencionado explícitamente formas de pago o envío — alcanza con que haya dado información de precio o producto.

**Por qué cambió:** Esta era la regla que más fallaba. Los casos típicos (cliente pregunta por desengrasante, bot da precio y combos, cliente no responde más) no se detectaban porque el bot no siempre menciona "formas de pago y envío" explícitamente. Ahora alcanza con que el bot haya dado precio o info del producto.

---
---

## NUEVAS REGLAS — ANÁLISIS Y RECOMENDACIÓN

A continuación se evalúa cada sugerencia de ChatGPT: si conviene como auto-tag (IA detecta en la conversación), como tag manual (requiere acción humana o datos externos), o si no aplica.

---

### RECOMENDADAS COMO AUTO-TAG

---

#### 5. Consultó producto ✅ AUTO-TAG
> ¿El cliente preguntó sobre algún producto específico (nombre, precio, ingredientes, uso, disponibilidad, etc.) pero la conversación terminó sin que mostrara intención clara de compra ni realizara un pedido?

**Para qué sirve:** Detecta personas en fase de exploración. Son leads fríos que pueden necesitar seguimiento.
**Diferencia con "Venta por cerrar":** Aquí el cliente solo consultó, no mostró intención activa de comprar.

---

#### 6. Cliente indeciso ✅ AUTO-TAG
> ¿El cliente hizo varias preguntas sobre el mismo producto o productos similares, el bot respondió con información detallada, pero el cliente mostró dudas, pidió comparaciones, o no tomó ninguna decisión al final de la conversación?

**Para qué sirve:** Identifica clientes que necesitan un empujón o una oferta especial para decidirse.
**Diferencia con "Venta por cerrar":** En "venta por cerrar" hay intención clara. Aquí el cliente está vacilando.

---

#### 7. Cliente perdido ✅ AUTO-TAG
> ¿El cliente expresó rechazo, dijo que no le interesa, que es muy caro, que ya lo consiguió en otro lado, que no lo necesita, o simplemente se fue sin responder después de recibir el precio o información del producto, y pasaron al menos 2 mensajes del bot sin respuesta?

**Para qué sirve:** Separa los leads muertos de los activos. Permite enfocarse en quienes tienen chances reales.
**Diferencia con "Mensajes Insta, Face, what":** "Mensajes" es para quien recibió info y desapareció (potencialmente interesado). "Cliente perdido" es para quien expresó rechazo o lleva mucho tiempo sin responder.

---

### RECOMENDADAS COMO TAG MANUAL (no auto-tag)

---

#### 8. Comprador — TAG MANUAL
**Por qué no auto-tag:** No se puede saber con certeza desde el chat si la venta se concretó. El bot no tiene acceso al sistema de pagos ni confirmación real. Es mejor asignarlo manualmente cuando el vendedor confirma el pedido, o automáticamente cuando se crea una orden en el CRM.

**Alternativa:** Asignar esta etiqueta automáticamente cuando se crea/completa una orden desde el panel.

---

#### 9. Cliente recurrente — TAG MANUAL
**Por qué no auto-tag:** Requiere cruzar historial de órdenes. La IA no puede saber si es la segunda compra solo leyendo la conversación actual.

**Alternativa:** Asignar automáticamente cuando el contacto tiene 2 o más órdenes completadas en el sistema.

---

#### 10. Nuevo contacto — TAG MANUAL / SISTEMA
**Por qué no auto-tag:** Se puede detectar por fecha del primer mensaje, no por contenido. Es mejor asignarlo automáticamente al recibir el primer mensaje de un número nuevo (lógica en app.py, no IA).

**Alternativa:** En app.py, cuando se crea un contacto nuevo, asignarle automáticamente esta etiqueta.

---
---

## RESUMEN — QUÉ HACER

| # | Etiqueta                     | Acción             | Prioridad |
|---|------------------------------|--------------------|-----------|
| 1 | Asistencia Humana            | Modificar prompt   | Alta      |
| 2 | Pedido para más adelante     | Modificar prompt   | Alta      |
| 3 | Venta por cerrar             | Modificar prompt   | Alta      |
| 4 | Mensajes Insta, Face, what   | Modificar prompt   | Alta      |
| 5 | Consultó producto            | Crear como auto-tag| Media     |
| 6 | Cliente indeciso             | Crear como auto-tag| Media     |
| 7 | Cliente perdido              | Crear como auto-tag| Baja      |
| 8 | Comprador                    | Tag manual / orden | Alta      |
| 9 | Cliente recurrente           | Tag manual / orden | Baja      |
|10 | Nuevo contacto               | Lógica en app.py   | Media     |

---

## ORDEN DE EVALUACIÓN SUGERIDO (para evitar conflictos)

El auto tagger evalúa las reglas por separado, pero si un contacto puede caer en varias, conviene este orden de prioridad:

1. **Asistencia Humana** (más específico — hubo derivación explícita)
2. **Pedido para más adelante** (más específico — el cliente lo dijo explícitamente)
3. **Venta por cerrar** (intención activa de compra sin concretar)
4. **Cliente indeciso** (muchas preguntas, sin decisión)
5. **Mensajes Insta, Face, what** (recibió info, desapareció)
6. **Consultó producto** (solo preguntó, sin intención clara)
7. **Cliente perdido** (rechazo o silencio prolongado)
