"""
Test script for conversation categorization.
Run: python test_categorization.py
"""
import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import Message, ConversationTopic, ConversationSession
from conversation_categorizer import run_categorization, split_into_sessions

TEST_PHONE = "test_5491100000000"

def create_test_topics():
    """Create sample topics if they don't exist."""
    with app.app_context():
        if ConversationTopic.query.count() == 0:
            topics = [
                ConversationTopic(
                    name="Consultas de Afiliación",
                    description="Preguntas sobre cómo afiliarse, requisitos, documentos",
                    keywords=["afiliar", "inscribir", "requisitos", "documentos", "matricula"],
                    color="blue"
                ),
                ConversationTopic(
                    name="Pagos y Cuotas",
                    description="Consultas sobre pagos, vencimientos, deudas",
                    keywords=["pago", "cuota", "debe", "vencimiento", "saldo", "factura"],
                    color="green"
                ),
                ConversationTopic(
                    name="Quejas y Reclamos",
                    description="Usuarios con problemas o quejas",
                    keywords=["queja", "problema", "mal", "reclamo", "furioso"],
                    color="red"
                )
            ]
            for t in topics:
                db.session.add(t)
            db.session.commit()
            print("✅ Created 3 test topics")
        else:
            print(f"ℹ️ Topics already exist ({ConversationTopic.query.count()} topics)")

def create_test_messages():
    """Create sample conversation messages."""
    with app.app_context():
        # Delete old test messages
        Message.query.filter(Message.phone_number == TEST_PHONE).delete()
        db.session.commit()
        
        # Create a sample conversation about payments
        now = datetime.utcnow() - timedelta(minutes=20)  # 20 min ago (so it's inactive)
        
        messages = [
            ("inbound", "Hola, quiero consultar sobre mi cuota", now),
            ("outbound", "¡Hola! Con gusto te ayudo. ¿Cuál es tu número de matrícula?", now + timedelta(seconds=30)),
            ("inbound", "Mi matrícula es 12345", now + timedelta(minutes=1)),
            ("outbound", "Perfecto. Tu cuota del mes de febrero está pendiente de pago. El vencimiento es el día 10.", now + timedelta(minutes=2)),
            ("inbound", "¿Cómo puedo pagar?", now + timedelta(minutes=3)),
            ("outbound", "Podés pagar por transferencia bancaria o en efectivo en nuestras oficinas. Te envío los datos...", now + timedelta(minutes=4)),
            ("inbound", "Gracias, voy a pagar ahora", now + timedelta(minutes=5)),
            ("outbound", "¡Perfecto! Cualquier duda me avisás. ¡Buen día!", now + timedelta(minutes=6)),
        ]
        
        for direction, content, timestamp in messages:
            msg = Message(
                phone_number=TEST_PHONE,
                direction=direction,
                content=content,
                message_type="text",
                timestamp=timestamp
            )
            db.session.add(msg)
        
        db.session.commit()
        print(f"✅ Created {len(messages)} test messages (conversation about payments)")

def run_test():
    """Run the categorization on test data."""
    with app.app_context():
        # Get messages
        messages = Message.query.filter(
            Message.phone_number == TEST_PHONE
        ).order_by(Message.timestamp).all()
        
        print(f"\n📱 Test messages for {TEST_PHONE}:")
        for m in messages:
            role = "👤" if m.direction == "inbound" else "🤖"
            print(f"  {role} {m.content[:60]}...")
        
        # Check session splitting
        sessions = split_into_sessions(messages)
        print(f"\n📊 Sessions detected: {len(sessions)}")
        for i, s in enumerate(sessions):
            print(f"  Session {i+1}: {len(s)} messages, {s[0].timestamp} to {s[-1].timestamp}")
        
        # Run categorization
        print("\n🤖 Running OpenAI categorization...")
        run_categorization(app.app_context())
        
        # Check results
        session = ConversationSession.query.filter(
            ConversationSession.phone_number == TEST_PHONE
        ).order_by(ConversationSession.id.desc()).first()
        
        if session:
            print("\n✅ CATEGORIZATION RESULT:")
            print(f"  Topic: {session.topic.name if session.topic else 'Sin categorizar'}")
            print(f"  Rating: {session.rating}")
            print(f"  Summary: {session.summary}")
            print(f"  Messages: {session.message_count}")
        else:
            print("\n❌ No session created - check OPENAI_API_KEY and topics")

def cleanup():
    """Remove test data."""
    with app.app_context():
        Message.query.filter(Message.phone_number == TEST_PHONE).delete()
        ConversationSession.query.filter(ConversationSession.phone_number == TEST_PHONE).delete()
        db.session.commit()
        print("\n🧹 Test data cleaned up")

if __name__ == "__main__":
    print("=" * 50)
    print("CONVERSATION CATEGORIZATION TEST")
    print("=" * 50)
    
    create_test_topics()
    create_test_messages()
    run_test()
    
    # Ask to cleanup
    resp = input("\n¿Limpiar datos de prueba? (s/n): ")
    if resp.lower() == 's':
        cleanup()
