from flask import Flask, render_template, request, redirect, send_file
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
from io import BytesIO
from datetime import date
from flask import session
import uuid
from datetime import datetime
from urllib.parse import quote_plus
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import text

app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://neondb_owner:npg_i0urhNxL8Ucz@ep-long-salad-aqpf88lx-pooler.c-8.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


db = SQLAlchemy(app)

app.secret_key = "erp-secret-key"


# ================= LOGIN DECORATOR =================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function


# ================= USER MODEL =================
class User(db.Model):
    __tablename__ = "users"
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default="viewer")  # admin, manager, viewer
    
    # Permissions
    can_view_base_stock = db.Column(db.Boolean, default=True)
    can_edit_base_stock = db.Column(db.Boolean, default=False)
    can_delete_base_stock = db.Column(db.Boolean, default=False)
    can_upload_base_stock = db.Column(db.Boolean, default=False)
    
    can_view_actual_stock = db.Column(db.Boolean, default=True)
    can_edit_actual_stock = db.Column(db.Boolean, default=False)
    can_delete_actual_stock = db.Column(db.Boolean, default=False)
    
    can_view_order_sheet = db.Column(db.Boolean, default=True)
    can_add_order = db.Column(db.Boolean, default=False)
    can_edit_order = db.Column(db.Boolean, default=False)
    can_delete_order = db.Column(db.Boolean, default=False)
    can_complete_order = db.Column(db.Boolean, default=False)
    
    can_view_requirement = db.Column(db.Boolean, default=True)
    can_export_requirement = db.Column(db.Boolean, default=False)
    
    can_view_custom_order = db.Column(db.Boolean, default=False)
    can_generate_order = db.Column(db.Boolean, default=False)
    
    can_manage_users = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.now)


# ================= MODEL =================
class BaseStock(db.Model):

    __tablename__ = "base_stock"

    id = db.Column(db.Integer, primary_key=True)

    ebo = db.Column(db.String(100))
    product = db.Column(db.String(200))
    color = db.Column(db.String(100))
    size = db.Column(db.String(50))

    qty = db.Column(db.Integer)


# ================= HOME =================
@app.route("/")
def home():
    if "user_id" not in session:
        return redirect("/login")
    return redirect("/base-stock")


# ================= BASE STOCK =================
@app.route("/base-stock")
@login_required
def base_stock():

    ebos_selected = request.args.getlist("ebo")
    products_selected = request.args.getlist("product")
    colors_selected = request.args.getlist("color")
    sizes_selected = request.args.getlist("size")

    query = BaseStock.query

    if ebos_selected:
        query = query.filter(BaseStock.ebo.in_(ebos_selected))

    if products_selected:
        query = query.filter(BaseStock.product.in_(products_selected))

    if colors_selected:
        query = query.filter(BaseStock.color.in_(colors_selected))

    if sizes_selected:
        query = query.filter(BaseStock.size.in_(sizes_selected))

    rows = query.all()

    ebos = db.session.query(BaseStock.ebo).distinct().all()
    products = db.session.query(BaseStock.product).distinct().all()
    colors = db.session.query(BaseStock.color).distinct().all()
    sizes = db.session.query(BaseStock.size).distinct().all()

    total_qty = sum(r.qty for r in rows)

    return render_template(
        "base_stock.html",
        rows=rows,
        ebos=ebos,
        products=products,
        colors=colors,
        sizes=sizes,
        total_qty=total_qty,
        ebos_selected=ebos_selected,
        products_selected=products_selected,
        colors_selected=colors_selected,
        sizes_selected=sizes_selected
    )


# ================= ADD STOCK =================
@app.route("/add-stock", methods=["POST"])
@login_required
def add_stock():

    row = BaseStock(
        ebo=request.form["ebo"],
        product=request.form["product"],
        color=request.form["color"],
        size=request.form["size"],
        qty=request.form["qty"]
    )

    db.session.add(row)
    db.session.commit()

    return redirect("/base-stock")


# ================= DELETE =================
@app.route("/delete/<int:id>")
@login_required
def delete_stock(id):

    row = BaseStock.query.get(id)

    if row:
        db.session.delete(row)
        db.session.commit()

    return redirect("/base-stock")


# ================= EDIT =================
@app.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_stock(id):

    row = BaseStock.query.get_or_404(id)

    if request.method == "POST":

        row.ebo = request.form["ebo"]
        row.product = request.form["product"]
        row.color = request.form["color"]
        row.size = request.form["size"]
        row.qty = request.form["qty"]

        db.session.commit()

        return redirect("/base-stock")

    return render_template("edit_stock.html", row=row)


