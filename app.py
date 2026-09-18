import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_db, init_db, TYPE_LABELS, ORDER_STATUS_LABELS, fetch_products, fetch_product

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'fallback-dev-key-123')

# Ensure database tables are created at startup
with app.app_context():
    init_db()
    
    # Auto-create default admin on fresh database if it doesn't exist
    conn = get_db()
    cursor = conn.cursor()
    database_url = os.environ.get('DATABASE_URL')
    
    try:
        if database_url:
            cursor.execute("SELECT * FROM users WHERE username = %s", ('admin',))
        else:
            cursor.execute("SELECT * FROM users WHERE username = ?", ('admin',))
            
        if not cursor.fetchone():
            hashed_pw = generate_password_hash('admin123')
            if database_url:
                cursor.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)", ('admin', hashed_pw, 'ADMIN'))
            else:
                cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", ('admin', hashed_pw, 'ADMIN'))
            conn.commit()
    except Exception as e:
        print(f"Startup user init check event: {e}")
    finally:
        cursor.close()
        conn.close()

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    products = fetch_products()
    return render_template('index.html', products=products)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db()
        cursor = conn.cursor()
        database_url = os.environ.get('DATABASE_URL')
        
        if database_url:
            cursor.execute("SELECT id, username, password, role FROM users WHERE username = %s", (username,))
            row = cursor.fetchone()
            user = {"id": row[0], "username": row[1], "password": row[2], "role": row[3]} if row else None
        else:
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            user = dict(row) if row else None
            
        cursor.close()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            return redirect(url_for('index'))
        
        flash('Invalid username or password', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/change-password', methods=['GET', 'POST'])
def change_password():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        old_password = request.form['old_password']
        new_password = request.form['new_password']
        
        conn = get_db()
        cursor = conn.cursor()
        database_url = os.environ.get('DATABASE_URL')
        
        if database_url:
            cursor.execute("SELECT password FROM users WHERE id = %s", (session['user_id'],))
            row = cursor.fetchone()
            current_pw = row[0] if row else None
        else:
            cursor.execute("SELECT password FROM users WHERE id = ?", (session['user_id'],))
            row = cursor.fetchone()
            current_pw = row['password'] if row else None
            
        if current_pw and check_password_hash(current_pw, old_password):
            hashed_new = generate_password_hash(new_password)
            if database_url:
                cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_new, session['user_id']))
            else:
                cursor.execute("UPDATE users SET password = ? WHERE id = ?", (hashed_new, session['user_id']))
            conn.commit()
            flash('Password updated successfully!', 'success')
            cursor.close()
            conn.close()
            return redirect(url_for('index'))
            
        flash('Incorrect current password', 'danger')
        cursor.close()
        conn.close()
        
    return render_template('change_password.html')

if __name__ == '__main__':
    app.run(debug=True)
