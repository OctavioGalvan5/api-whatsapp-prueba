# Actualizar Perfil de WhatsApp Business via API

## 📋 Resumen de capacidades

| Campo | ¿Se puede modificar via API? | Límite/Notas |
|-------|----------------------------|--------------|
| **Descripción (About)** | ✅ SÍ | Máximo 256 caracteres |
| **Descripción larga** | ✅ SÍ | Máximo 512 caracteres |
| **Dirección** | ✅ SÍ | Texto libre |
| **Email** | ✅ SÍ | Email válido |
| **Sitio web** | ✅ SÍ | Hasta 2 URLs |
| **Categoría (Vertical)** | ✅ SÍ | Lista predefinida |
| **Nombre del negocio** | ❌ NO | Solo desde Meta Business Manager |
| **Foto de perfil** | ❌ NO | Solo desde Meta Business Manager |

---

## 🔧 Ejemplo 1: Actualizar solo la descripción

### cURL
```bash
curl -X POST "https://graph.facebook.com/v21.0/PHONE_NUMBER_ID/whatsapp_business_profile" \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product": "whatsapp",
    "about": "Caja de Abogados de Salta - Atención al afiliado"
  }'
```

### JavaScript (fetch)
```javascript
const updateDescription = async () => {
  const response = await fetch(
    'https://graph.facebook.com/v21.0/PHONE_NUMBER_ID/whatsapp_business_profile',
    {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer ACCESS_TOKEN',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        messaging_product: 'whatsapp',
        about: 'Caja de Abogados de Salta - Atención al afiliado'
      })
    }
  );

  const data = await response.json();
  console.log(data);
};
```

---

## 🔧 Ejemplo 2: Actualizar información completa

### cURL
```bash
curl -X POST "https://graph.facebook.com/v21.0/PHONE_NUMBER_ID/whatsapp_business_profile" \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product": "whatsapp",
    "about": "Caja de Abogados de Salta - Asistencia a afiliados",
    "address": "Dirección de la delegación central, Salta Capital",
    "description": "Institución que brinda servicios y beneficios a abogados colegiados de la provincia de Salta.",
    "email": "mesadeentrada@cajaabogadossalta.com.ar",
    "vertical": "PROF_SERVICES",
    "websites": ["https://www.cajaabogadossalta.com.ar"]
  }'
```

---

## 🔧 Ejemplo 3: Obtener información actual del perfil

### cURL
```bash
curl -X GET "https://graph.facebook.com/v21.0/PHONE_NUMBER_ID/whatsapp_business_profile?fields=about,address,description,email,profile_picture_url,websites,vertical" \
  -H "Authorization: Bearer ACCESS_TOKEN"
```

### Respuesta ejemplo:
```json
{
  "data": [
    {
      "about": "Caja de Abogados de Salta - Asistencia a afiliados",
      "address": "Dirección de la delegación central, Salta Capital",
      "description": "Institución que brinda servicios y beneficios a abogados colegiados de la provincia de Salta.",
      "email": "mesadeentrada@cajaabogadossalta.com.ar",
      "profile_picture_url": "https://...",
      "websites": [
        "https://www.cajaabogadossalta.com.ar"
      ],
      "vertical": "PROF_SERVICES",
      "id": "PHONE_NUMBER_ID"
    }
  ]
}
```

---

## 🔧 Ejemplo 4: Integración en n8n (HTTP Request Node)

### Configuración del nodo HTTP Request:

**Method:** POST

**URL:**
```
https://graph.facebook.com/v21.0/{{$node["Set Variables"].json["phone_number_id"]}}/whatsapp_business_profile
```

**Authentication:** None (usar Header)

**Headers:**
```json
{
  "Authorization": "Bearer {{$node["Set Variables"].json["access_token"]}}",
  "Content-Type": "application/json"
}
```

**Body (JSON):**
```json
{
  "messaging_product": "whatsapp",
  "about": "Caja de Abogados de Salta - Atención al afiliado",
  "address": "Calle Ejemplo 123, Salta Capital",
  "description": "Institución que brinda servicios y beneficios a abogados colegiados de Salta. Subsidios, préstamos y más.",
  "email": "mesadeentrada@cajaabogadossalta.com.ar",
  "vertical": "PROF_SERVICES",
  "websites": ["https://www.cajaabogadossalta.com.ar"]
}
```

---

## 📝 Categorías de negocio disponibles (vertical)

Algunas categorías comunes:

- `AUTO` - Automotriz
- `BEAUTY` - Belleza, spa, salón
- `APPAREL` - Ropa y accesorios
- `EDU` - Educación
- `ENTERTAIN` - Entretenimiento
- `EVENT_PLAN` - Planificación de eventos
- `FINANCE` - Finanzas y banca
- `GROCERY` - Supermercado
- `GOVT` - Gobierno
- `HOTEL` - Hotel y alojamiento
- `HEALTH` - Salud
- `NONPROFIT` - Organización sin fines de lucro
- **`PROF_SERVICES`** - **Servicios profesionales** ✅ (Recomendado)
- `RETAIL` - Retail
- `TRAVEL` - Viajes y turismo
- `RESTAURANT` - Restaurante
- `NOT_A_BIZ` - No es un negocio

---

## 🚨 Limitaciones importantes

1. **Nombre del negocio (Display Name):**
   - ❌ NO se puede cambiar via API
   - Solo se puede modificar desde [Meta Business Manager](https://business.facebook.com/)
   - Requiere verificación manual

2. **Foto de perfil:**
   - ❌ NO se puede cambiar via API
   - Solo se puede modificar desde [Meta Business Manager](https://business.facebook.com/)

3. **Límites de caracteres:**
   - `about`: máximo 256 caracteres
   - `description`: máximo 512 caracteres
   - `address`: sin límite específico, pero razonable

4. **Websites:**
   - Máximo 2 URLs
   - Deben ser URLs válidas con protocolo (https://)

---

## 🔍 Cómo obtener tu PHONE_NUMBER_ID

```bash
curl -X GET "https://graph.facebook.com/v21.0/WABA_ID/phone_numbers" \
  -H "Authorization: Bearer ACCESS_TOKEN"
```

Respuesta:
```json
{
  "data": [
    {
      "verified_name": "Caja de Abogados de Salta",
      "display_phone_number": "+54 9 387 xxx xxxx",
      "id": "123456789012345",  // <-- Este es tu PHONE_NUMBER_ID
      "quality_rating": "GREEN"
    }
  ]
}
```

---

## 📚 Referencias

- [Documentación oficial de WhatsApp Business Profile API](https://developers.facebook.com/docs/whatsapp/business-management-api/manage-profile)
- [Meta Business Manager](https://business.facebook.com/)
- [WhatsApp Business API Reference](https://developers.facebook.com/docs/whatsapp/cloud-api/reference/business-profiles)