# ================= EXCEL UPLOAD =================
@app.route("/upload", methods=["POST"])
@login_required
def upload_excel():

    file = request.files["file"]

    replace = request.form.get("replace")

    try:
        df = pd.read_excel(file)
    except Exception as e:
        return f"Error reading Excel file: {e}", 400

    df.columns = [str(c).strip().upper() for c in df.columns]

    # REPLACE OLD DATA
    if replace == "1":

        BaseStock.query.delete()

        db.session.commit()

    # INSERT NEW DATA
    for _, r in df.iterrows():

        qty_val = r.get("QTY", 0)
        try:
            qty_val = int(qty_val) if pd.notna(qty_val) else 0
        except (ValueError, TypeError):
            qty_val = 0

        row = BaseStock(
            ebo=str(r.get("EBO", "")) if pd.notna(r.get("EBO")) else "",
            product=str(r.get("PRODUCT", "")) if pd.notna(r.get("PRODUCT")) else "",
            color=str(r.get("COLOR", "")) if pd.notna(r.get("COLOR")) else "",
            size=str(r.get("SIZE", "")) if pd.notna(r.get("SIZE")) else "",
            qty=qty_val
        )

        db.session.add(row)

    db.session.commit()

    return redirect("/base-stock")


# ================= EXPORT =================
@app.route("/export")
@login_required
def export_excel():

    rows = BaseStock.query.all()

    data = []

    for r in rows:

        data.append({
            "EBO": r.ebo,
            "PRODUCT": r.product,
            "COLOR": r.color,
            "SIZE": r.size,
            "QTY": r.qty
        })

    df = pd.DataFrame(data)

    output = BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)

    output.seek(0)

    return send_file(
        output,
        download_name="base_stock.xlsx",
        as_attachment=True
    )

# ================= ACTUAL STOCK MODEL =================

class ActualStock(db.Model):

    __tablename__ = "actual_stock"

    id = db.Column(db.Integer, primary_key=True)

    ebo = db.Column(db.String(100))
    product = db.Column(db.String(200))
    color = db.Column(db.String(100))
    size = db.Column(db.String(50))

    actual_qty = db.Column(db.Integer)


# ================= ACTUAL STOCK PAGE =================

@app.route("/actual-stock")
@login_required
def actual_stock():

    ebos_selected = request.args.getlist("ebo")
    products_selected = request.args.getlist("product")
    colors_selected = request.args.getlist("color")
    sizes_selected = request.args.getlist("size")

    query = ActualStock.query

    if ebos_selected:
        query = query.filter(ActualStock.ebo.in_(ebos_selected))

    if products_selected:
        query = query.filter(ActualStock.product.in_(products_selected))

    if colors_selected:
        query = query.filter(ActualStock.color.in_(colors_selected))

    if sizes_selected:
        query = query.filter(ActualStock.size.in_(sizes_selected))

    rows = query.all()

    ebos = db.session.query(ActualStock.ebo).distinct().all()
    products = db.session.query(ActualStock.product).distinct().all()
    colors = db.session.query(ActualStock.color).distinct().all()
    sizes = db.session.query(ActualStock.size).distinct().all()

    total_actual = sum(r.actual_qty for r in rows)

    return render_template(
        "actual_stock.html",
        rows=rows,
        ebos=ebos,
        products=products,
        colors=colors,
        sizes=sizes,
        total_actual=total_actual,
        ebos_selected=ebos_selected,
        products_selected=products_selected,
        colors_selected=colors_selected,
        sizes_selected=sizes_selected
    )


# ================= ADD ACTUAL STOCK =================

@app.route("/add-actual-stock", methods=["POST"])
@login_required
def add_actual_stock():

    row = ActualStock(
        ebo=request.form["ebo"],
        product=request.form["product"],
        color=request.form["color"],
        size=request.form["size"],
        actual_qty=request.form["actual_qty"]
    )

    db.session.add(row)
    db.session.commit()

    return redirect("/actual-stock")


# ================= DELETE ACTUAL STOCK =================

@app.route("/delete-actual-stock/<int:id>")
@login_required
def delete_actual_stock(id):

    row = ActualStock.query.get(id)

    if row:
        db.session.delete(row)
        db.session.commit()

    return redirect("/actual-stock")


# ================= EDIT ACTUAL STOCK =================

@app.route("/edit-actual-stock/<int:id>", methods=["GET", "POST"])
@login_required
def edit_actual_stock(id):

    row = ActualStock.query.get_or_404(id)

    if request.method == "POST":

        row.ebo = request.form["ebo"]
        row.product = request.form["product"]
        row.color = request.form["color"]
        row.size = request.form["size"]
        row.actual_qty = request.form["actual_qty"]

        db.session.commit()

        return redirect("/actual-stock")

    return render_template(
        "edit_actual_stock.html",
        row=row
    )


