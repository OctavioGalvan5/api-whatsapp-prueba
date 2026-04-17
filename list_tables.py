import os
from sqlalchemy import create_engine, inspect

database_url = "postgresql://postgres.your-tenant-id:9sncpyfxnajnypnitzjgue8is9jacc9c@76.13.233.143:6543/postgres"
engine = create_engine(database_url)
inspector = inspect(engine)

print("=== TABLAS EN LA BASE DE DATOS ===")
tables = inspector.get_table_names()
for table_name in tables:
    columns = inspector.get_columns(table_name)
    col_names = [col['name'] for col in columns]
    
    # Check if it looks like a chat memory table
    is_memory = any(c in col_names for c in ['session_id', 'message', 'role', 'content'])
    
    if is_memory:
        print(f"[*] {table_name}  <-- PROBABLE TABLA DE MEMORIA N8N")
        print(f"    Columnas: {', '.join(col_names)}")
    else:
        print(f"[ ] {table_name}")

print("\nScript ejecutado exitosamente.")
