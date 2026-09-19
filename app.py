import csv
import io
import os
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, Response
)
from werkzeug.security import generate_password_hash, check_password_hash

from db import (get_db, close_db, init_db, fetch_products, fetch_product,
                TYPE_LABELS, ORDER_STATUS_LABELS, IS_POSTGRES)
from importer import parse_report, parse_orders_workbook

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "stock-manager-local-secret-key")
app.teardown_appcontext(close_db)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", next=request.path))
        if session.get("role") != "admin":
            flash("That page is only available to admins.", "error")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return wrapper


@app.context_processor
def inject_globals():
    current_user = None
    if "user_id" in session:
        current_user = {
            "id": session.get("user_id"),
            "full_name": session.get("full_name"),
            "role": session.get("role"),
            "username": session.get("username"),
        }
    return dict(current_user=current_user, type_labels=TYPE_LABELS,
                order_status_labels=ORDER_STATUS_LABELS)


@app.context_processor
def inject_asset_helper():
    def asset_url(filename):
        """Static file URL with a cache-busting version based on the file's
        own last-modified time, so browsers always fetch a fresh copy after
        style.css or script.js changes, instead of serving a stale cached
        version."""
        try:
            mtime = int(os.path.getmtime(os.path.join(app.static_folder, filename)))
        except OSError:
            mtime = 0
        return url_for("static", filename=filename) + f"?v={mtime}"
    return dict(asset_url=asset_url)


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["full_name"] = user["full_name"]
            session["role"] = user["role"]
            flash(f"Welcome back, {user['full_name']}.", "success")
            next_url = request.args.get("next") or url_for("dashboard")
            return redirect(next_url)
        flash("Incorrect username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("login"))


@app.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        if not check_password_hash(user["password_hash"], current):
            flash("Current password is incorrect.", "error")
        elif len(new) < 6:
            flash("New password should be at least 6 characters.", "error")
        elif new != confirm:
            flash("New passwords don't match.", "error")
        else:
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                         (generate_password_hash(new), user["id"]))
            conn.commit()
            flash("Password changed.", "success")
            return redirect(url_for("dashboard"))
    return render_template("change_password.html")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route("/")
@login_required
def dashboard():
    conn = get_db()
    products = fetch_products(conn)
    total_products = len(products)
    total_units = sum(max(p["current_stock"], 0) for p in products)
    low_stock = sorted(
        [p for p in products if 0 < p["current_stock"] <= p["reorder_level"]],
        key=lambda p: p["current_stock"],
    )
    out_of_stock = sorted(
        [p for p in products if p["current_stock"] <= 0],
        key=lambda p: p["current_stock"],
    )
    recent = conn.execute(
        """
        SELECT m.*, p.name AS product_name, p.sku
        FROM movements m
        JOIN products p ON p.id = m.product_id
        ORDER BY m.created_at DESC, m.id DESC
        LIMIT 15
        """
    ).fetchall()
    return render_template(
        "dashboard.html",
        total_products=total_products,
        total_units=total_units,
        low_stock=low_stock,
        out_of_stock=out_of_stock,
        needs_attention=out_of_stock + low_stock,
        recent=recent,
    )


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

@app.route("/products")
@login_required
def products():
    search = request.args.get("q", "").strip()
    stock_filter = request.args.get("stock", "").strip()  # '', 'in', 'low', 'out'
    conn = get_db()
    all_rows = fetch_products(conn, search=search or None)
    counts = {
        "all": len(all_rows),
        "in": len([p for p in all_rows if p["current_stock"] > p["reorder_level"]]),
        "low": len([p for p in all_rows if 0 < p["current_stock"] <= p["reorder_level"]]),
        "out": len([p for p in all_rows if p["current_stock"] <= 0]),
    }
    if stock_filter == "out":
        rows = [p for p in all_rows if p["current_stock"] <= 0]
    elif stock_filter == "low":
        rows = [p for p in all_rows if 0 < p["current_stock"] <= p["reorder_level"]]
    elif stock_filter == "in":
        rows = [p for p in all_rows if p["current_stock"] > p["reorder_level"]]
    else:
        stock_filter = ""
        rows = all_rows
    return render_template(
        "products.html", products=rows, search=search,
        stock_filter=stock_filter, counts=counts
    )