# ================= UPLOAD EXCEL =================

@app.route("/upload-actual-stock", methods=["POST"])
@login_required
def upload_actual_stock():

    file = request.files["file"]

    replace = request.form.get("replace")

    try:
        df = pd.read_excel(file)
    except Exception as e:
        return f"Error reading Excel file: {e}", 400

    df.columns = [str(c).strip().upper() for c in df.columns]

    # REPLACE OLD DATA
    if replace == "1":

        ActualStock.query.delete()

        db.session.commit()

    for _, r in df.iterrows():

        qty_val = r.get("ACTUAL_QTY", r.get("ACTUAL QTY", r.get("QTY", 0)))
        try:
            qty_val = int(qty_val) if pd.notna(qty_val) else 0
        except (ValueError, TypeError):
            qty_val = 0

        row = ActualStock(
            ebo=str(r.get("EBO", "")) if pd.notna(r.get("EBO")) else "",
            product=str(r.get("PRODUCT", "")) if pd.notna(r.get("PRODUCT")) else "",
            color=str(r.get("COLOR", "")) if pd.notna(r.get("COLOR")) else "",
            size=str(r.get("SIZE", "")) if pd.notna(r.get("SIZE")) else "",
            actual_qty=qty_val
        )

        db.session.add(row)

    db.session.commit()

    return redirect("/actual-stock")


# ================= EXPORT EXCEL =================

@app.route("/export-actual-stock")
@login_required
def export_actual_stock():

    rows = ActualStock.query.all()

    data = []

    for r in rows:

        data.append({
            "EBO": r.ebo,
            "PRODUCT": r.product,
            "COLOR": r.color,
            "SIZE": r.size,
            "ACTUAL_QTY": r.actual_qty
        })

    df = pd.DataFrame(data)

    output = BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)

    output.seek(0)

    return send_file(
        output,
        download_name="actual_stock.xlsx",
        as_attachment=True
    )

# ================= REQUIREMENT REPORT =================   

@app.route("/requirement-report")
@login_required
def requirement_report():

    group_by = request.args.get("group_by", "ebo")

    include_process = request.args.get(
        "include_process",
        "yes"
    )

    status_filter = request.args.get(
        "status_filter",
        "both"
    )

    ebos_selected = request.args.getlist("ebo")
    products_selected = request.args.getlist("product")
    colors_selected = request.args.getlist("color")
    sizes_selected = request.args.getlist("size")

    query = BaseStock.query

    if ebos_selected:
        query = query.filter(BaseStock.ebo.in_(ebos_selected))
    if products_selected:
        query = query.filter(BaseStock.product.in_(products_selected))
    if colors_selected:
        query = query.filter(BaseStock.color.in_(colors_selected))
    if sizes_selected:
        query = query.filter(BaseStock.size.in_(sizes_selected))

    base_rows = query.all()
    actual_rows = ActualStock.query.all()
    process_rows = OrderSheet.query.filter_by(status="UNDER PROCESS").all()

    # ================= ACTUAL MAP =================

    actual_map = {}

    for a in actual_rows:

        key = (
            a.ebo,
            a.product,
            a.color,
            a.size
        )

        actual_map[key] = a.actual_qty

    # ================= PROCESS MAP =================

    process_map = {}

    for p in process_rows:

        key = (
            p.ebo,
            p.product,
            p.color,
            p.size
        )

        process_map[key] = process_map.get(key, 0) + p.qty

    report_data = []

    # ================= REPORT LOGIC =================

    for b in base_rows:

        key = (
            b.ebo,
            b.product,
            b.color,
            b.size
        )

        actual_qty = actual_map.get(key, 0)

        process_qty = 0

        if include_process == "yes":
            process_qty = process_map.get(key, 0)

        covered_qty = actual_qty + process_qty
        requirement_qty = max(0, b.qty - covered_qty)
        excess_qty = max(0, covered_qty - b.qty)

        # FILTER BY REQUIREMENT/EXCESS/BOTH
        if status_filter == "requirements" and requirement_qty == 0:
            continue
        if status_filter == "excess" and excess_qty == 0:
            continue

        # DYNAMIC GROUP VALUE
        group_value = getattr(b, group_by)

        report_data.append({

            "group_value": group_value,

            "ebo": b.ebo,
            "product": b.product,
            "color": b.color,
            "size": b.size,

            "base_qty": b.qty,
            "actual_qty": actual_qty,
            "process_qty": process_qty,

            "requirement_qty": requirement_qty,
            "excess_qty": excess_qty

        })

    ebos = db.session.query(BaseStock.ebo).distinct().all()
    products = db.session.query(BaseStock.product).distinct().all()
    colors = db.session.query(BaseStock.color).distinct().all()
    sizes = db.session.query(BaseStock.size).distinct().all()

    return render_template(
        "requirement_report.html",
        report_data=report_data,
        group_by=group_by,
        include_process=include_process,
        status_filter=status_filter,
        ebos=ebos,
        products=products,
        colors=colors,
        sizes=sizes,
        ebos_selected=ebos_selected,
        products_selected=products_selected,
        colors_selected=colors_selected,
        sizes_selected=sizes_selected
    )

