-- Stock Manager database schema
-- current_stock is never stored directly — it is always calculated from
-- initial_stock + every movement logged against a product. That is what
-- keeps the audit trail honest: the only way stock changes is through a
-- logged, attributed movement.

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin','staff')) DEFAULT 'staff',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    asin TEXT,
    category TEXT,
    initial_stock INTEGER NOT NULL DEFAULT 0,
    reorder_level INTEGER NOT NULL DEFAULT 5,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK(type IN ('received','shipped','returned','damaged','adjustment_in','adjustment_out')),
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    reference TEXT,
    notes TEXT,
    -- user_id can go NULL if that login is later removed, but user_name_snapshot
    -- keeps a permanent record of who actually logged the entry either way.
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    user_name_snapshot TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_movements_product ON movements(product_id);
CREATE INDEX IF NOT EXISTS idx_movements_created ON movements(created_at);
CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku);

-- Daily order log: a reference record per Amazon order, separate from
-- movements. This does NOT change stock by itself — it's for tracking
-- order status day to day. Use Log Movement (or the shortcut link on each
-- order row) to actually record the stock effect when you're ready to.
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_date TEXT NOT NULL,
    order_number TEXT NOT NULL,
    product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
    -- Free-text product description as typed/imported (e.g. from an Excel
    -- sheet where it doesn't cleanly match a specific catalog SKU). Shown
    -- whenever product_id isn't linked to a specific product.
    product_description TEXT,
    quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity > 0),
    status TEXT NOT NULL CHECK(status IN
        ('pending','shipped','delivered','returned','damaged','lost','cancelled')),
    shipped_date TEXT,
    notes TEXT,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    user_name_snapshot TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(order_date);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
