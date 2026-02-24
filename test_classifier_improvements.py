"""
Script para probar mejoras en el clasificador de conversaciones.
Simula conversaciones reales y verifica la clasificación.
"""
import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Casos de prueba basados en tus ejemplos
test_cases = [
    {
        "name": "Caso 1: Jubilado emocionado (NO debería necesitar ayuda humana)",
        "conversation": """[Usuario]: SOY JUBILADOOOO !!!!! SE DEBITA DE LA JUBILACIONNNNNN
[Bot]: [Campaña: Deuda obra social 1er envío 0226] [Template: deuda_obras_sociales]""",
        "expected_needs_human": False,
        "reason": "Usuario expresó emoción pero fue respondido con template relevante de obras sociales"
    },
    {
        "name": "Caso 2: Usuario informando pago (NO debería necesitar ayuda humana)",
        "conversation": """[Usuario]: Ya aboné la semana pasada e informe al sector contable
[Bot]: [Campaña: Deuda obra social 1er envío 0226] [Template: deuda_obras_sociales]
[Usuario]: Buenos días""",
        "expected_needs_human": False,
        "reason": "Usuario solo informó, no pidió ayuda. Saludo no requiere asistencia"
    },
    {
        "name": "Caso 3: Usuario planea acción (NO debería necesitar ayuda humana)",
        "conversation": """[Bot]: [Campaña: Deudores estado 14 - 2do envío] [Template: deudores_estado14_]
[Usuario]: Hola buenos días!
[Usuario]: Voy a pedir un turno para regularizar. Gracias""",
        "expected_needs_human": False,
        "reason": "Usuario informa que tomará acción, no requiere intervención"
    },
    {
        "name": "Caso 4: Pregunta de plan de pago sin respuesta (SÍ necesita ayuda humana)",
        "conversation": """[Bot]: [Campaña: Deudores estado 14 - 1er envío] [Template: deudores_estado14_]
[Bot]: [Campaña: Deudores estado 14 - 2do envío] [Template: deudores_estado14_]
[Usuario]: Hola buenas tardes! Se podrá hacer un plan de pago?.""",
        "expected_needs_human": True,
        "reason": "Pregunta específica sobre plan de pago personalizado sin respuesta del bot"
    },
    {
        "name": "Caso 5: Usuario pide hablar con alguien (SÍ necesita ayuda humana)",
        "conversation": """[Bot]: [Campaña: Recordatorio de deuda]
[Usuario]: Necesito hablar con alguien del área administrativa
[Usuario]: Es urgente""",
        "expected_needs_human": True,
        "reason": "Solicitud explícita de contacto humano con urgencia"
    },
    {
        "name": "Caso 6: Solo saludo (NO debería necesitar ayuda humana)",
        "conversation": """[Bot]: [Campaña: Deuda obra social 1er envío 0226]
[Usuario]: Buen día Mañana iré a la oficina de la Caja para regularizar la deuda
[Usuario]: Saludos""",
        "expected_needs_human": False,
        "reason": "Usuario confirma que irá a resolver, no necesita ayuda inmediata"
    }
]