@app.route("/export-requirement-report")
@login_required
def export_requirement_report():
    group_by = request.args.get("group_by", "ebo")
    include_process = request.args.get("include_process", "yes")
    status_filter = request.args.get("status_filter", "both")

    ebos_selected = request.args.getlist("ebo")
    products_selected = request.args.getlist("product")
    colors_selected = request.args.getlist("color")
    sizes_selected = request.args.getlist("size")

    query = BaseStock.query

    if ebos_selected:
        query = query.filter(BaseStock.ebo.in_(ebos_selected))
    if products_selected:
        query = query.filter(BaseStock.product.in_(products_selected))
    if colors_selected:
        query = query.filter(BaseStock.color.in_(colors_selected))
    if sizes_selected:
        query = query.filter(BaseStock.size.in_(sizes_selected))

    base_rows = query.all()
    actual_rows = ActualStock.query.all()
    process_rows = OrderSheet.query.filter_by(status="UNDER PROCESS").all()

    actual_map = {}
    for a in actual_rows:
        actual_map[(a.ebo, a.product, a.color, a.size)] = a.actual_qty

    process_map = {}
    for p in process_rows:
        key = (p.ebo, p.product, p.color, p.size)
        process_map[key] = process_map.get(key, 0) + p.qty

    data = []
    for b in base_rows:
        key = (b.ebo, b.product, b.color, b.size)
        actual_qty = actual_map.get(key, 0)
        process_qty = process_map.get(key, 0) if include_process == "yes" else 0
        covered_qty = actual_qty + process_qty
        requirement_qty = max(0, b.qty - covered_qty)
        excess_qty = max(0, covered_qty - b.qty)

        if status_filter == "requirements" and requirement_qty == 0:
            continue
        if status_filter == "excess" and excess_qty == 0:
            continue

        data.append({
            group_by.upper(): getattr(b, group_by),
            "EBO": b.ebo,
            "PRODUCT": b.product,
            "COLOR": b.color,
            "SIZE": b.size,
            "BASE_QTY": b.qty,
            "ACTUAL_QTY": actual_qty,
            "PROCESS_QTY": process_qty,
            "REQUIREMENT_QTY": requirement_qty,
            "EXCESS_QTY": excess_qty,
            "INCLUDE_PROCESS": include_process.upper(),
        "STATUS_FILTER": status_filter.upper()
        })

    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)

    return send_file(
        output,
        download_name="requirement_report.xlsx",
        as_attachment=True
    )

# ================= ORDER SHEET MODEL =================

class OrderSheet(db.Model):

    __tablename__ = "order_sheets"

    id = db.Column(db.Integer, primary_key=True)

    order_sheet_no = db.Column(db.String(100))

    ebo = db.Column(db.String(100))
    product = db.Column(db.String(200))
    color = db.Column(db.String(100))
    size = db.Column(db.String(50))

    qty = db.Column(db.Integer)

    status = db.Column(db.String(50))

    order_date = db.Column(db.Date)
    complete_date = db.Column(db.Date)

# ================= ORDER SHEET PAGE =================

@app.route("/order-sheet")
@login_required
def order_sheet():

    rows = OrderSheet.query.order_by(
        OrderSheet.id.desc()
    ).all()

    return render_template(
        "order_sheet.html",
        rows=rows
    )
def next_order_sheet_no():

    last = OrderSheet.query.order_by(
        OrderSheet.id.desc()
    ).first()

    if not last:
        return "OS001"

    num = int(
        last.order_sheet_no.replace("OS", "")
    )

    return f"OS{num+1:03d}"
# ================= ADD ORDER =================

@app.route("/add-order", methods=["POST"])
@login_required
def add_order():

    row = OrderSheet(

        order_sheet_no=next_order_sheet_no(),

        ebo=request.form["ebo"],
        product=request.form["product"],
        color=request.form["color"],
        size=request.form["size"],

        qty=request.form["qty"],

        status="UNDER PROCESS",

        order_date=datetime.now().date()

    )

    db.session.add(row)

    db.session.commit()

    return redirect("/order-sheet")

