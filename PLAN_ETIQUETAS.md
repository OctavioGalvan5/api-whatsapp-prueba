# Plan de Implementación: Sistema de Etiquetas y Campañas

## Objetivo
Transformar el sistema de etiquetas actual (texto libre) en un sistema gestionado robusto que permita segmentación precisa para campañas de marketing masivo.

## Fase 1: Gestión de Etiquetas (Core)
Prioridad inmediata. Formalizar las etiquetas en la base de datos.

1.  **Nuevo Modelo `Tag`**: 
    *   Tabla `whatsapp_tags` (id, name, color, created_at).
    *   Relación `many-to-many` con `Contact`.
2.  **Migración de Datos**: 
    *   Script para normalizar las etiquetas actuales (JSON) a la nueva tabla.
3.  **UI de Gestión (`/tags`)**:
    *   Formulario para CREAR etiquetas (Nombre, Color).
    *   Lista visual para EDITAR y ELIMINAR etiquetas.
4.  **Actualización de Contactos**:
    *   En Dashboard y Edición, usar un selector oficial de etiquetas (no texto libre).

## Fase 2: Etiquetado Masivo (Bulk Actions)
Herramientas para gestionar miles de contactos.

1.  **Selección Múltiple en Lista de Contactos**:
    *   Checkboxes en cada fila.
    *   Barra flotante: "Asignar Etiqueta", "Quitar Etiqueta" a los seleccionados.
2.  **Importación Avanzada (Excel)**:
    *   **Herramienta de Importación**: Subir Excel con columnas simples (celular).
    *   **Acción Masiva**: Elegir una etiqueta (ej: "Deudores Septiembre") y aplicarla a todos los números del Excel.
    *   **Limpieza**: Opción para "Quitar etiqueta" usando la misma lista de Excel.
3.  **Optimizaciones Backend**:
    *   Endpoints para actualizaciones por lotes (batch updates).

## Fase 3: Sistema de Campañas
Marketing masivo basado en segmentos.

1.  **Modelo `Campaign`**:
    *   Campos: nombre, template_usado, etiqueta_destino, fecha_programada, estado (borrador, enviando, completado).
2.  **Modelo `CampaignLog`**:
    *   Registro individual: campaign_id, contact_phone, message_id, status (sent, failed, read).
3.  **UI de Campañas**:
    *   **Nueva Campaña**: Wizard para elegir Template + Etiqueta de Segmento.
    *   **Monitor en Vivo**: Barra de progreso de envío.
    *   **Reportes**: KPIs de la campaña (Tasa de entrega, Tasa de lectura, Clics).
