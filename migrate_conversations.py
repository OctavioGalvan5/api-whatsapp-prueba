"""
Migration script to create conversation categorization tables.
Run: python migrate_conversations.py
"""
import os
import sys

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

from dotenv import load_dotenv
load_dotenv()

def migrate():
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        print("[ERROR] DATABASE_URL not configured")
        sys.exit(1)
    
    is_postgres = 'postgresql' in database_url or 'postgres' in database_url
    
    if is_postgres:
        import psycopg2
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        print("[INFO] Creating conversation categorization tables (PostgreSQL)...")
        
        # Create conversation_topics table
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_topics (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) UNIQUE NOT NULL,
                    description TEXT,
                    keywords JSON DEFAULT '[]',
                    color VARCHAR(20) DEFAULT 'blue',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print("[OK] Table conversation_topics created")
        except Exception as e:
            print(f"[WARN] conversation_topics: {e}")
        
        # Create conversation_sessions table
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_sessions (
                    id SERIAL PRIMARY KEY,
                    phone_number VARCHAR(20) NOT NULL,
                    topic_id INTEGER REFERENCES conversation_topics(id),
                    rating VARCHAR(20),
                    started_at TIMESTAMP NOT NULL,
                    ended_at TIMESTAMP NOT NULL,
                    message_count INTEGER DEFAULT 0,
                    summary TEXT,
                    auto_categorized BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print("[OK] Table conversation_sessions created")
        except Exception as e:
            print(f"[WARN] conversation_sessions: {e}")
        
        # Create indexes
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_phone_started 
                ON conversation_sessions(phone_number, started_at)
            """)
            print("[OK] Index idx_sessions_phone_started created")
        except Exception as e:
            print(f"[WARN] Index: {e}")
        
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_phone 
                ON conversation_sessions(phone_number)
            """)
            print("[OK] Index idx_sessions_phone created")
        except Exception as e:
            print(f"[WARN] Index: {e}")
        
        conn.commit()
        cursor.close()
        conn.close()
        
    else:
        # SQLite
        import sqlite3
        db_path = database_url.replace('sqlite:///', '')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("[INFO] Creating conversation categorization tables (SQLite)...")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversation_topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) UNIQUE NOT NULL,
                description TEXT,
                keywords JSON DEFAULT '[]',
                color VARCHAR(20) DEFAULT 'blue',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("[OK] Table conversation_topics created")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversation_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_number VARCHAR(20) NOT NULL,
                topic_id INTEGER REFERENCES conversation_topics(id),
                rating VARCHAR(20),
                started_at TIMESTAMP NOT NULL,
                ended_at TIMESTAMP NOT NULL,
                message_count INTEGER DEFAULT 0,
                summary TEXT,
                auto_categorized BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("[OK] Table conversation_sessions created")
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_phone_started 
            ON conversation_sessions(phone_number, started_at)
        """)
        print("[OK] Index created")
        
        conn.commit()
        cursor.close()
        conn.close()
    
    print("\n[OK] Migration completed successfully!")

if __name__ == '__main__':
    migrate()