# ================= DELETE ORDER =================

@app.route("/delete-order/<int:id>")
@login_required
def delete_order(id):

    row = OrderSheet.query.get(id)

    if row:

        db.session.delete(row)
        db.session.commit()

    return redirect("/order-sheet")

# ================= COMPLETE ORDER =================

@app.route("/complete-order/<int:id>")
@login_required
def complete_order(id):

    row = OrderSheet.query.get(id)

    if row:

        row.status = "COMPLETED"

        row.complete_date = datetime.now().date()

        db.session.commit()

    return redirect("/order-sheet")

# ================= BATCH ORDER ACTION =================

@app.route("/batch-order-action", methods=["POST"])
@login_required
def batch_order_action():

    selected_ids = request.form.getlist("selected_ids")
    action = request.form.get("action")

    if selected_ids and action in {"delete", "complete"}:
        try:
            ids = [int(i) for i in selected_ids if str(i).isdigit()]
        except ValueError:
            ids = []

        if ids:
            rows = OrderSheet.query.filter(OrderSheet.id.in_(ids)).all()

            if action == "delete":
                for row in rows:
                    db.session.delete(row)

            elif action == "complete":
                for row in rows:
                    if row.status != "COMPLETED":
                        row.status = "COMPLETED"
                        row.complete_date = datetime.now().date()

            db.session.commit()

    return redirect("/order-sheet")

# ================= EDIT ORDER =================

@app.route("/edit-order/<int:id>", methods=["GET", "POST"])
@login_required
def edit_order(id):

    row = OrderSheet.query.get_or_404(id)

    if request.method == "POST":

        row.ebo = request.form["ebo"]
        row.product = request.form["product"]
        row.color = request.form["color"]
        row.size = request.form["size"]

        row.qty = request.form["qty"]

        db.session.commit()

        return redirect("/order-sheet")

    return render_template(
        "edit_order.html",
        row=row
    )
# ================= CUSTOM ORDER GENERATION =================

@app.route("/custom-order-generation")
@login_required
def custom_order_generation():

    if "frozen_orders" not in session:
        session["frozen_orders"] = []

    # FILTER VALUES
    ebo_filter = request.args.getlist("ebo")
    product_filter = request.args.getlist("product")
    color_filter = request.args.getlist("color")
    size_filter = request.args.getlist("size")

    base_query = BaseStock.query

    # APPLY FILTERS
    if ebo_filter:
        base_query = base_query.filter(
            BaseStock.ebo.in_(ebo_filter)
        )

    if product_filter:
        base_query = base_query.filter(
            BaseStock.product.in_(product_filter)
        )

    if color_filter:
        base_query = base_query.filter(
            BaseStock.color.in_(color_filter)
        )

    if size_filter:
        base_query = base_query.filter(
            BaseStock.size.in_(size_filter)
        )

    base_rows = base_query.all()

    actual_rows = ActualStock.query.all()
    process_rows = OrderSheet.query.filter_by(status="UNDER PROCESS").all()

    actual_map = {}

    for a in actual_rows:

        key = (
            a.ebo,
            a.product,
            a.color,
            a.size
        )

        actual_map[key] = a.actual_qty

    process_map = {}

    for p in process_rows:

        key = (
            p.ebo,
            p.product,
            p.color,
            p.size
        )

        process_map[key] = process_map.get(key, 0) + p.qty

    frozen_orders = session.get("frozen_orders", [])
    frozen_map = {}

    for f in frozen_orders:
        key = (f["ebo"], f["product"], f["color"], f["size"])
        frozen_map[key] = frozen_map.get(key, 0) + int(f["order_qty"])

    report_data = []

    for b in base_rows:

        key = (
            b.ebo,
            b.product,
            b.color,
            b.size
        )

        actual_qty = actual_map.get(key, 0)
        process_qty = process_map.get(key, 0)
        frozen_qty = frozen_map.get(key, 0)

        requirement_qty = b.qty - actual_qty + process_qty - frozen_qty

        if requirement_qty <= 0:
            continue

        report_data.append({

            "id": str(uuid.uuid4()),

            "ebo": b.ebo,
            "product": b.product,
            "color": b.color,
            "size": b.size,

            "base_qty": b.qty,
            "actual_qty": actual_qty,
            "process_qty": process_qty,
            "frozen_qty": frozen_qty,

            "requirement_qty": requirement_qty,
            "order_qty": requirement_qty

        })

    frozen_orders = session.get("frozen_orders", [])

    # DROPDOWN VALUES
    ebos = db.session.query(
        BaseStock.ebo
    ).distinct().all()

    products = db.session.query(
        BaseStock.product
    ).distinct().all()

    colors = db.session.query(
        BaseStock.color
    ).distinct().all()

    sizes = db.session.query(
        BaseStock.size
    ).distinct().all()

    return render_template(

        "custom_order_generation.html",

        report_data=report_data,
        frozen_orders=frozen_orders,

        ebos=ebos,
        products=products,
        colors=colors,
        sizes=sizes,

        ebo_filter=ebo_filter,
        product_filter=product_filter,
        color_filter=color_filter,
        size_filter=size_filter

    )
