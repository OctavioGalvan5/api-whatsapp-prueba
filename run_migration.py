"""
Script de setup inicial para nuevas instancias en Supabase.

Uso:
  python run_migration.py

Genera el SQL que hay que pegar en el SQL Editor de Supabase.
La contrasena del admin se toma de LOGIN_PASSWORD en el .env (default: 'admin').
"""
import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

admin_password = os.getenv("LOGIN_PASSWORD", "admin")
password_hash = generate_password_hash(admin_password)

sql = f"""-- ============================================================
-- Setup inicial - pegar en SQL Editor de Supabase
-- ============================================================

-- 1. Dar permisos a postgres sobre las tablas del CRM
GRANT ALL PRIVILEGES ON TABLE crm_users TO postgres;
GRANT ALL PRIVILEGES ON TABLE crm_user_permissions TO postgres;
GRANT USAGE, SELECT ON SEQUENCE crm_users_id_seq TO postgres;

-- 2. Crear usuario admin inicial (contrasena desde .env LOGIN_PASSWORD)
INSERT INTO crm_users (username, display_name, password_hash, is_admin, is_active)
VALUES ('admin', 'Administrador', '{password_hash}', true, true)
ON CONFLICT (username) DO NOTHING;

-- ============================================================
"""

print(sql)
print("Instrucciones:")
print("  1. Copia el SQL de arriba")
print("  2. Pegalo en el SQL Editor de tu proyecto Supabase")
print("  3. Ejecutalo")
print(f"  4. Ingresa con usuario 'admin' y contrasena '{admin_password}'")
