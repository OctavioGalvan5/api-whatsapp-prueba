-- ==========================================
-- Migración: Sistema de Órdenes + Catálogo
-- Ejecutar sobre la base de datos existente
-- ==========================================

-- ==========================================
-- CATALOG PRODUCTS
-- ==========================================
CREATE TABLE IF NOT EXISTS catalog_products (
    retailer_id VARCHAR(100) PRIMARY KEY,
    wa_product_id VARCHAR(100),
    name VARCHAR(255),
    description TEXT,
    price NUMERIC(12, 2),
    currency VARCHAR(10),
    availability VARCHAR(20) DEFAULT 'in_stock',
    image_url TEXT,
    synced_at TIMESTAMP
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
    terminated_by_id INTEGER REFERENCES crm_users(id) ON DELETE SET NULL
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

CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);

-- ==========================================
-- Permisos para las nuevas tablas
-- ==========================================
GRANT ALL PRIVILEGES ON TABLE catalog_products TO PUBLIC;
GRANT ALL PRIVILEGES ON TABLE orders TO PUBLIC;
GRANT ALL PRIVILEGES ON TABLE order_items TO PUBLIC;
GRANT ALL PRIVILEGES ON SEQUENCE orders_id_seq TO PUBLIC;
GRANT ALL PRIVILEGES ON SEQUENCE order_items_id_seq TO PUBLIC;

-- ==========================================
-- FIN
-- ==========================================