def test_classification(conversation_text):
    """Prueba la clasificación de una conversación."""
    prompt = f"""Analiza esta conversación de WhatsApp entre un usuario y un bot de una caja de abogados y categorízala.

CONVERSACIÓN:
{conversation_text}

Responde SOLO con un JSON válido con este formato exacto:
{{
  "rating": "excelente|buena|neutral|mala|problematica",
  "summary": "resumen de 1-2 oraciones cortas",
  "has_unanswered_questions": true/false,
  "needs_human_assistance": true/false,
  "reasoning": "breve explicación de por qué marcaste needs_human_assistance así"
}}

Criterios para rating:
- excelente: El usuario recibió ayuda completa, información útil y quedó satisfecho
- buena: El usuario recibió información útil del bot o template automático
- neutral: Conversación fue informativa pero sin impacto claro, o solo saludos/confirmaciones
- mala: El usuario no obtuvo lo que buscaba, hubo confusión, o el bot no pudo ayudar
- problematica: Quejas explícitas, insultos, frustración clara, o usuario muy molesto

Criterios para has_unanswered_questions (analiza si hay PREGUNTAS REALES sin respuesta):
- true SOLO si:
  * El usuario hizo una PREGUNTA ESPECÍFICA (interrogación, solicitud de información) Y el bot NO respondió a esa pregunta
  * El bot dijo explícitamente "no tengo esa información" o "no puedo ayudarte con eso"
  * La conversación terminó con una pregunta del usuario sin ninguna respuesta del bot después
- false si:
  * Todas las preguntas fueron respondidas (incluso con templates automáticos)
  * El usuario solo hace comentarios, afirmaciones o exclamaciones (NO son preguntas)
  * El usuario solo saluda o se despide
  * El usuario informa algo sin esperar respuesta

Criterios para needs_human_assistance (SÉ MUY SELECTIVO, evita falsos positivos):
- true SOLO si se cumple AL MENOS UNO de estos casos GRAVES:
  * El usuario hizo una PREGUNTA ESPECÍFICA sobre temas complejos (planes de pago personalizados, casos especiales, trámites urgentes) Y el bot NO pudo responder adecuadamente
  * El usuario expresó QUEJA SERIA o frustración clara pidiendo solución
  * El usuario EXPLÍCITAMENTE pidió hablar con una persona, ser contactado, o que alguien lo llame
  * El bot dijo que no puede ayudar y sugirió contacto humano
  * Hay preguntas sin responder Y el tema es crítico (deudas, situaciones legales, urgencias)

- false si:
  * El usuario solo expresó emociones o exclamaciones pero fue atendido con información automática (templates/campañas)
  * El usuario solo saludó, se despidió, o dio las gracias
  * El usuario hizo un comentario informativo sin esperar acción específica
  * El usuario dijo que hará algo ("voy a ir", "llamaré después", etc.) sin pedir ayuda inmediata
  * La conversación fue respondida con templates informativos aunque sean genéricos (campañas, recordatorios automáticos)
  * El usuario preguntó algo básico y recibió template automático relevante

CONTEXTO IMPORTANTE:
- Los mensajes verdes son templates/campañas automáticas del sistema (NO del bot conversacional)
- Si un template automático responde adecuadamente al contexto del usuario, NO requiere asistencia humana
- Solo marca needs_human_assistance=true si el usuario realmente necesita interacción personalizada que el sistema automatizado no puede proporcionar

EJEMPLOS DE FALSOS POSITIVOS A EVITAR:
❌ "SOY JUBILADO!!!!" + template de obras sociales → needs_human_assistance=false (fue atendido con info relevante)
❌ "Ya aboné la semana pasada" → needs_human_assistance=false (es una afirmación, no pide ayuda)
❌ "Buenos días" → needs_human_assistance=false (solo saludo)
❌ "Voy a pedir un turno para regularizar" → needs_human_assistance=false (informa su plan, no pide ayuda)

EJEMPLOS DE VERDADEROS POSITIVOS:
✅ "Se podrá hacer un plan de pago?" + sin respuesta del bot → needs_human_assistance=true (pregunta específica sin respuesta)
✅ "Necesito hablar con alguien urgente" → needs_human_assistance=true (solicitud explícita)
✅ "El bot no me ayuda, esto es urgente" → needs_human_assistance=true (frustración + urgencia)"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres un analizador experto de conversaciones de atención al cliente. Tu trabajo es clasificar conversaciones con alta precisión, evitando falsos positivos. Sé muy selectivo al marcar conversaciones que requieren asistencia humana. Responde siempre en JSON válido."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=400
        )

        result_text = response.choices[0].message.content.strip()

        # Clean JSON if wrapped in markdown
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        return json.loads(result_text)

    except Exception as e:
        return {"error": str(e)}


def run_tests():
    """Ejecuta todos los casos de prueba y muestra resultados."""
    print("=" * 80)
    print("PRUEBA DE MEJORAS EN EL CLASIFICADOR DE CONVERSACIONES")
    print("=" * 80)
    print()

    total = len(test_cases)
    passed = 0
    failed = 0

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'=' * 80}")
        print(f"CASO {i}/{total}: {test_case['name']}")
        print(f"{'=' * 80}")
        print(f"\nConversación:")
        print(test_case['conversation'])
        print(f"\nEsperado needs_human_assistance: {test_case['expected_needs_human']}")
        print(f"Razón: {test_case['reason']}")

        result = test_classification(test_case['conversation'])

        if 'error' in result:
            print(f"\n❌ ERROR: {result['error']}")
            failed += 1
            continue

        actual_needs_human = result.get('needs_human_assistance', False)
        print(f"\nResultado de clasificación:")
        print(f"  - needs_human_assistance: {actual_needs_human}")
        print(f"  - has_unanswered_questions: {result.get('has_unanswered_questions', False)}")
        print(f"  - rating: {result.get('rating', 'N/A')}")
        print(f"  - summary: {result.get('summary', 'N/A')}")
        print(f"  - reasoning: {result.get('reasoning', 'N/A')}")

        if actual_needs_human == test_case['expected_needs_human']:
            print(f"\n✅ CORRECTO - El clasificador funcionó como esperado")
            passed += 1
        else:
            print(f"\n❌ INCORRECTO - Esperado: {test_case['expected_needs_human']}, Obtenido: {actual_needs_human}")
            failed += 1

    print(f"\n{'=' * 80}")
    print(f"RESUMEN FINAL")
    print(f"{'=' * 80}")
    print(f"Total de pruebas: {total}")
    print(f"✅ Pasadas: {passed} ({passed/total*100:.1f}%)")
    print(f"❌ Fallidas: {failed} ({failed/total*100:.1f}%)")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    run_tests()