# ================= FREEZE ORDER =================

@app.route("/freeze-order", methods=["POST"])
@login_required
def freeze_order():

    frozen_orders = session.get("frozen_orders", [])

    row = {
        "ebo": request.form["ebo"],
        "product": request.form["product"],
        "color": request.form["color"],
        "size": request.form["size"],
        "base_qty": request.form["base_qty"],
        "actual_qty": request.form["actual_qty"],
        "process_qty": request.form["process_qty"],
        "requirement_qty": request.form["requirement_qty"],
        "order_qty": request.form["order_qty"]
    }

    exists = False

    for f in frozen_orders:

        if (
            f["ebo"] == row["ebo"] and
            f["product"] == row["product"] and
            f["color"] == row["color"] and
            f["size"] == row["size"]
        ):

            f["order_qty"] = row["order_qty"]
            exists = True
            break

    if not exists:
        frozen_orders.append(row)

    session["frozen_orders"] = frozen_orders

    return redirect("/custom-order-generation")

# ================= FREEZE SELECTED =================

@app.route("/freeze-selected", methods=["POST"])
@login_required
def freeze_selected():

    selected_rows = request.form.getlist("selected_row")
    if not selected_rows:
        return redirect("/custom-order-generation")

    all_values = {
        "ebo": request.form.getlist("ebo"),
        "product": request.form.getlist("product"),
        "color": request.form.getlist("color"),
        "size": request.form.getlist("size"),
        "base_qty": request.form.getlist("base_qty"),
        "actual_qty": request.form.getlist("actual_qty"),
        "process_qty": request.form.getlist("process_qty"),
        "requirement_qty": request.form.getlist("requirement_qty"),
        "order_qty": request.form.getlist("order_qty")
    }

    frozen_orders = session.get("frozen_orders", [])

    for idx_str in selected_rows:
        try:
            idx = int(idx_str)
        except ValueError:
            continue

        if idx < 0 or idx >= len(all_values["ebo"]):
            continue

        row = {
            "ebo": all_values["ebo"][idx],
            "product": all_values["product"][idx],
            "color": all_values["color"][idx],
            "size": all_values["size"][idx],
            "base_qty": all_values["base_qty"][idx],
            "actual_qty": all_values["actual_qty"][idx],
            "process_qty": all_values["process_qty"][idx],
            "requirement_qty": all_values["requirement_qty"][idx],
            "order_qty": all_values["order_qty"][idx]
        }

        exists = False
        for f in frozen_orders:
            if (
                f["ebo"] == row["ebo"] and
                f["product"] == row["product"] and
                f["color"] == row["color"] and
                f["size"] == row["size"]
            ):
                f["order_qty"] = row["order_qty"]
                exists = True
                break

        if not exists:
            frozen_orders.append(row)

    session["frozen_orders"] = frozen_orders

    query_parts = []
    for value in request.form.getlist("filter_ebo"):
        query_parts.append(f"ebo={quote_plus(value)}")
    for value in request.form.getlist("filter_product"):
        query_parts.append(f"product={quote_plus(value)}")
    for value in request.form.getlist("filter_color"):
        query_parts.append(f"color={quote_plus(value)}")
    for value in request.form.getlist("filter_size"):
        query_parts.append(f"size={quote_plus(value)}")

    redirect_url = "/custom-order-generation"
    if query_parts:
        redirect_url += "?" + "&".join(query_parts)

    return redirect(redirect_url)

# ================= REMOVE FROZEN =================

@app.route(
"/remove-frozen/<ebo>/<product>/<color>/<size>"
)
@login_required
def remove_frozen(
    ebo,
    product,
    color,
    size
):

    frozen_orders = session.get("frozen_orders", [])

    frozen_orders = [
        f for f in frozen_orders
        if not (
            f["ebo"] == ebo and
            f["product"] == product and
            f["color"] == color and
            f["size"] == size
        )
    ]

    session["frozen_orders"] = frozen_orders

    return redirect("/custom-order-generation")