@app.route("/products/new", methods=["GET", "POST"])
@login_required
def product_new():
    if request.method == "POST":
        sku = request.form.get("sku", "").strip()
        name = request.form.get("name", "").strip()
        asin = request.form.get("asin", "").strip()
        category = request.form.get("category", "").strip()
        notes = request.form.get("notes", "").strip()
        initial_stock_raw = request.form.get("initial_stock", "0").strip()
        reorder_level_raw = request.form.get("reorder_level", "5").strip()

        errors = []
        if not sku:
            errors.append("SKU is required.")
        if not name:
            errors.append("Product name is required.")
        try:
            initial_stock = int(initial_stock_raw)
            if initial_stock < 0:
                errors.append("Starting stock can't be negative.")
        except ValueError:
            errors.append("Starting stock must be a whole number.")
            initial_stock = 0
        try:
            reorder_level = int(reorder_level_raw)
            if reorder_level < 0:
                errors.append("Reorder level can't be negative.")
        except ValueError:
            errors.append("Reorder level must be a whole number.")
            reorder_level = 5

        conn = get_db()
        if sku and not errors:
            if conn.execute("SELECT id FROM products WHERE sku = ?", (sku,)).fetchone():
                errors.append(f"SKU '{sku}' already exists.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("product_form.html", product=request.form, mode="new")

        conn.execute(
            """INSERT INTO products (sku, name, asin, category, initial_stock, reorder_level, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (sku, name, asin, category, initial_stock, reorder_level, notes),
        )
        conn.commit()
        flash(f"Added {name} to the catalog.", "success")
        return redirect(url_for("products"))

    return render_template("product_form.html", product=None, mode="new")


@app.route("/products/import", methods=["GET", "POST"])
@login_required
def product_import():
    if request.method == "POST":
        file = request.files.get("report_file")
        if not file or not file.filename:
            flash("Choose a file to upload first.", "error")
            return redirect(url_for("product_import"))

        rows, error = parse_report(file.read())
        if error:
            flash(error, "error")
            return redirect(url_for("product_import"))
        if not rows:
            flash("No product rows were found in that file.", "error")
            return redirect(url_for("product_import"))

        conn = get_db()
        today = datetime.now().strftime("%Y-%m-%d")
        added, updated, adjusted, unchanged = [], [], [], []

        for row in rows:
            existing = conn.execute(
                "SELECT * FROM products WHERE sku = ?", (row["sku"],)
            ).fetchone()

            if existing is None:
                conn.execute(
                    """INSERT INTO products (sku, name, asin, category, initial_stock, reorder_level, notes)
                       VALUES (?, ?, ?, '', ?, 5, ?)""",
                    (row["sku"], row["name"] or row["sku"], row["asin"],
                     row["quantity"] or 0, f"Imported from report on {today}."),
                )
                added.append(row["sku"])
                continue

            new_name = row["name"] or existing["name"]
            new_asin = row["asin"] or existing["asin"]
            details_changed = new_name != existing["name"] or new_asin != existing["asin"]
            if details_changed:
                conn.execute(
                    "UPDATE products SET name=?, asin=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (new_name, new_asin, existing["id"]),
                )
                updated.append(row["sku"])

            stock_changed = False
            if row["quantity"] is not None:
                current_stock = fetch_product(conn, existing["id"])["current_stock"]
                diff = row["quantity"] - current_stock
                if diff != 0:
                    mtype = "adjustment_in" if diff > 0 else "adjustment_out"
                    conn.execute(
                        """INSERT INTO movements
                           (product_id, type, quantity, reference, notes, user_id, user_name_snapshot)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (existing["id"], mtype, abs(diff), f"Import {today}",
                         "Synced to match uploaded report",
                         session["user_id"], session["full_name"]),
                    )
                    stock_changed = True
                    adjusted.append(row["sku"])

            if not details_changed and not stock_changed:
                unchanged.append(row["sku"])

        conn.commit()
        return render_template(
            "product_import_result.html",
            added=added, updated=updated, adjusted=adjusted,
            unchanged=unchanged, total=len(rows),
        )

    return render_template("product_import.html")


@app.route("/products/<int:pid>/edit", methods=["GET", "POST"])
@login_required
def product_edit(pid):
    conn = get_db()
    product = fetch_product(conn, pid)
    if not product:
        flash("Product not found.", "error")
        return redirect(url_for("products"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        asin = request.form.get("asin", "").strip()
        category = request.form.get("category", "").strip()
        notes = request.form.get("notes", "").strip()
        reorder_level_raw = request.form.get("reorder_level", "5").strip()

        errors = []
        if not name:
            errors.append("Product name is required.")
        try:
            reorder_level = int(reorder_level_raw)
            if reorder_level < 0:
                errors.append("Reorder level can't be negative.")
        except ValueError:
            errors.append("Reorder level must be a whole number.")
            reorder_level = product["reorder_level"]

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("product_form.html", product=product, mode="edit")

        conn.execute(
            """UPDATE products SET name=?, asin=?, category=?, reorder_level=?, notes=?,
               updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (name, asin, category, reorder_level, notes, pid),
        )
        conn.commit()
        flash("Product updated.", "success")
        return redirect(url_for("products"))

    return render_template("product_form.html", product=product, mode="edit")


@app.route("/products/<int:pid>/delete", methods=["POST"])
@admin_required
def product_delete(pid):
    conn = get_db()
    product = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    if product:
        conn.execute("DELETE FROM products WHERE id = ?", (pid,))
        conn.commit()
        flash(f"Deleted {product['name']} and its movement history.", "success")
    return redirect(url_for("products"))


# ---------------------------------------------------------------------------
# Movements (the audit trail)
# ---------------------------------------------------------------------------

@app.route("/movements")
@login_required
def movements():
    conn = get_db()
    product_list = fetch_products(conn)
    products_js = products_for_js(product_list)

    query = """
        SELECT m.*, p.name AS product_name, p.sku
        FROM movements m
        JOIN products p ON p.id = m.product_id
        WHERE 1=1
    """
    params = []
    product_id = request.args.get("product_id", "").strip()
    mtype = request.args.get("type", "").strip()
    date_from = request.args.get("from", "").strip()
    date_to = request.args.get("to", "").strip()

    if product_id:
        query += " AND m.product_id = ?"
        params.append(product_id)
    if mtype:
        query += " AND m.type = ?"
        params.append(mtype)
    if date_from:
        query += " AND substr(m.created_at, 1, 10) >= ?"
        params.append(date_from)
    if date_to:
        query += " AND substr(m.created_at, 1, 10) <= ?"
        params.append(date_to)

    query += " ORDER BY m.created_at DESC, m.id DESC LIMIT 500"
    rows = conn.execute(query, params).fetchall()
    return render_template(
        "movements.html",
        movements=rows,
        products=product_list,
        products_js=products_js,
        filters=request.args,
    )


def products_for_js(product_list):
    """Compact product data for the searchable-select widget in forms."""
    return [
        {"id": p["id"], "sku": p["sku"], "name": p["name"], "stock": p["current_stock"]}
        for p in product_list
    ]


@app.route("/movements/new", methods=["GET", "POST"])
@login_required
def movement_new():
    conn = get_db()
    product_list = fetch_products(conn)
    products_js = products_for_js(product_list)

    if request.method == "POST":
        product_id = request.form.get("product_id", "")
        mtype = request.form.get("type", "")
        quantity_raw = request.form.get("quantity", "").strip()
        reference = request.form.get("reference", "").strip()
        notes = request.form.get("notes", "").strip()
        log_another = request.form.get("log_another")

        errors = []
        if not product_id:
            errors.append("Choose a product.")
        if mtype not in TYPE_LABELS:
            errors.append("Choose a movement type.")
        try:
            quantity = int(quantity_raw)
            if quantity <= 0:
                errors.append("Quantity must be greater than zero.")
        except ValueError:
            errors.append("Quantity must be a whole number.")
            quantity = 0

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "movement_form.html", products=product_list, products_js=products_js,
                form=request.form
            )

        conn.execute(
            """INSERT INTO movements (product_id, type, quantity, reference, notes, user_id, user_name_snapshot)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (product_id, mtype, quantity, reference, notes,
             session["user_id"], session["full_name"]),
        )
        conn.commit()
        product = conn.execute("SELECT name FROM products WHERE id = ?", (product_id,)).fetchone()
        flash(f"Logged {TYPE_LABELS[mtype].lower()} for {product['name']}.", "success")
        if log_another:
            return redirect(url_for("movement_new", product_id=product_id))
        return redirect(url_for("dashboard"))

    preselect = request.args.get("product_id", "")
    return render_template(
        "movement_form.html", products=product_list, products_js=products_js,
        form=None, preselect=preselect
    )



@app.route("/movements/<int:mid>/delete", methods=["POST"])
@admin_required
def movement_delete(mid):
    conn = get_db()
    conn.execute("DELETE FROM movements WHERE id = ?", (mid,))
    conn.commit()
    flash("Entry removed — stock recalculated automatically.", "success")
    return redirect(url_for("movements"))


# ---------------------------------------------------------------------------
# Daily orders (a reference log, separate from stock movements)
# ---------------------------------------------------------------------------

@app.route("/orders")
@login_required
def orders():
    conn = get_db()
    product_list = conn.execute(
        "SELECT id, sku, name FROM products ORDER BY LOWER(name)"
    ).fetchall()

    query = """
        SELECT o.*, COALESCE(p.name, o.product_description) AS product_name,
               p.sku, p.asin
        FROM orders o
        LEFT JOIN products p ON p.id = o.product_id
        WHERE 1=1
    """
    params = []
    status = request.args.get("status", "").strip()
    date_from = request.args.get("from", "").strip()
    date_to = request.args.get("to", "").strip()

    if status:
        query += " AND o.status = ?"
        params.append(status)
    if date_from:
        query += " AND substr(o.order_date, 1, 10) >= ?"
        params.append(date_from)
    if date_to:
        query += " AND substr(o.order_date, 1, 10) <= ?"
        params.append(date_to)

    query += " ORDER BY o.order_date DESC, o.id DESC LIMIT 500"
    rows = conn.execute(query, params).fetchall()
    return render_template(
        "orders.html", orders=rows, products=product_list, filters=request.args
    )


@app.route("/orders/new", methods=["GET", "POST"])
@login_required
def order_new():
    conn = get_db()
    product_list = fetch_products(conn)
    products_js = products_for_js(product_list)

    if request.method == "POST":
        order_date = request.form.get("order_date", "").strip()
        order_number = request.form.get("order_number", "").strip()
        product_id = request.form.get("product_id", "") or None
        product_description = request.form.get("product_description", "").strip()
        quantity_raw = request.form.get("quantity", "1").strip()
        status = request.form.get("status", "")
        notes = request.form.get("notes", "").strip()
        add_another = request.form.get("add_another")

        errors = []
        if not order_date:
            errors.append("Order date is required.")
        if not order_number:
            errors.append("Order number is required.")
        if not product_id and not product_description:
            errors.append("Choose a product, or type a description if it's not in your catalog.")
        if status not in ORDER_STATUS_LABELS:
            errors.append("Choose a valid status.")
        try:
            quantity = int(quantity_raw)
            if quantity <= 0:
                errors.append("Quantity must be greater than zero.")
        except ValueError:
            errors.append("Quantity must be a whole number.")
            quantity = 1
        if order_number and not errors:
            if conn.execute("SELECT id FROM orders WHERE order_number = ?", (order_number,)).fetchone():
                errors.append(f"An order numbered '{order_number}' already exists.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "order_form.html", products=product_list, products_js=products_js,
                order=request.form, mode="new"
            )

        conn.execute(
            """INSERT INTO orders
               (order_date, order_number, product_id, product_description, quantity,
                status, notes, user_id, user_name_snapshot)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (order_date, order_number, product_id, product_description or None, quantity,
             status, notes, session["user_id"], session["full_name"]),
        )
        conn.commit()
        flash(f"Logged order {order_number}.", "success")
        if add_another:
            return redirect(url_for("order_new"))
        return redirect(url_for("orders"))

    today = datetime.now().strftime("%Y-%m-%d")
    return render_template(
        "order_form.html", products=product_list, products_js=products_js,
        order=None, mode="new", today=today
    )


@app.route("/orders/<int:oid>/edit", methods=["GET", "POST"])
@login_required
def order_edit(oid):
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (oid,)).fetchone()
    if not order:
        flash("Order not found.", "error")
        return redirect(url_for("orders"))
    product_list = fetch_products(conn)
    products_js = products_for_js(product_list)

    if request.method == "POST":
        order_date = request.form.get("order_date", "").strip()
        order_number = request.form.get("order_number", "").strip()
        product_id = request.form.get("product_id", "") or None
        product_description = request.form.get("product_description", "").strip()
        quantity_raw = request.form.get("quantity", "1").strip()
        status = request.form.get("status", "")
        notes = request.form.get("notes", "").strip()

        errors = []
        if not order_date:
            errors.append("Order date is required.")
        if not order_number:
            errors.append("Order number is required.")
        if not product_id and not product_description:
            errors.append("Choose a product, or type a description if it's not in your catalog.")
        if status not in ORDER_STATUS_LABELS:
            errors.append("Choose a valid status.")
        try:
            quantity = int(quantity_raw)
            if quantity <= 0:
                errors.append("Quantity must be greater than zero.")
        except ValueError:
            errors.append("Quantity must be a whole number.")
            quantity = order["quantity"]
        if order_number and not errors:
            clash = conn.execute(
                "SELECT id FROM orders WHERE order_number = ? AND id != ?", (order_number, oid)
            ).fetchone()
            if clash:
                errors.append(f"An order numbered '{order_number}' already exists.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "order_form.html", products=product_list, products_js=products_js,
                order=request.form, mode="edit", oid=oid
            )

        conn.execute(
            """UPDATE orders SET order_date=?, order_number=?, product_id=?, product_description=?,
               quantity=?, status=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (order_date, order_number, product_id, product_description or None,
             quantity, status, notes, oid),
        )
        conn.commit()
        flash(f"Updated order {order_number}.", "success")
        return redirect(url_for("orders"))

    return render_template("order_form.html", products=product_list, products_js=products_js,
                            order=order, mode="edit", oid=oid)


@app.route("/orders/<int:oid>/delete", methods=["POST"])
@admin_required
def order_delete(oid):
    conn = get_db()
    conn.execute("DELETE FROM orders WHERE id = ?", (oid,))
    conn.commit()
    flash("Order entry removed.", "success")
    return redirect(url_for("orders"))


@app.route("/orders/import", methods=["GET", "POST"])
@login_required
def order_import():
    if request.method == "POST":
        file = request.files.get("report_file")
        if not file or not file.filename:
            flash("Choose a file to upload first.", "error")
            return redirect(url_for("order_import"))

        rows, sheet_report = parse_orders_workbook(file.read())

        conn = get_db()
        added = 0
        skipped_existing = 0
        insert_sql = (
            """INSERT INTO orders
               (order_date, order_number, product_id, product_description, quantity,
                status, shipped_date, notes, user_id, user_name_snapshot)
               VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (order_number) DO NOTHING"""
            if IS_POSTGRES else
            """INSERT OR IGNORE INTO orders
               (order_date, order_number, product_id, product_description, quantity,
                status, shipped_date, notes, user_id, user_name_snapshot)
               VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)"""
        )
        for row in rows:
            notes_parts = []
            if row["status_note"]:
                notes_parts.append(f"Original status: {row['status_note']}")
            notes_parts.append("Imported from Excel")
            cur = conn.execute(
                insert_sql,
                (row["order_date"], row["order_number"], row["description"], row["quantity"],
                 row["status"], row["shipped_date"], ". ".join(notes_parts),
                 session["user_id"], session["full_name"]),
            )
            if cur.rowcount:
                added += 1
            else:
                skipped_existing += 1
        conn.commit()

        return render_template(
            "order_import_result.html",
            added=added, skipped_existing=skipped_existing,
            sheet_report=sheet_report, total=len(rows),
        )

    return render_template("order_import.html")


# ---------------------------------------------------------------------------
# Employees (admin only)
# ---------------------------------------------------------------------------

@app.route("/users")
@admin_required
def users():
    conn = get_db()
    rows = conn.execute("SELECT * FROM users ORDER BY LOWER(full_name)").fetchall()
    return render_template("users.html", users=rows)


@app.route("/users/new", methods=["GET", "POST"])
@admin_required
def user_new():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "staff")
        if role not in ("admin", "staff"):
            role = "staff"

        errors = []
        if not username:
            errors.append("Username is required.")
        if not full_name:
            errors.append("Full name is required.")
        if len(password) < 6:
            errors.append("Password should be at least 6 characters.")

        conn = get_db()
        if username and not errors:
            if conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
                errors.append("That username is already taken.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("user_form.html", form=request.form)

        conn.execute(
            "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
            (username, generate_password_hash(password), full_name, role),
        )
        conn.commit()
        flash(f"Added a login for {full_name}.", "success")
        return redirect(url_for("users"))

    return render_template("user_form.html", form=None)


@app.route("/users/<int:uid>/delete", methods=["POST"])
@admin_required
def user_delete(uid):
    if uid == session["user_id"]:
        flash("You can't remove your own login while logged in.", "error")
        return redirect(url_for("users"))
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    admins_left = conn.execute("SELECT COUNT(*) c FROM users WHERE role = 'admin'").fetchone()["c"]
    if user and user["role"] == "admin" and admins_left <= 1:
        flash("You can't remove the last admin login.", "error")
        return redirect(url_for("users"))
    if user:
        # Movement history is kept (and stays attributed via user_name_snapshot)
        # even after the login itself is removed.
        conn.execute("DELETE FROM users WHERE id = ?", (uid,))
        conn.commit()
        flash(f"Removed login for {user['full_name']}.", "success")
    return redirect(url_for("users"))


@app.route("/users/<int:uid>/reset-password", methods=["POST"])
@admin_required
def user_reset_password(uid):
    new_password = request.form.get("password", "")
    if len(new_password) < 6:
        flash("Password should be at least 6 characters.", "error")
        return redirect(url_for("users"))
    conn = get_db()
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                 (generate_password_hash(new_password), uid))
    conn.commit()
    flash("Password reset.", "success")
    return redirect(url_for("users"))


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

@app.route("/export/products.csv")
@login_required
def export_products():
    conn = get_db()
    rows = fetch_products(conn)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["SKU", "Name", "ASIN", "Category", "Current Stock", "Reorder Level", "Notes"])
    for r in rows:
        writer.writerow([r["sku"], r["name"], r["asin"] or "", r["category"] or "",
                          r["current_stock"], r["reorder_level"], r["notes"] or ""])
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=stock_export.csv"},
    )


