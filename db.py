import os
import sqlite3

from flask import g
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "stock.db"))
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")
SCHEMA_PG_PATH = os.path.join(BASE_DIR, "schema_postgres.sql")

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
IS_POSTGRES = bool(DATABASE_URL)

if IS_POSTGRES:
    import psycopg2
    import psycopg2.extras

# Movement types that add to stock vs. take away from it.
STOCK_IN_TYPES = ("received", "returned", "adjustment_in")
STOCK_OUT_TYPES = ("shipped", "damaged", "adjustment_out")

TYPE_LABELS = {
    "received": "Received from supplier",
    "shipped": "Shipped (sold)",
    "returned": "Customer return",
    "damaged": "Damaged / written off",
    "adjustment_in": "Manual adjustment (+)",
    "adjustment_out": "Manual adjustment (-)",
}

ORDER_STATUS_LABELS = {
    "pending": "Pending",
    "shipped": "Shipped",
    "delivered": "Delivered",
    "returned": "Returned",
    "damaged": "Damaged in transit",
    "lost": "Lost in transit",
    "cancelled": "Cancelled",
}


# ---------------------------------------------------------------------------
# A thin shim so the rest of the app can always write conn.execute(sql, params)
# .fetchone() / .fetchall(), exactly like sqlite3 already allows, regardless
# of which database is actually behind it. Only this file needs to know the
# difference between SQLite and Postgres.
# ---------------------------------------------------------------------------

class _PGResult:
    def __init__(self, cursor):
        self._cursor = cursor

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def rowcount(self):
        return self._cursor.rowcount


class PGConnection:
    """Adapts a psycopg2 connection to sqlite3.Connection's convenient
    conn.execute(...).fetchone() style. Rows come back as dict-like
    RealDictRow objects, so both row["col"] (Python) and row.col (Jinja,
    which falls back to item access) keep working unchanged."""

    def __init__(self, pg_conn):
        self._conn = pg_conn

    def execute(self, query, params=()):
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Our SQL is written with sqlite-style "?" placeholders throughout;
        # translate to psycopg2's "%s" here so every query above this layer
        # can stay identical between both database backends.
        cur.execute(query.replace("?", "%s"), params)
        return _PGResult(cur)

    def executemany(self, query, seq_of_params):
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.executemany(query.replace("?", "%s"), seq_of_params)
        return _PGResult(cur)

    def executescript(self, script):
        cur = self._conn.cursor()
        cur.execute(script)
        cur.close()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def _connect_sqlite():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 8000")
    return conn


def _connect_postgres():
    raw = psycopg2.connect(DATABASE_URL, sslmode="require")
    raw.autocommit = False
    return PGConnection(raw)


def get_db():
    """One connection per request, reused across calls, closed automatically
    by close_db() (registered via app.teardown_appcontext). This is the
    standard Flask pattern and it's what guarantees a connection is never
    left open (and holding a lock, in SQLite's case) if a request errors out."""
    if "db" not in g:
        g.db = _connect_postgres() if IS_POSTGRES else _connect_sqlite()
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _migrate_sqlite(conn):
    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(orders)")}
    if "product_description" not in existing_cols:
        conn.execute("ALTER TABLE orders ADD COLUMN product_description TEXT")
    if "shipped_date" not in existing_cols:
        conn.execute("ALTER TABLE orders ADD COLUMN shipped_date TEXT")
    conn.commit()
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_order_number ON orders(order_number)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_movements_product_type ON movements(product_id, type)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_movements_created_id ON movements(created_at, id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_orders_status_date ON orders(status, order_date, id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_orders_date_id ON orders(order_date, id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_products_name_lower ON products(name COLLATE NOCASE)"
        )
        conn.commit()
    except sqlite3.IntegrityError:
        # Pre-existing duplicate order numbers from before this was enforced —
        # leave as-is rather than crashing startup; new ones are still blocked.
        pass


def _migrate_postgres(conn):
    cur = conn._conn.cursor()
    cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS product_description TEXT")
    cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS shipped_date TEXT")
    conn.commit()
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_order_number ON orders(order_number)"
    )
    # Indexes used by the high-traffic list/filter pages and stock calculation.
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_movements_product_type ON movements(product_id, type)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_movements_created_id ON movements(created_at, id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_orders_status_date ON orders(status, order_date, id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_orders_date_id ON orders(order_date, id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_products_name_lower ON products(LOWER(name))"
    )
    conn.commit()
    cur.close()


def init_db():
    """Create tables if needed, run migrations, and seed a default admin
    login on first run. Runs at import time, before any request context
    exists, so it uses its own plain connection rather than get_db()."""
    if IS_POSTGRES:
        conn = _connect_postgres()
        with open(SCHEMA_PG_PATH, "r") as f:
            conn.executescript(f.read())
        conn.commit()
        _migrate_postgres(conn)
        seed_needed = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 0
    else:
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        conn = _connect_sqlite()
        conn.execute("PRAGMA journal_mode = WAL")  # persists in the db file itself
        with open(SCHEMA_PATH, "r") as f:
            conn.executescript(f.read())
        conn.commit()
        _migrate_sqlite(conn)
        seed_needed = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 0

    if seed_needed:
        conn.execute(
            "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
            ("admin", generate_password_hash("admin123"), "Administrator", "admin"),
        )
        conn.commit()
        print("=" * 64)
        print(" First run — a default admin login was created:")
        print("   Username: admin")
        print("   Password: admin123")
        print(" Log in and change this password right away (top left, ")
        print(" 'Change password'), then add a login for each employee.")
        print("=" * 64)
    conn.close()


def fetch_products(conn, search=None, sku=None):
    """Return products with current_stock computed from initial_stock + movements."""
    query = """
        SELECT p.*,
            p.initial_stock
            + COALESCE(SUM(CASE WHEN m.type IN ('received','returned','adjustment_in')
                                 THEN m.quantity ELSE 0 END), 0)
            - COALESCE(SUM(CASE WHEN m.type IN ('shipped','damaged','adjustment_out')
                                 THEN m.quantity ELSE 0 END), 0)
            AS current_stock
        FROM products p
        LEFT JOIN movements m ON m.product_id = p.id
    """
    clauses = []
    params = []
    if search:
        clauses.append("(p.sku LIKE ? OR p.name LIKE ? OR p.asin LIKE ? OR p.category LIKE ?)")
        like = f"%{search}%"
        params += [like, like, like, like]
    if sku:
        clauses.append("p.sku = ?")
        params.append(sku)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " GROUP BY p.id ORDER BY LOWER(p.name) ASC"
    return conn.execute(query, params).fetchall()


def fetch_product(conn, pid):
    rows = conn.execute(
        """
        SELECT p.*,
            p.initial_stock
            + COALESCE(SUM(CASE WHEN m.type IN ('received','returned','adjustment_in')
                                 THEN m.quantity ELSE 0 END), 0)
            - COALESCE(SUM(CASE WHEN m.type IN ('shipped','damaged','adjustment_out')
                                 THEN m.quantity ELSE 0 END), 0)
            AS current_stock
        FROM products p
        LEFT JOIN movements m ON m.product_id = p.id
        WHERE p.id = ?
        GROUP BY p.id
        """,
        (pid,),
    ).fetchall()
    return rows[0] if rows else None