# ================= GENERATE ORDER SHEET =================

@app.route("/generate-order-sheet")
@login_required
def generate_order_sheet():

    frozen_orders = session.get("frozen_orders", [])

    if frozen_orders:
        order_sheet_no = next_order_sheet_no()

        for f in frozen_orders:

            row = OrderSheet(

                order_sheet_no=order_sheet_no,

                ebo=f["ebo"],
                product=f["product"],
                color=f["color"],
                size=f["size"],

                qty=int(f["order_qty"]),

                status="UNDER PROCESS",

                order_date=datetime.now().date()
            )

            db.session.add(row)

        db.session.commit()

        session["frozen_orders"] = []

    return redirect("/order-sheet")

from collections import defaultdict


@app.route("/view-order/<int:id>")
@login_required
def view_order(id):

    row = OrderSheet.query.get_or_404(id)

    all_rows = OrderSheet.query.filter_by(
        order_sheet_no=row.order_sheet_no
    ).all()

    grouped_data = defaultdict(lambda: defaultdict(list))

    grand_totals = {}

    # ================= GROUP DATA =================

    for r in all_rows:

        product = r.product
        color = r.color

        size_data = {
            "ebo": r.ebo,
            "s": 0,
            "m": 0,
            "l": 0,
            "xl": 0,
            "xxl": 0,
            "xxxl": 0,
            "xxxxl": 0
        }

        size_name = str(r.size).strip().upper()

        if size_name == "S":
            size_data["s"] = r.qty

        elif size_name == "M":
            size_data["m"] = r.qty

        elif size_name == "L":
            size_data["l"] = r.qty

        elif size_name == "XL":
            size_data["xl"] = r.qty

        elif size_name == "2XL":
            size_data["xxl"] = r.qty

        elif size_name == "3XL":
            size_data["xxxl"] = r.qty

        elif size_name == "4XL":
            size_data["xxxxl"] = r.qty

        grouped_data[product][color].append(size_data)

    # ================= GRAND TOTALS =================

    for product, colors in grouped_data.items():

        totals = {
            "s": 0,
            "m": 0,
            "l": 0,
            "xl": 0,
            "xxl": 0,
            "xxxl": 0,
            "xxxxl": 0
        }

        for color_rows in colors.values():

            for r in color_rows:

                totals["s"] += r["s"]
                totals["m"] += r["m"]
                totals["l"] += r["l"]
                totals["xl"] += r["xl"]
                totals["xxl"] += r["xxl"]
                totals["xxxl"] += r["xxxl"]
                totals["xxxxl"] += r["xxxxl"]

        grand_totals[product] = totals

    return render_template(

        "view_order.html",

        grouped_data=grouped_data,
        grand_totals=grand_totals,

        order_sheet_no=row.order_sheet_no,
        order_date=row.order_date,
        status=row.status

    )



# ================= DEPENDENT FILTER =================

@app.route("/get-dependent-filters")
@login_required
def get_dependent_filters():

    page = request.args.get("page", "base")

    ebos = request.args.getlist("ebo")
    products = request.args.getlist("product")
    colors = request.args.getlist("color")

    # ================= MODEL SELECTION =================

    if page == "actual":
        Model = ActualStock

    else:
        Model = BaseStock

    # ================= PRODUCTS =================

    product_query = Model.query

    if ebos:
        product_query = product_query.filter(
            db.func.trim(Model.ebo).in_(ebos)
        )

    product_rows = product_query.all()

    product_values = sorted(
        list(set(
            r.product.strip()
            for r in product_rows
            if r.product
        ))
    )

    # ================= COLORS =================

    color_query = Model.query

    if ebos:
        color_query = color_query.filter(
            db.func.trim(Model.ebo).in_(ebos)
        )

    if products:
        color_query = color_query.filter(
            db.func.trim(Model.product).in_(products)
        )

    color_rows = color_query.all()

    color_values = sorted(
        list(set(
            r.color.strip()
            for r in color_rows
            if r.color
        ))
    )

    # ================= SIZES =================

    size_query = Model.query

    if ebos:
        size_query = size_query.filter(
            db.func.trim(Model.ebo).in_(ebos)
        )

    if products:
        size_query = size_query.filter(
            db.func.trim(Model.product).in_(products)
        )

    if colors:
        size_query = size_query.filter(
            db.func.trim(Model.color).in_(colors)
        )

    size_rows = size_query.all()

    size_values = sorted(
        list(set(
            r.size.strip()
            for r in size_rows
            if r.size
        ))
    )

    return {
        "products": product_values,
        "colors": color_values,
        "sizes": size_values
    }


