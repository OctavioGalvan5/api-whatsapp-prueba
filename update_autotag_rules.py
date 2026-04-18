"""
Actualiza los prompts de las reglas de auto-tagging con versiones mejoradas.
Ejecutar: python update_autotag_rules.py
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL_caja')

REGLAS_MEJORADAS = [
    {
        "tag_name": "Asistencia Humana",
        "prompt": (
            "¿En la conversación el bot derivó al cliente a hablar con una persona humana, "
            "o lo invitó a contactar por otro medio (teléfono, sucursal, WhatsApp de vendedor, etc.), "
            "y el cliente no realizó una compra?"
        )
    },
    {
        "tag_name": "Pedido para más adelante",
        "prompt": (
            "¿El cliente expresó explícitamente que quiere comprar pero en otro momento? "
            "Por ejemplo: 'después', 'más adelante', 'la semana que viene', 'cuando tenga plata', "
            "'te aviso', 'lo pienso', etc. La conversación terminó sin concretarse la venta."
        )
    },
    {
        "tag_name": "Venta por cerrar",
        "prompt": (
            "¿El cliente mostró interés claro en comprar (pidió precio de un producto específico, "
            "preguntó cómo pagar, preguntó por el envío, o dijo que lo quiere), el bot respondió "
            "con información sobre el producto o precio, pero la compra no se concretó? "
            "Respondé SI solo si el cliente mostró intención activa, no si solo hizo una consulta general."
        )
    },
    {
        "tag_name": "Mensajes Insta, Face, what",
        "prompt": (
            "¿El bot proporcionó información sobre algún producto (precio, descripción, beneficios, "
            "combos o modos de uso) y el cliente dejó de responder, o solo respondió con algo como "
            "'gracias', 'ok', 'dale', sin realizar ninguna compra? "
            "Respondé SI aunque el bot no haya mencionado explícitamente formas de pago o envío — "
            "alcanza con que haya dado información de precio o producto."
        )
    },
]

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

print("=" * 60)
print("Actualizando reglas de auto-tagging...")
print("=" * 60)

actualizadas = 0
no_encontradas = []

for regla in REGLAS_MEJORADAS:
    tag_name = regla["tag_name"]
    nuevo_prompt = regla["prompt"]

    # Buscar la regla por nombre de etiqueta
    cur.execute("""
        SELECT atr.id, atr.prompt_condition
        FROM auto_tag_rules atr
        JOIN whatsapp_tags wt ON wt.id = atr.tag_id
        WHERE wt.name = %s
    """, (tag_name,))

    rows = cur.fetchall()

    if not rows:
        print(f"\n⚠️  No se encontró regla para etiqueta: '{tag_name}'")
        no_encontradas.append(tag_name)
        continue

    for rule_id, prompt_viejo in rows:
        cur.execute("""
            UPDATE auto_tag_rules
            SET prompt_condition = %s
            WHERE id = %s
        """, (nuevo_prompt, rule_id))

        print(f"\n✅ Regla #{rule_id} — '{tag_name}'")
        print(f"   ANTES : {prompt_viejo[:80]}...")
        print(f"   AHORA : {nuevo_prompt[:80]}...")
        actualizadas += 1

print("\n" + "=" * 60)
print(f"✅ {actualizadas} regla(s) actualizada(s).")

if no_encontradas:
    print(f"⚠️  No encontradas: {', '.join(no_encontradas)}")
    print("   Verificá que los nombres de las etiquetas sean exactos.")

# Limpiar el cache para que las conversaciones sean re-analizadas
print("\nLimpiando cache del auto-tagger...")
cur.execute("DELETE FROM chatbot_config WHERE key LIKE 'auto_tag_%'")
print("✅ Cache limpiado — las conversaciones serán re-analizadas en el próximo ciclo.")

cur.close()
conn.close()
print("=" * 60)
print("Listo.")