@app.route("/export/movements.csv")
@login_required
def export_movements():
    conn = get_db()
    rows = conn.execute(
        """
        SELECT m.created_at, p.sku, p.name, m.type, m.quantity, m.reference, m.notes, m.user_name_snapshot
        FROM movements m
        JOIN products p ON p.id = m.product_id
        ORDER BY m.created_at DESC
        """
    ).fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "SKU", "Product", "Type", "Quantity", "Reference", "Notes", "Logged By"])
    for r in rows:
        writer.writerow([r["created_at"], r["sku"], r["name"], TYPE_LABELS.get(r["type"], r["type"]),
                          r["quantity"], r["reference"] or "", r["notes"] or "", r["user_name_snapshot"]])
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=movements_export.csv"},
    )


@app.route("/export/orders.csv")
@login_required
def export_orders():
    conn = get_db()
    rows = conn.execute(
        """
        SELECT o.order_date, o.order_number, p.sku, COALESCE(p.name, o.product_description) AS product_name,
               p.asin, o.quantity, o.status, o.shipped_date, o.notes, o.user_name_snapshot
        FROM orders o
        LEFT JOIN products p ON p.id = o.product_id
        ORDER BY o.order_date DESC
        """
    ).fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Order Number", "SKU", "Product", "ASIN", "Quantity",
                      "Status", "Shipped Date", "Notes", "Logged By"])
    for r in rows:
        writer.writerow([r["order_date"], r["order_number"], r["sku"] or "", r["product_name"] or "",
                          r["asin"] or "", r["quantity"], ORDER_STATUS_LABELS.get(r["status"], r["status"]),
                          r["shipped_date"] or "", r["notes"] or "", r["user_name_snapshot"]])
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=orders_export.csv"},
    )


# ---------------------------------------------------------------------------

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\nDS Amazon Stock Management running — open http://localhost:{port} in your browser.")
    print("Other computers on your network can use your machine's local IP instead of 'localhost'.\n")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
