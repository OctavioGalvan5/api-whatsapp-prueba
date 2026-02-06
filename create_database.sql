-- ==========================================
-- Script de creación de base de datos
-- WhatsApp CRM + Chatbot RAG
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
    keywords JSON,
    color VARCHAR(20) DEFAULT 'blue',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- CONVERSATION SESSIONS
-- ==========================================
CREATE TABLE IF NOT EXISTS conversation_sessions (
    id SERIAL PRIMARY KEY,
    phone_number VARCHAR(50) NOT NULL,
    topic_id INTEGER REFERENCES conversation_topics(id) ON DELETE SET NULL,
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP NOT NULL,
    message_count INTEGER DEFAULT 0,
    summary TEXT,
    rating VARCHAR(50),
    auto_categorized BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sessions_phone_started ON conversation_sessions(phone_number, started_at);

-- ==========================================
-- DOCUMENT METADATA (para RAG)
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
    embedding vector(1536)
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
    embedding vector(1536),
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
    status VARCHAR(50) DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- WHATSAPP TAGS
-- ==========================================
CREATE TABLE IF NOT EXISTS whatsapp_tags (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    color VARCHAR(20) DEFAULT 'green',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- WHATSAPP CONTACTS
-- ==========================================
CREATE TABLE IF NOT EXISTS whatsapp_contacts (
    id SERIAL PRIMARY KEY,
    contact_id VARCHAR(100),
    phone_number VARCHAR(50) NOT NULL,
    name VARCHAR(255),
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
    tags JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_contacts_phone ON whatsapp_contacts(phone_number);
CREATE INDEX IF NOT EXISTS idx_contacts_contact_id ON whatsapp_contacts(contact_id);

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
    phone_number VARCHAR(50) NOT NULL,
    direction VARCHAR(20) NOT NULL,
    message_type VARCHAR(50) NOT NULL,
    content TEXT,
    media_id VARCHAR(255),
    media_url VARCHAR(500),
    caption TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_messages_phone_ts ON whatsapp_messages(phone_number, timestamp);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON whatsapp_messages(timestamp);

-- ==========================================
-- WHATSAPP MESSAGE STATUSES
-- ==========================================
CREATE TABLE IF NOT EXISTS whatsapp_message_statuses (
    id SERIAL PRIMARY KEY,
    wa_message_id VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    error_code VARCHAR(50),
    error_title VARCHAR(200),
    error_details TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_statuses_wa_id ON whatsapp_message_statuses(wa_message_id);

-- ==========================================
-- WHATSAPP CAMPAIGNS
-- ==========================================
CREATE TABLE IF NOT EXISTS whatsapp_campaigns (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    template_name VARCHAR(200) NOT NULL,
    template_language VARCHAR(20) DEFAULT 'es_AR',
    tag_id INTEGER NOT NULL REFERENCES whatsapp_tags(id),
    status VARCHAR(50) DEFAULT 'draft',
    variables JSON,
    scheduled_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- WHATSAPP CAMPAIGN LOGS
-- ==========================================
CREATE TABLE IF NOT EXISTS whatsapp_campaign_logs (
    id SERIAL PRIMARY KEY,
    campaign_id INTEGER NOT NULL REFERENCES whatsapp_campaigns(id) ON DELETE CASCADE,
    contact_id INTEGER REFERENCES whatsapp_contacts(id),
    contact_phone VARCHAR(50) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    message_id VARCHAR(100),
    error_detail TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(campaign_id, contact_id)
);

CREATE INDEX IF NOT EXISTS idx_campaign_logs_campaign_contact ON whatsapp_campaign_logs(campaign_id, contact_id);

-- ==========================================
-- FIN DEL SCRIPT
-- ==========================================
