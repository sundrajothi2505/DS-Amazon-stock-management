import os
import sqlite3

from flask import g
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Locally this defaults to a file right next to the app (unchanged behaviour).
# When hosted, set the DB_PATH environment variable to a path on a persistent
# disk (e.g. /var/data/stock.db) so the database survives redeploys/restarts.
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "stock.db"))
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

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

# Simplified from Amazon's full carrier-tracking status list to the
# statuses that actually matter for day-to-day order tracking.
ORDER_STATUS_LABELS = {
    "pending": "Pending",
    "shipped": "Shipped",
    "delivered": "Delivered",
    "returned": "Returned",
    "damaged": "Damaged in transit",
    "lost": "Lost in transit",
    "cancelled": "Cancelled",
}


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 8000")
    return conn


def get_db():
    """One connection per request, reused across calls, closed automatically
    by close_db() (registered via app.teardown_appcontext). This is the
    standard Flask + sqlite3 pattern and it's what guarantees a connection
    is never left open (and holding a lock) if a request errors out."""
    if "db" not in g:
        g.db = _connect()
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _migrate(conn):
    """Additive, safe-to-run-every-time schema upgrades for databases created
    by an earlier version of the app. Only adds what's missing."""
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
        conn.commit()
    except sqlite3.IntegrityError:
        # Pre-existing duplicate order numbers from before this was enforced —
        # leave as-is rather than crashing startup; new ones are still blocked.
        pass


def init_db():
    """Create tables if needed, enable WAL mode, run migrations, and seed a
    default admin login on first run. Runs at import time, before any request
    context exists, so it uses its own plain connection rather than get_db()."""
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    is_new = not os.path.exists(DB_PATH)
    conn = _connect()
    conn.execute("PRAGMA journal_mode = WAL")  # persists in the db file itself
    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())
    conn.commit()
    _migrate(conn)

    user_count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    if user_count == 0:
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
    return is_new


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
    query += " GROUP BY p.id ORDER BY p.name COLLATE NOCASE ASC"
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