# ================= USER MANAGEMENT =================

@app.route("/users")
@login_required
def users():
    users_list = User.query.all()
    return render_template("users.html", users=users_list)


@app.route("/add-user", methods=["GET", "POST"])
@login_required
def add_user():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        role = request.form.get("role", "viewer")
        
        # Check if user exists
        if User.query.filter_by(username=username).first():
            return "Username already exists", 400
        
        user = User(
            username=username,
            email=email,
            password=generate_password_hash(password),  # Hash the password
            role=role
        )
        
        # Set permissions based on role
        if role == "admin":
            user.can_edit_base_stock = True
            user.can_delete_base_stock = True
            user.can_upload_base_stock = True
            user.can_edit_actual_stock = True
            user.can_delete_actual_stock = True
            user.can_add_order = True
            user.can_edit_order = True
            user.can_delete_order = True
            user.can_complete_order = True
            user.can_export_requirement = True
            user.can_view_custom_order = True
            user.can_generate_order = True
            user.can_manage_users = True
        
        elif role == "manager":
            user.can_edit_base_stock = True
            user.can_upload_base_stock = True
            user.can_edit_actual_stock = True
            user.can_add_order = True
            user.can_edit_order = True
            user.can_complete_order = True
            user.can_export_requirement = True
            user.can_view_custom_order = True
            user.can_generate_order = True
        
        # viewer has default read-only permissions
        
        db.session.add(user)
        db.session.commit()
        
        return redirect("/users")
    
    return render_template("add_user.html")


@app.route("/edit-user/<int:id>", methods=["GET", "POST"])
@login_required
def edit_user(id):
    user = User.query.get_or_404(id)
    
    if request.method == "POST":
        user.username = request.form.get("username", user.username)
        user.email = request.form.get("email", user.email)
        user.role = request.form.get("role", user.role)
        
        # Update permissions based on checkboxes
        user.can_view_base_stock = "can_view_base_stock" in request.form
        user.can_edit_base_stock = "can_edit_base_stock" in request.form
        user.can_delete_base_stock = "can_delete_base_stock" in request.form
        user.can_upload_base_stock = "can_upload_base_stock" in request.form
        
        user.can_view_actual_stock = "can_view_actual_stock" in request.form
        user.can_edit_actual_stock = "can_edit_actual_stock" in request.form
        user.can_delete_actual_stock = "can_delete_actual_stock" in request.form
        
        user.can_view_order_sheet = "can_view_order_sheet" in request.form
        user.can_add_order = "can_add_order" in request.form
        user.can_edit_order = "can_edit_order" in request.form
        user.can_delete_order = "can_delete_order" in request.form
        user.can_complete_order = "can_complete_order" in request.form
        
        user.can_view_requirement = "can_view_requirement" in request.form
        user.can_export_requirement = "can_export_requirement" in request.form
        
        user.can_view_custom_order = "can_view_custom_order" in request.form
        user.can_generate_order = "can_generate_order" in request.form
        
        user.can_manage_users = "can_manage_users" in request.form
        
        db.session.commit()
        return redirect("/users")
    
    return render_template("edit_user.html", user=user)


@app.route("/delete-user/<int:id>")
@login_required
def delete_user(id):
    user = User.query.get(id)
    if user:
        db.session.delete(user)
        db.session.commit()
    return redirect("/users")


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()

        if user:
            password_matches = False

            # Prefer hashed password verification
            try:
                password_matches = check_password_hash(user.password, password)
            except ValueError:
                password_matches = False

            # Allow legacy plain-text password fallback and auto-migrate to hash
            if not password_matches and user.password == password:
                password_matches = True
                user.password = generate_password_hash(password)
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()

            if password_matches:
                session["user_id"] = user.id
                session["username"] = user.username
                session["role"] = user.role
                return redirect("/base-stock")

        error = "Invalid username or password"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


def ensure_password_column_size():
    # PostgreSQL may already have a users.password column limited to 100 chars.
    # If so, enlarge it to support hashed passwords.
    try:
        result = db.session.execute(
            text(
                "SELECT character_maximum_length FROM information_schema.columns "
                "WHERE table_name='users' AND column_name='password'"
            )
        ).fetchone()
    except Exception as exc:
        print("ensure_password_column_size failed:", exc)
        return

    if result and result[0] is not None and result[0] < 255:
        try:
            db.session.execute(
                text("ALTER TABLE public.users ALTER COLUMN password TYPE VARCHAR(255);")
            )
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            print("password column resize failed:", exc)


with app.app_context():
    db.create_all()
    ensure_password_column_size()

if __name__ == "__main__":
    app.run(debug=True)
