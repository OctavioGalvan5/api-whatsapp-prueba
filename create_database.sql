-- ==========================================
-- Script de creación de base de datos
-- WhatsApp CRM + Chatbot RAG
-- Estructura completa SIN datos
-- Actualizado: 2026-04-16
-- ==========================================

-- Extensión para vectores (pgvector)
CREATE EXTENSION IF NOT EXISTS vector;

-- ==========================================
-- CHATBOT CONFIG
-- ==========================================
CREATE TABLE IF NOT EXISTS chatbot_config (
    id SERIAL PRIMARY KEY,
    key VARCHAR(50) UNIQUE NOT NULL,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- CONVERSATION TOPICS
-- ==========================================
CREATE TABLE IF NOT EXISTS conversation_topics (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    keywords JSON DEFAULT '[]',
    color VARCHAR(20) DEFAULT 'blue',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- CONVERSATION SESSIONS
-- ==========================================
CREATE TABLE IF NOT EXISTS conversation_sessions (
    id SERIAL PRIMARY KEY,
    phone_number VARCHAR(20) NOT NULL,
    topic_id INTEGER REFERENCES conversation_topics(id) ON DELETE SET NULL,
    rating VARCHAR(20),
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP NOT NULL,
    message_count INTEGER DEFAULT 0,
    summary TEXT,
    auto_categorized BOOLEAN DEFAULT TRUE,
    has_unanswered_questions BOOLEAN DEFAULT FALSE NOT NULL,
    escalated_to_human BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sessions_phone_started ON conversation_sessions(phone_number, started_at);

-- ==========================================
-- DOCUMENT METADATA (para RAG / n8n)
-- ==========================================
CREATE TABLE IF NOT EXISTS document_metadata (
    id TEXT PRIMARY KEY,
    title TEXT,
    url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- DOCUMENT ROWS (para tablas de Excel/CSV)
-- ==========================================
CREATE TABLE IF NOT EXISTS document_rows (
    id BIGSERIAL PRIMARY KEY,
    dataset_id TEXT,
    row_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- DOCUMENTS PG (vectores pgvector)
-- ==========================================
CREATE TABLE IF NOT EXISTS documents_pg (
    id BIGSERIAL PRIMARY KEY,
    text TEXT,
    metadata JSONB,
    embedding vector(3072)
);

-- ==========================================
-- LANGCHAIN COLLECTIONS
-- ==========================================
CREATE TABLE IF NOT EXISTS langchain_pg_collection (
    uuid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255),
    cmetadata JSONB
);

-- ==========================================
-- LANGCHAIN EMBEDDINGS
-- ==========================================
CREATE TABLE IF NOT EXISTS langchain_pg_embedding (
    id BIGSERIAL PRIMARY KEY,
    collection_id UUID REFERENCES langchain_pg_collection(uuid) ON DELETE CASCADE,
    embedding vector(3072),
    document TEXT,
    cmetadata JSONB
);

-- ==========================================
-- N8N CHAT HISTORIES
-- ==========================================
CREATE TABLE IF NOT EXISTS n8n_chat_histories (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL,
    message JSONB NOT NULL
);

-- ==========================================
-- RAG DOCUMENTS
-- ==========================================
CREATE TABLE IF NOT EXISTS rag_documents (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    file_size INTEGER NOT NULL,
    file_hash VARCHAR(64) NOT NULL,
    minio_path VARCHAR(500) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rag_documents_file_hash ON rag_documents(file_hash);

-- ==========================================
-- WHATSAPP TAGS
-- ==========================================
CREATE TABLE IF NOT EXISTS whatsapp_tags (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    color VARCHAR(20) DEFAULT 'green',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    is_system BOOLEAN DEFAULT FALSE NOT NULL
);

-- ==========================================
-- WHATSAPP CONTACTS
-- ==========================================
CREATE TABLE IF NOT EXISTS whatsapp_contacts (
    id SERIAL PRIMARY KEY,
    contact_id VARCHAR(50) UNIQUE,
    phone_number VARCHAR(20) NOT NULL,
    name VARCHAR(100),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    notes TEXT,
    custom_field_1 VARCHAR(255),
    custom_field_2 VARCHAR(255),
    custom_field_3 VARCHAR(255),
    custom_field_4 VARCHAR(255),
    custom_field_5 VARCHAR(255),
    custom_field_6 VARCHAR(255),
    custom_field_7 VARCHAR(255),
    tags JSON DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_contacts_phone ON whatsapp_contacts(phone_number);
CREATE INDEX IF NOT EXISTS idx_contacts_contact_id ON whatsapp_contacts(contact_id);
CREATE INDEX IF NOT EXISTS idx_contacts_name ON whatsapp_contacts(name);

-- ==========================================
-- WHATSAPP CONTACT TAGS (tabla de asociación)
-- ==========================================
CREATE TABLE IF NOT EXISTS whatsapp_contact_tags (
    contact_id INTEGER NOT NULL REFERENCES whatsapp_contacts(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES whatsapp_tags(id) ON DELETE CASCADE,
    PRIMARY KEY (contact_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_contact_tags_tag ON whatsapp_contact_tags(tag_id);

-- ==========================================
-- WHATSAPP MESSAGES
-- ==========================================
CREATE TABLE IF NOT EXISTS whatsapp_messages (
    id SERIAL PRIMARY KEY,
    wa_message_id VARCHAR(100) UNIQUE,
    phone_number VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    message_type VARCHAR(20) NOT NULL,
    content TEXT,
    media_id VARCHAR(100),
    media_url TEXT,
    caption TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sent_by VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS ix_messages_phone_ts ON whatsapp_messages(phone_number, timestamp);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON whatsapp_messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_messages_phone ON whatsapp_messages(phone_number);
CREATE INDEX IF NOT EXISTS idx_messages_direction ON whatsapp_messages(direction);

-- ==========================================
-- WHATSAPP MESSAGE STATUSES
-- ==========================================
CREATE TABLE IF NOT EXISTS whatsapp_message_statuses (
    id SERIAL PRIMARY KEY,
    wa_message_id VARCHAR(100) NOT NULL REFERENCES whatsapp_messages(wa_message_id),
    status VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    error_code VARCHAR(50),
    error_title VARCHAR(200),
    error_details TEXT
);

CREATE INDEX IF NOT EXISTS idx_statuses_wa_id ON whatsapp_message_statuses(wa_message_id);
CREATE INDEX IF NOT EXISTS idx_statuses_status ON whatsapp_message_statuses(status);
CREATE INDEX IF NOT EXISTS idx_statuses_timestamp ON whatsapp_message_statuses(timestamp);

-- ==========================================
-- WHATSAPP CAMPAIGNS
-- ==========================================
CREATE TABLE IF NOT EXISTS whatsapp_campaigns (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    template_name VARCHAR(100) NOT NULL,
    template_language VARCHAR(10) DEFAULT 'es_AR',
    tag_id INTEGER NOT NULL REFERENCES whatsapp_tags(id),
    status VARCHAR(20) DEFAULT 'draft',
    variables JSON,
    scheduled_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100)
);

-- ==========================================
-- WHATSAPP CAMPAIGN LOGS
-- ==========================================
CREATE TABLE IF NOT EXISTS whatsapp_campaign_logs (
    id SERIAL PRIMARY KEY,
    campaign_id INTEGER NOT NULL REFERENCES whatsapp_campaigns(id) ON DELETE CASCADE,
    contact_id INTEGER REFERENCES whatsapp_contacts(id),
    contact_phone VARCHAR(20) NOT NULL,
    message_id VARCHAR(100),
    status VARCHAR(20) DEFAULT 'pending',
    error_detail TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_campaign_contact_log UNIQUE (campaign_id, contact_id)
);

CREATE INDEX IF NOT EXISTS idx_campaign_logs_campaign_status ON whatsapp_campaign_logs(campaign_id, status);
CREATE INDEX IF NOT EXISTS idx_campaign_logs_campaign_contact ON whatsapp_campaign_logs(campaign_id, contact_id);

-- ==========================================
-- CONVERSATION NOTES (notas internas del equipo)
-- ==========================================
CREATE TABLE IF NOT EXISTS conversation_notes (
    id SERIAL PRIMARY KEY,
    phone_number VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_conversation_notes_phone ON conversation_notes(phone_number);

-- ==========================================
-- CRM USERS
-- ==========================================
CREATE TABLE IF NOT EXISTS crm_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    can_see_untagged BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- CRM USER PERMISSIONS
-- ==========================================
CREATE TABLE IF NOT EXISTS crm_user_permissions (
    user_id INTEGER NOT NULL REFERENCES crm_users(id) ON DELETE CASCADE,
    permission VARCHAR(50) NOT NULL,
    PRIMARY KEY (user_id, permission)
);

-- ==========================================
-- CRM USER TAG VISIBILITY
-- ==========================================
CREATE TABLE IF NOT EXISTS crm_user_tag_visibility (
    user_id INTEGER NOT NULL REFERENCES crm_users(id) ON DELETE CASCADE,
    tag_id  INTEGER NOT NULL REFERENCES whatsapp_tags(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, tag_id)
);

-- ==========================================
-- AUTO TAG RULES
-- ==========================================
CREATE TABLE IF NOT EXISTS auto_tag_rules (
    id SERIAL PRIMARY KEY,
    tag_id INTEGER NOT NULL REFERENCES whatsapp_tags(id) ON DELETE CASCADE,
    prompt_condition TEXT NOT NULL,
    inactivity_minutes INTEGER DEFAULT 30,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- AUTO TAG LOGS
-- ==========================================
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

-- ==========================================
-- FOLLOW-UP SEQUENCES
-- ==========================================
CREATE TABLE IF NOT EXISTS followup_sequences (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    tag_id INTEGER NOT NULL REFERENCES whatsapp_tags(id) ON DELETE CASCADE,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    send_window_start VARCHAR(5),
    send_window_end VARCHAR(5),
    send_weekdays JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- FOLLOW-UP STEPS
-- ==========================================
CREATE TABLE IF NOT EXISTS followup_steps (
    id SERIAL PRIMARY KEY,
    sequence_id INTEGER NOT NULL REFERENCES followup_sequences(id) ON DELETE CASCADE,
    "order" INTEGER NOT NULL,
    delay_hours FLOAT NOT NULL,
    template_name VARCHAR(100) NOT NULL,
    template_language VARCHAR(10) DEFAULT 'es_AR',
    template_params JSON,
    remove_tag_on_execute BOOLEAN DEFAULT FALSE,
    schedule_type VARCHAR(20) DEFAULT 'delay',
    scheduled_weekday INTEGER,
    scheduled_time VARCHAR(5)
);

-- ==========================================
-- FOLLOW-UP ENROLLMENTS
-- ==========================================
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

-- ==========================================
-- CATALOG PRODUCTS
-- ==========================================
CREATE TABLE IF NOT EXISTS catalog_products (
    retailer_id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price NUMERIC(12, 2),
    currency VARCHAR(10) DEFAULT 'ARS',
    availability VARCHAR(20) DEFAULT 'in stock',
    image_url TEXT,
    meta_product_id VARCHAR(100),
    synced_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- ORDERS
-- ==========================================
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    contact_id INTEGER REFERENCES whatsapp_contacts(id) ON DELETE SET NULL,
    phone_number VARCHAR(20) NOT NULL,
    source VARCHAR(20) DEFAULT 'whatsapp',
    wa_message_id VARCHAR(100),
    status VARCHAR(30) DEFAULT 'pendiente',
    payment_status VARCHAR(20) DEFAULT 'sin_pagar',
    payment_method VARCHAR(20),
    total NUMERIC(12, 2),
    currency VARCHAR(10) DEFAULT 'ARS',
    shipping_address TEXT,
    notes TEXT,
    seen_at TIMESTAMP,
    seen_by_id INTEGER REFERENCES crm_users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id INTEGER REFERENCES crm_users(id) ON DELETE SET NULL,
    last_edited_by_id INTEGER REFERENCES crm_users(id) ON DELETE SET NULL,
    terminated_at TIMESTAMP,
    terminated_by_id INTEGER REFERENCES crm_users(id) ON DELETE SET NULL,
    delivery_date DATE,
    delivery_time VARCHAR(5),
    earliest_arrival_time VARCHAR(5),
    latest_arrival_time VARCHAR(5),
    recipient_name VARCHAR(255),
    recipient_phone VARCHAR(30),
    latitude NUMERIC(10, 7),
    longitude NUMERIC(10, 7)
);

CREATE INDEX IF NOT EXISTS idx_orders_contact ON orders(contact_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_seen_at ON orders(seen_at);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);

-- ==========================================
-- ORDER ITEMS
-- ==========================================
CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    retailer_id VARCHAR(100) NOT NULL,
    product_name VARCHAR(255) NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_price NUMERIC(12, 2) NOT NULL,
    currency VARCHAR(10) DEFAULT 'ARS'
);

-- ==========================================
-- ADMIN INICIAL
-- Contraseña por defecto: admin
-- Cambiala desde el panel en /admin/users
-- ==========================================
INSERT INTO crm_users (username, display_name, password_hash, is_admin, is_active)
VALUES (
    'admin',
    'Administrador',
    'scrypt:32768:8:1$M0LKNtMlGBOEpxOn$4c16c86a951505402d90d8914433b28fb64299e19b92b9468dfdd54cafb2f6a0499b5a897614a0c91606482f3cfb373cfeb21d52bc8105ca7069ea0935a815af',
    true,
    true
)
ON CONFLICT (username) DO NOTHING;

-- ==========================================
-- PERMISOS PUBLICOS (para cualquier usuario)
-- ==========================================

-- Permisos para TODOS los usuarios en tablas y secuencias existentes
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO PUBLIC;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO PUBLIC;

-- Permisos automáticos para futuras tablas/secuencias
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO PUBLIC;

-- ==========================================
-- FIN DEL SCRIPT
-- ==========================================

