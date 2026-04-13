-- ==========================================
-- MIGRACIÓN: Sistema de Re-engagement
-- Ejecutar en Supabase SQL Editor
-- ==========================================

-- 1. AUTO TAG RULES (sin dependencias)
CREATE TABLE IF NOT EXISTS auto_tag_rules (
    id SERIAL PRIMARY KEY,
    tag_id INTEGER NOT NULL REFERENCES whatsapp_tags(id) ON DELETE CASCADE,
    prompt_condition TEXT NOT NULL,
    inactivity_minutes INTEGER DEFAULT 30,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Si la tabla ya existe, agregar la columna si falta
ALTER TABLE auto_tag_rules ADD COLUMN IF NOT EXISTS activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- 2. AUTO TAG LOGS (depende de auto_tag_rules)
CREATE TABLE IF NOT EXISTS auto_tag_logs (
    id SERIAL PRIMARY KEY,
    rule_id INTEGER REFERENCES auto_tag_rules(id) ON DELETE SET NULL,
    contact_id INTEGER REFERENCES whatsapp_contacts(id) ON DELETE SET NULL,
    phone_number VARCHAR(20) NOT NULL,
    tag_id INTEGER REFERENCES whatsapp_tags(id) ON DELETE SET NULL,
    result VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_auto_tag_logs_created ON auto_tag_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_auto_tag_logs_result ON auto_tag_logs(result);

-- 3. FOLLOW-UP SEQUENCES (sin dependencias)
CREATE TABLE IF NOT EXISTS followup_sequences (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    tag_id INTEGER NOT NULL REFERENCES whatsapp_tags(id) ON DELETE CASCADE,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. FOLLOW-UP STEPS (depende de followup_sequences)
CREATE TABLE IF NOT EXISTS followup_steps (
    id SERIAL PRIMARY KEY,
    sequence_id INTEGER NOT NULL REFERENCES followup_sequences(id) ON DELETE CASCADE,
    "order" INTEGER NOT NULL,
    delay_hours FLOAT NOT NULL,
    template_name VARCHAR(100) NOT NULL,
    template_language VARCHAR(10) DEFAULT 'es_AR',
    template_params JSON,
    remove_tag_on_execute BOOLEAN DEFAULT FALSE
);

-- Si las tablas ya existen, agregar columnas si faltan
ALTER TABLE followup_sequences ADD COLUMN IF NOT EXISTS send_window_start VARCHAR(5);
ALTER TABLE followup_sequences ADD COLUMN IF NOT EXISTS send_window_end VARCHAR(5);
ALTER TABLE followup_sequences ADD COLUMN IF NOT EXISTS send_weekdays JSON;
ALTER TABLE followup_steps ADD COLUMN IF NOT EXISTS remove_tag_on_execute BOOLEAN DEFAULT FALSE;
ALTER TABLE followup_steps ADD COLUMN IF NOT EXISTS schedule_type VARCHAR(20) DEFAULT 'delay';
ALTER TABLE followup_steps ADD COLUMN IF NOT EXISTS scheduled_weekday INTEGER;
ALTER TABLE followup_steps ADD COLUMN IF NOT EXISTS scheduled_time VARCHAR(5);

-- 5. FOLLOW-UP ENROLLMENTS (depende de followup_sequences y whatsapp_contacts)
CREATE TABLE IF NOT EXISTS followup_enrollments (
    id SERIAL PRIMARY KEY,
    contact_id INTEGER NOT NULL REFERENCES whatsapp_contacts(id) ON DELETE CASCADE,
    sequence_id INTEGER NOT NULL REFERENCES followup_sequences(id) ON DELETE CASCADE,
    current_step INTEGER DEFAULT 1,
    status VARCHAR(20) DEFAULT 'pending',
    next_send_at TIMESTAMP,
    enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    cancelled_at TIMESTAMP,
    CONSTRAINT uq_enrollment_contact_sequence UNIQUE (contact_id, sequence_id)
);

CREATE INDEX IF NOT EXISTS idx_enrollments_status_next ON followup_enrollments(status, next_send_at);

-- PERMISOS
GRANT ALL PRIVILEGES ON TABLE auto_tag_rules TO PUBLIC;
GRANT ALL PRIVILEGES ON TABLE auto_tag_logs TO PUBLIC;
GRANT ALL PRIVILEGES ON TABLE followup_sequences TO PUBLIC;
GRANT ALL PRIVILEGES ON TABLE followup_steps TO PUBLIC;
GRANT ALL PRIVILEGES ON TABLE followup_enrollments TO PUBLIC;

GRANT USAGE, SELECT ON SEQUENCE auto_tag_rules_id_seq TO PUBLIC;
GRANT USAGE, SELECT ON SEQUENCE auto_tag_logs_id_seq TO PUBLIC;
GRANT USAGE, SELECT ON SEQUENCE followup_sequences_id_seq TO PUBLIC;
GRANT USAGE, SELECT ON SEQUENCE followup_steps_id_seq TO PUBLIC;
GRANT USAGE, SELECT ON SEQUENCE followup_enrollments_id_seq TO PUBLIC;
