"""
Migration script: Add conversation_notes table.
Run: python migrate_notes.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from models import db
from sqlalchemy import text

with app.app_context():
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS conversation_notes (
            id SERIAL PRIMARY KEY,
            phone_number VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """))
    db.session.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_conversation_notes_phone ON conversation_notes (phone_number);
    """))
    db.session.commit()
    print("✅ Table 'conversation_notes' created successfully.")
