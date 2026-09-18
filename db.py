import os
import sqlite3
import psycopg2
from urllib.parse import urlparse

# Global labels required by app.py
TYPE_LABELS = {
    'INCOMING': 'Incoming / Procurement',
    'OUTGOING': 'Outgoing / Dispatch',
    'ADJUSTMENT': 'Inventory Adjustment',
    'RETURN': 'Customer Return'
}

ORDER_STATUS_LABELS = {
    'PENDING': 'Pending Verification',
    'APPROVED': 'Approved & Staged',
    'COMPLETED': 'Completed & Dispatched',
    'CANCELLED': 'Cancelled'
}

def get_db_connection():
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        result = urlparse(database_url)
        username = result.username
        password = result.password
        database = result.path[1:]
        hostname = result.hostname
        port = result.port
        
        conn = psycopg2.connect(
            database=database,
            user=username,
            password=password,
            host=hostname,
            port=port
        )
        return conn
    else:
        conn = sqlite3.connect('stock.db')
        conn.row_factory = sqlite3.Row
        return conn

# Naming compatibility aliases
get_db = get_db_connection

def close_db(e=None):
    pass

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                asin TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                status TEXT NOT NULL
            )
        ''')
    else:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asin TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                status TEXT NOT NULL
            )
        ''')
        
    conn.commit()
    cursor.close()
    conn.close()

def fetch_products():
    conn = get_db_connection()
    cursor = conn.cursor()
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        cursor.execute("SELECT id, asin, name, quantity, price, status FROM products ORDER BY name ASC")
        rows = cursor.fetchall()
        # Convert tuple list to list of dicts to mimic sqlite Row behavior
        products = [{"id": r[0], "asin": r[1], "name": r[2], "quantity": r[3], "price": r[4], "status": r[5]} for r in rows]
    else:
        cursor.execute("SELECT * FROM products ORDER BY name ASC")
        products = cursor.fetchall()
        
    cursor.close()
    conn.close()
    return products

def fetch_product(product_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        cursor.execute("SELECT id, asin, name, quantity, price, status FROM products WHERE id = %s", (product_id,))
        row = cursor.fetchone()
        product = {"id": row[0], "asin": row[1], "name": row[2], "quantity": row[3], "price": row[4], "status": row[5]} if row else None
    else:
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        product = cursor.fetchone()
        
    cursor.close()
    conn.close()
    return product
