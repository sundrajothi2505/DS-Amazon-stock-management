import os
import sqlite3
import psycopg2
from urllib.parse import urlparse

def get_db_connection():
    # If Render has a DATABASE_URL, use Supabase (PostgreSQL)
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
        # Fallback to local SQLite if running locally on your PC
        conn = sqlite3.connect('stock.db')
        conn.row_factory = sqlite3.Row
        return conn

# Create an alias so files looking for 'get_db' don't crash
get_db = get_db_connection

def close_db(e=None):
    # Placeholder to prevent import crashes if called elsewhere
    pass

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # PostgreSQL Schema
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
        # SQLite Schema
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
