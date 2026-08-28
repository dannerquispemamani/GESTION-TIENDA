"""
Gestión Comercial
Sistema de Gestión de Ventas e Inventario para Tiendas de Barrio y Minimarkets
Capa de Presentación (UI) + Lógica de Negocio (BLL) -> database.py (DAL)
"""
import re
from flask import (
    Flask, render_template, request, redirect, url_for, session, flash,
    send_file, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
from functools import wraps
import io

from database import get_connection, init_db, luhn_valido, detectar_marca

app = Flask(__name__)
app.secret_key = "tiendacontrol-clave-secreta-cambiar-en-produccion"

init_db()  # Asegura que la BD y las tablas existan al arrancar


# ---------------------------------------------------------------------------
# Utilidades / decoradores de seguridad
# ---------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("rol") != "Admin":
            flash("Acceso restringido: se requiere rol Administrador.", "danger")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return wrapper


@app.context_processor
def inject_globals():
    conn = get_connection()
    stock_bajo = conn.execute(
        "SELECT COUNT(*) AS c FROM Productos WHERE Stock_Actual <= Stock_Minimo AND Activo=1"
    ).fetchone()["c"]
    conn.close()
    return dict(alertas_stock=stock_bajo, session=session)


# ---------------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    return redirect(url_for("dashboard") if "user_id" in session else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        conn = get_connection()
        user = conn.execute(
            "SELECT * FROM Usuarios WHERE Username = ? AND Activo = 1", (username,)
        ).fetchone()
        conn.close()
        if user and check_password_hash(user["Password_Hash"], password):
            session["user_id"] = user["ID_Usuario"]
            session["nombre"] = user["NombreCompleto"]
            session["rol"] = user["Rol"]
            flash(f"Bienvenido, {user['NombreCompleto']}", "success")
            return redirect(url_for("dashboard"))
        flash("Usuario o contraseña incorrectos.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_connection()
    total_productos = conn.execute("SELECT COUNT(*) c FROM Productos WHERE Activo=1").fetchone()["c"]
    stock_bajo = conn.execute(
        "SELECT * FROM Productos WHERE Stock_Actual <= Stock_Minimo AND Activo=1"
    ).fetchall()
    hoy = date.today().isoformat()
    ventas_hoy = conn.execute(
        "SELECT COUNT(*) c, COALESCE(SUM(Total),0) t FROM Ventas WHERE substr(FechaHora,1,10)=?",
        (hoy,),
    ).fetchone()
    valor_inventario = conn.execute(
        "SELECT COALESCE(SUM(Stock_Actual * Precio_Venta),0) v FROM Productos WHERE Activo=1"
    ).fetchone()["v"]
    ultimas_ventas = conn.execute(
        """SELECT v.ID_Venta, v.FechaHora, v.Total, u.NombreCompleto
           FROM Ventas v JOIN Usuarios u ON u.ID_Usuario = v.ID_Usuario
           ORDER BY v.ID_Venta DESC LIMIT 5"""
    ).fetchall()
    conn.close()
    return render_template(
        "dashboard.html",
        total_productos=total_productos,
        stock_bajo=stock_bajo,
        ventas_hoy_count=ventas_hoy["c"],
        ventas_hoy_total=ventas_hoy["t"],
        valor_inventario=valor_inventario,
        ultimas_ventas=ultimas_ventas,
    )


# ---------------------------------------------------------------------------
# Módulo: Productos e Inventario (CRUD)
# ---------------------------------------------------------------------------
@app.route("/productos")
@login_required
def productos_list():
    q = request.args.get("q", "").strip()
    conn = get_connection()
    if q:
        productos = conn.execute(
            """SELECT * FROM Productos WHERE Activo=1 AND
               (Nombre LIKE ? OR Categoria LIKE ?) ORDER BY Nombre""",
            (f"%{q}%", f"%{q}%"),
        ).fetchall()
    else:
        productos = conn.execute("SELECT * FROM Productos WHERE Activo=1 ORDER BY Nombre").fetchall()
    conn.close()
    return render_template("productos.html", productos=productos, q=q)


@app.route("/productos/nuevo", methods=["GET", "POST"])
@login_required
def producto_nuevo():
    if request.method == "POST":
        try:
            nombre = request.form["nombre"].strip()
            categoria = request.form.get("categoria", "").strip()
            p_compra = float(request.form["precio_compra"])
            p_venta = float(request.form["precio_venta"])
            stock = int(request.form["stock_actual"])
            stock_min = int(request.form["stock_minimo"])
            if not nombre:
                raise ValueError("El nombre es obligatorio.")
            conn = get_connection()
            conn.execute(
                """INSERT INTO Productos
                   (Nombre, Categoria, Precio_Compra, Precio_Venta, Stock_Actual, Stock_Minimo)
                   VALUES (?,?,?,?,?,?)""",
                (nombre, categoria, p_compra, p_venta, stock, stock_min),
            )
            conn.commit()
            conn.close()
            flash("Producto registrado correctamente.", "success")
            return redirect(url_for("productos_list"))
        except (ValueError, KeyError) as e:
            flash(f"Datos inválidos: {e}", "danger")
    return render_template("producto_form.html", producto=None)


@app.route("/productos/<int:pid>/editar", methods=["GET", "POST"])
@login_required
def producto_editar(pid):
    conn = get_connection()
    producto = conn.execute("SELECT * FROM Productos WHERE ID_Producto=?", (pid,)).fetchone()
    if not producto:
        conn.close()
        flash("Producto no encontrado.", "danger")
        return redirect(url_for("productos_list"))

    if request.method == "POST":
        try:
            nombre = request.form["nombre"].strip()
            categoria = request.form.get("categoria", "").strip()
            p_compra = float(request.form["precio_compra"])
            p_venta = float(request.form["precio_venta"])
            stock = int(request.form["stock_actual"])
            stock_min = int(request.form["stock_minimo"])
            conn.execute(
                """UPDATE Productos SET Nombre=?, Categoria=?, Precio_Compra=?, Precio_Venta=?,
                   Stock_Actual=?, Stock_Minimo=? WHERE ID_Producto=?""",
                (nombre, categoria, p_compra, p_venta, stock, stock_min, pid),
            )
            conn.commit()
            flash("Producto actualizado.", "success")
            return redirect(url_for("productos_list"))
        except (ValueError, KeyError) as e:
            flash(f"Datos inválidos: {e}", "danger")
        finally:
            conn.close()
    else:
        conn.close()
    return render_template("producto_form.html", producto=producto)


@app.route("/productos/<int:pid>/eliminar", methods=["POST"])
@login_required
@admin_required
def producto_eliminar(pid):
    conn = get_connection()
    conn.execute("UPDATE Productos SET Activo=0 WHERE ID_Producto=?", (pid,))
    conn.commit()
    conn.close()
    flash("Producto eliminado.", "success")
    return redirect(url_for("productos_list"))


# ---------------------------------------------------------------------------
# Módulo: Punto de Venta (POS)
# ---------------------------------------------------------------------------
@app.route("/pos")
@login_required
def pos():
    conn = get_connection()
    productos = conn.execute(
        "SELECT * FROM Productos WHERE Activo=1 AND Stock_Actual > 0 ORDER BY Nombre"
    ).fetchall()
    conn.close()
    return render_template("pos.html", productos=productos)


@app.route("/api/pos/vender", methods=["POST"])
@login_required
def pos_vender():
    """Registra una venta: valida stock, calcula totales, descuenta inventario."""
    data = request.get_json(force=True)
    items = data.get("items", [])
    metodo_pago = data.get("metodo_pago", "Efectivo")
    if metodo_pago not in ("Efectivo", "Tarjeta"):
        metodo_pago = "Efectivo"

    if not items:
        return jsonify({"ok": False, "error": "El carrito está vacío."}), 400

    conn = get_connection()
    cur = conn.cursor()
    total = 0.0
    detalles = []
    tarjeta_info = None

    try:
        for item in items:
            pid = int(item["id_producto"])
            cantidad = int(item["cantidad"])
            producto = cur.execute(
                "SELECT * FROM Productos WHERE ID_Producto=? AND Activo=1", (pid,)
            ).fetchone()
            if not producto:
                raise ValueError(f"Producto {pid} no existe.")
            if cantidad <= 0:
                raise ValueError("Cantidad inválida.")
            if producto["Stock_Actual"] < cantidad:
                raise ValueError(f"Stock insuficiente para '{producto['Nombre']}'.")
            subtotal = round(producto["Precio_Venta"] * cantidad, 2)
            total += subtotal
            detalles.append((pid, cantidad, producto["Precio_Venta"], subtotal))

        total = round(total, 2)

        if metodo_pago == "Tarjeta":
            id_tarjeta = int(data.get("id_tarjeta", 0) or 0)
            tarjeta = cur.execute(
                "SELECT * FROM TarjetasPago WHERE ID_Tarjeta=? AND ID_Usuario=?",
                (id_tarjeta, session["user_id"]),
            ).fetchone()
            if not tarjeta:
                raise ValueError("Selecciona una tarjeta válida para el cobro.")
            # El pago con tarjeta se autoriza por el monto exacto de la venta.
            monto_pagado = total
            cambio = 0.0
            tarjeta_info = f"{tarjeta['Marca']} **** {tarjeta['Ultimos4']}"
        else:
            monto_pagado = float(data.get("monto_pagado", 0))
            if monto_pagado < total:
                raise ValueError("El monto pagado es menor al total de la venta.")
            cambio = round(monto_pagado - total, 2)

        cur.execute(
            """INSERT INTO Ventas
               (FechaHora, Total, Monto_Pagado, Cambio, ID_Usuario, Metodo_Pago, Tarjeta_Info)
               VALUES (?,?,?,?,?,?,?)""",
            (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), total, monto_pagado, cambio,
                session["user_id"], metodo_pago, tarjeta_info,
            ),
        )
        id_venta = cur.lastrowid

        for pid, cantidad, precio_unit, subtotal in detalles:
            cur.execute(
                """INSERT INTO DetalleVenta (ID_Venta, ID_Producto, Cantidad, Precio_Unitario, Subtotal)
                   VALUES (?,?,?,?,?)""",
                (id_venta, pid, cantidad, precio_unit, subtotal),
            )
            cur.execute(
                "UPDATE Productos SET Stock_Actual = Stock_Actual - ? WHERE ID_Producto=?",
                (cantidad, pid),
            )

        conn.commit()
        return jsonify({
            "ok": True, "id_venta": id_venta, "total": total, "cambio": cambio,
            "metodo_pago": metodo_pago,
        })
    except (ValueError, KeyError) as e:
        conn.rollback()
        return jsonify({"ok": False, "error": str(e)}), 400
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Módulo: Compras (reabastecimiento de inventario) - solo Admin
# ---------------------------------------------------------------------------
@app.route("/compras")
@login_required
@admin_required
def compras():
    conn = get_connection()
    productos = conn.execute(
        "SELECT * FROM Productos WHERE Activo=1 ORDER BY Nombre"
    ).fetchall()
    conn.close()
    return render_template("compras.html", productos=productos)


@app.route("/api/compras/registrar", methods=["POST"])
@login_required
@admin_required
def compras_registrar():
    """Registra una compra: aumenta stock y actualiza el precio de costo del producto."""
    data = request.get_json(force=True)
    items = data.get("items", [])
    proveedor = (data.get("proveedor") or "").strip()

    if not items:
        return jsonify({"ok": False, "error": "El carrito de compra está vacío."}), 400

    conn = get_connection()
    cur = conn.cursor()
    total = 0.0
    detalles = []

    try:
        for item in items:
            pid = int(item["id_producto"])
            cantidad = int(item["cantidad"])
            precio_unit = float(item["precio_unitario"])
            producto = cur.execute(
                "SELECT * FROM Productos WHERE ID_Producto=? AND Activo=1", (pid,)
            ).fetchone()
            if not producto:
                raise ValueError(f"Producto {pid} no existe.")
            if cantidad <= 0:
                raise ValueError("Cantidad inválida.")
            if precio_unit < 0:
                raise ValueError("Precio de compra inválido.")
            subtotal = round(precio_unit * cantidad, 2)
            total += subtotal
            detalles.append((pid, cantidad, precio_unit, subtotal))

        total = round(total, 2)

        cur.execute(
            "INSERT INTO Compras (FechaHora, Proveedor, Total, ID_Usuario) VALUES (?,?,?,?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), proveedor, total, session["user_id"]),
        )
        id_compra = cur.lastrowid

        for pid, cantidad, precio_unit, subtotal in detalles:
            cur.execute(
                """INSERT INTO DetalleCompra (ID_Compra, ID_Producto, Cantidad, Precio_Unitario, Subtotal)
                   VALUES (?,?,?,?,?)""",
                (id_compra, pid, cantidad, precio_unit, subtotal),
            )
            # Aumenta el stock y actualiza el precio de costo con el último precio de compra
            cur.execute(
                "UPDATE Productos SET Stock_Actual = Stock_Actual + ?, Precio_Compra = ? WHERE ID_Producto=?",
                (cantidad, precio_unit, pid),
            )

        conn.commit()
        return jsonify({"ok": True, "id_compra": id_compra, "total": total})
    except (ValueError, KeyError) as e:
        conn.rollback()
        return jsonify({"ok": False, "error": str(e)}), 400
    finally:
        conn.close()


@app.route("/compras/historial")
@login_required
@admin_required
def compras_historial():
    desde = request.args.get("desde", "")
    hasta = request.args.get("hasta", "")
    conn = get_connection()
    query = """SELECT c.*, u.NombreCompleto FROM Compras c
               JOIN Usuarios u ON u.ID_Usuario = c.ID_Usuario WHERE 1=1"""
    params = []
    if desde:
        query += " AND date(c.FechaHora) >= date(?)"
        params.append(desde)
    if hasta:
        query += " AND date(c.FechaHora) <= date(?)"
        params.append(hasta)
    query += " ORDER BY c.ID_Compra DESC"
    compras_rows = conn.execute(query, params).fetchall()
    conn.close()
    return render_template("compras_historial.html", compras=compras_rows, desde=desde, hasta=hasta)


@app.route("/compras/<int:cid>")
@login_required
@admin_required
def compra_detalle(cid):
    conn = get_connection()
    compra = conn.execute(
        """SELECT c.*, u.NombreCompleto FROM Compras c
           JOIN Usuarios u ON u.ID_Usuario=c.ID_Usuario WHERE c.ID_Compra=?""",
        (cid,),
    ).fetchone()
    detalles = conn.execute(
        """SELECT d.*, p.Nombre FROM DetalleCompra d
           JOIN Productos p ON p.ID_Producto = d.ID_Producto WHERE d.ID_Compra=?""",
        (cid,),
    ).fetchall()
    conn.close()
    if not compra:
        flash("Compra no encontrada.", "danger")
        return redirect(url_for("compras_historial"))
    return render_template("compra_detalle.html", compra=compra, detalles=detalles)


@app.route("/compras/<int:cid>/comprobante.pdf")
@login_required
@admin_required
def compra_comprobante_pdf(cid):
    from reports import generar_comprobante_compra_pdf
    conn = get_connection()
    compra = conn.execute(
        """SELECT c.*, u.NombreCompleto FROM Compras c
           JOIN Usuarios u ON u.ID_Usuario=c.ID_Usuario WHERE c.ID_Compra=?""",
        (cid,),
    ).fetchone()
    detalles = conn.execute(
        """SELECT d.*, p.Nombre FROM DetalleCompra d
           JOIN Productos p ON p.ID_Producto = d.ID_Producto WHERE d.ID_Compra=?""",
        (cid,),
    ).fetchall()
    conn.close()
    buffer = generar_comprobante_compra_pdf(compra, detalles)
    return send_file(
        buffer, mimetype="application/pdf", as_attachment=True,
        download_name=f"comprobante_compra_{cid}.pdf",
    )


# ---------------------------------------------------------------------------
# Historial de ventas
# ---------------------------------------------------------------------------
@app.route("/ventas")
@login_required
def ventas_historial():
    fecha_desde = request.args.get("desde", "")
    fecha_hasta = request.args.get("hasta", "")
    conn = get_connection()
    query = """SELECT v.*, u.NombreCompleto FROM Ventas v
               JOIN Usuarios u ON u.ID_Usuario = v.ID_Usuario WHERE 1=1"""
    params = []
    if fecha_desde:
        query += " AND date(v.FechaHora) >= date(?)"
        params.append(fecha_desde)
    if fecha_hasta:
        query += " AND date(v.FechaHora) <= date(?)"
        params.append(fecha_hasta)
    query += " ORDER BY v.ID_Venta DESC"
    ventas = conn.execute(query, params).fetchall()
    conn.close()
    return render_template("ventas.html", ventas=ventas, desde=fecha_desde, hasta=fecha_hasta)


@app.route("/ventas/<int:vid>")
@login_required
def venta_detalle(vid):
    conn = get_connection()
    venta = conn.execute(
        """SELECT v.*, u.NombreCompleto FROM Ventas v
           JOIN Usuarios u ON u.ID_Usuario=v.ID_Usuario WHERE v.ID_Venta=?""",
        (vid,),
    ).fetchone()
    detalles = conn.execute(
        """SELECT d.*, p.Nombre FROM DetalleVenta d
           JOIN Productos p ON p.ID_Producto = d.ID_Producto WHERE d.ID_Venta=?""",
        (vid,),
    ).fetchall()
    conn.close()
    if not venta:
        flash("Venta no encontrada.", "danger")
        return redirect(url_for("ventas_historial"))
    return render_template("venta_detalle.html", venta=venta, detalles=detalles)


@app.route("/ventas/<int:vid>/comprobante.pdf")
@login_required
def venta_comprobante_pdf(vid):
    from reports import generar_comprobante_pdf
    conn = get_connection()
    venta = conn.execute(
        """SELECT v.*, u.NombreCompleto FROM Ventas v
           JOIN Usuarios u ON u.ID_Usuario=v.ID_Usuario WHERE v.ID_Venta=?""",
        (vid,),
    ).fetchone()
    detalles = conn.execute(
        """SELECT d.*, p.Nombre FROM DetalleVenta d
           JOIN Productos p ON p.ID_Producto = d.ID_Producto WHERE d.ID_Venta=?""",
        (vid,),
    ).fetchall()
    conn.close()
    buffer = generar_comprobante_pdf(venta, detalles)
    return send_file(
        buffer, mimetype="application/pdf", as_attachment=True,
        download_name=f"comprobante_venta_{vid}.pdf",
    )


# ---------------------------------------------------------------------------
# Reportes gerenciales
# ---------------------------------------------------------------------------
@app.route("/reportes")
@login_required
def reportes():
    conn = get_connection()
    hoy = date.today().isoformat()
    resumen_hoy = conn.execute(
        "SELECT COUNT(*) c, COALESCE(SUM(Total),0) t FROM Ventas WHERE substr(FechaHora,1,10)=?",
        (hoy,),
    ).fetchone()
    top_productos = conn.execute(
        """SELECT p.Nombre, SUM(d.Cantidad) unidades, SUM(d.Subtotal) total
           FROM DetalleVenta d JOIN Productos p ON p.ID_Producto = d.ID_Producto
           GROUP BY d.ID_Producto ORDER BY unidades DESC LIMIT 5"""
    ).fetchall()
    conn.close()
    return render_template(
        "reportes.html", resumen_hoy=resumen_hoy, top_productos=top_productos, hoy=hoy
    )


@app.route("/reportes/inventario.pdf")
@login_required
def reporte_inventario_pdf():
    from reports import generar_reporte_inventario_pdf
    conn = get_connection()
    productos = conn.execute("SELECT * FROM Productos WHERE Activo=1 ORDER BY Nombre").fetchall()
    conn.close()
    buffer = generar_reporte_inventario_pdf(productos)
    return send_file(
        buffer, mimetype="application/pdf", as_attachment=True,
        download_name="reporte_inventario.pdf",
    )


@app.route("/reportes/ventas.pdf")
@login_required
def reporte_ventas_pdf():
    from reports import generar_reporte_ventas_pdf
    desde = request.args.get("desde", "")
    hasta = request.args.get("hasta", "")
    conn = get_connection()
    query = """SELECT v.*, u.NombreCompleto FROM Ventas v
               JOIN Usuarios u ON u.ID_Usuario = v.ID_Usuario WHERE 1=1"""
    params = []
    if desde:
        query += " AND date(v.FechaHora) >= date(?)"
        params.append(desde)
    if hasta:
        query += " AND date(v.FechaHora) <= date(?)"
        params.append(hasta)
    query += " ORDER BY v.ID_Venta"
    ventas = conn.execute(query, params).fetchall()
    conn.close()
    buffer = generar_reporte_ventas_pdf(ventas, desde, hasta)
    return send_file(
        buffer, mimetype="application/pdf", as_attachment=True,
        download_name="reporte_ventas.pdf",
    )


# ---------------------------------------------------------------------------
# Módulo: Usuarios y Seguridad (solo Admin)
# ---------------------------------------------------------------------------
@app.route("/usuarios")
@login_required
@admin_required
def usuarios_list():
    conn = get_connection()
    usuarios = conn.execute("SELECT * FROM Usuarios ORDER BY NombreCompleto").fetchall()
    conn.close()
    return render_template("usuarios.html", usuarios=usuarios)


@app.route("/usuarios/nuevo", methods=["GET", "POST"])
@login_required
@admin_required
def usuario_nuevo():
    if request.method == "POST":
        try:
            nombre = request.form["nombre"].strip()
            username = request.form["username"].strip()
            password = request.form["password"]
            rol = request.form["rol"]
            if not nombre or not username or not password:
                raise ValueError("Todos los campos son obligatorios.")
            if rol not in ("Admin", "Cajero"):
                raise ValueError("Rol inválido.")
            conn = get_connection()
            conn.execute(
                "INSERT INTO Usuarios (NombreCompleto, Username, Password_Hash, Rol) VALUES (?,?,?,?)",
                (nombre, username, generate_password_hash(password), rol),
            )
            conn.commit()
            conn.close()
            flash("Usuario creado correctamente.", "success")
            return redirect(url_for("usuarios_list"))
        except Exception as e:
            flash(f"Error: {e}", "danger")
    return render_template("usuario_form.html")


@app.route("/usuarios/<int:uid>/toggle", methods=["POST"])
@login_required
@admin_required
def usuario_toggle(uid):
    conn = get_connection()
    conn.execute("UPDATE Usuarios SET Activo = 1 - Activo WHERE ID_Usuario=?", (uid,))
    conn.commit()
    conn.close()
    return redirect(url_for("usuarios_list"))


# ---------------------------------------------------------------------------
# Módulo: Ajustes de cuenta (usuario, contraseña, contacto, tarjetas de pago)
# ---------------------------------------------------------------------------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TELEFONO_RE = re.compile(r"^[0-9+()\s-]{7,20}$")


@app.route("/ajustes")
@login_required
def ajustes():
    conn = get_connection()
    usuario = conn.execute(
        "SELECT * FROM Usuarios WHERE ID_Usuario=?", (session["user_id"],)
    ).fetchone()
    tarjetas = conn.execute(
        "SELECT * FROM TarjetasPago WHERE ID_Usuario=? ORDER BY Predeterminada DESC, ID_Tarjeta DESC",
        (session["user_id"],),
    ).fetchall()
    conn.close()
    return render_template("ajustes.html", usuario=usuario, tarjetas=tarjetas)


@app.route("/ajustes/perfil", methods=["POST"])
@login_required
def ajustes_perfil():
    """Permite cambiar el nombre de usuario y/o la contraseña (requiere la contraseña actual)."""
    nuevo_username = request.form.get("username", "").strip()
    password_actual = request.form.get("password_actual", "")
    nueva_password = request.form.get("nueva_password", "")
    confirmar_password = request.form.get("confirmar_password", "")

    conn = get_connection()
    usuario = conn.execute(
        "SELECT * FROM Usuarios WHERE ID_Usuario=?", (session["user_id"],)
    ).fetchone()

    if not usuario or not check_password_hash(usuario["Password_Hash"], password_actual):
        conn.close()
        flash("La contraseña actual no es correcta.", "danger")
        return redirect(url_for("ajustes", tab="cuenta"))

    try:
        if not nuevo_username:
            raise ValueError("El nombre de usuario no puede estar vacío.")

        if nuevo_username != usuario["Username"]:
            existe = conn.execute(
                "SELECT 1 FROM Usuarios WHERE Username=? AND ID_Usuario<>?",
                (nuevo_username, session["user_id"]),
            ).fetchone()
            if existe:
                raise ValueError("Ese nombre de usuario ya está en uso.")

        if nueva_password or confirmar_password:
            if len(nueva_password) < 6:
                raise ValueError("La nueva contraseña debe tener al menos 6 caracteres.")
            if nueva_password != confirmar_password:
                raise ValueError("La confirmación de contraseña no coincide.")
            conn.execute(
                "UPDATE Usuarios SET Username=?, Password_Hash=? WHERE ID_Usuario=?",
                (nuevo_username, generate_password_hash(nueva_password), session["user_id"]),
            )
        else:
            conn.execute(
                "UPDATE Usuarios SET Username=? WHERE ID_Usuario=?",
                (nuevo_username, session["user_id"]),
            )
        conn.commit()
        session["username"] = nuevo_username
        flash("Datos de acceso actualizados correctamente.", "success")
    except ValueError as e:
        flash(str(e), "danger")
    finally:
        conn.close()
    return redirect(url_for("ajustes", tab="cuenta"))


@app.route("/ajustes/contacto", methods=["POST"])
@login_required
def ajustes_contacto():
    """Vincula o actualiza el correo electrónico y/o número celular del usuario."""
    email = request.form.get("email", "").strip()
    telefono = request.form.get("telefono", "").strip()

    try:
        if email and not EMAIL_RE.match(email):
            raise ValueError("El correo electrónico no tiene un formato válido.")
        if telefono and not TELEFONO_RE.match(telefono):
            raise ValueError("El número celular no tiene un formato válido.")

        conn = get_connection()
        conn.execute(
            "UPDATE Usuarios SET Email=?, Telefono=? WHERE ID_Usuario=?",
            (email or None, telefono or None, session["user_id"]),
        )
        conn.commit()
        conn.close()
        flash("Datos de contacto actualizados correctamente.", "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("ajustes", tab="contacto"))


@app.route("/ajustes/tarjetas/agregar", methods=["POST"])
@login_required
def ajustes_tarjeta_agregar():
    """
    Registra una tarjeta de crédito/débito para usarla como método de pago en el POS.

    Por seguridad (norma PCI-DSS), el sistema NUNCA almacena el número completo
    ni el código de seguridad (CVV): solo se validan al momento del registro y
    se conservan la marca, los últimos 4 dígitos y la fecha de vencimiento.
    """
    titular = request.form.get("titular", "").strip()
    numero = re.sub(r"\D", "", request.form.get("numero", ""))
    cvv = request.form.get("cvv", "").strip()
    mes = request.form.get("mes_exp", "")
    anio = request.form.get("anio_exp", "")
    alias = request.form.get("alias", "").strip()

    try:
        if not titular:
            raise ValueError("El nombre del titular es obligatorio.")
        if not (13 <= len(numero) <= 19):
            raise ValueError("El número de tarjeta no es válido.")
        if not luhn_valido(numero):
            raise ValueError("El número de tarjeta no pasó la validación (dígito de control incorrecto).")
        if not re.match(r"^[0-9]{3,4}$", cvv):
            raise ValueError("El código de seguridad (CVV) no es válido.")
        mes, anio = int(mes), int(anio)
        if not (1 <= mes <= 12):
            raise ValueError("El mes de vencimiento no es válido.")
        hoy = date.today()
        if (anio, mes) < (hoy.year, hoy.month):
            raise ValueError("La tarjeta está vencida.")

        marca = detectar_marca(numero)
        ultimos4 = numero[-4:]

        conn = get_connection()
        ya_tiene = conn.execute(
            "SELECT COUNT(*) c FROM TarjetasPago WHERE ID_Usuario=?", (session["user_id"],)
        ).fetchone()["c"]
        conn.execute(
            """INSERT INTO TarjetasPago
               (ID_Usuario, Alias, Titular, Marca, Ultimos4, MesExp, AnioExp, Predeterminada, FechaRegistro)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                session["user_id"], alias or f"{marca} terminada en {ultimos4}", titular,
                marca, ultimos4, mes, anio, 1 if ya_tiene == 0 else 0,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        conn.commit()
        conn.close()
        flash(f"Tarjeta {marca} terminada en {ultimos4} agregada correctamente.", "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("ajustes", tab="tarjetas"))


@app.route("/ajustes/tarjetas/<int:tid>/eliminar", methods=["POST"])
@login_required
def ajustes_tarjeta_eliminar(tid):
    conn = get_connection()
    tarjeta = conn.execute(
        "SELECT * FROM TarjetasPago WHERE ID_Tarjeta=? AND ID_Usuario=?", (tid, session["user_id"])
    ).fetchone()
    if not tarjeta:
        conn.close()
        flash("Tarjeta no encontrada.", "danger")
        return redirect(url_for("ajustes", tab="tarjetas"))
    conn.execute("DELETE FROM TarjetasPago WHERE ID_Tarjeta=?", (tid,))
    if tarjeta["Predeterminada"]:
        siguiente = conn.execute(
            "SELECT ID_Tarjeta FROM TarjetasPago WHERE ID_Usuario=? ORDER BY ID_Tarjeta LIMIT 1",
            (session["user_id"],),
        ).fetchone()
        if siguiente:
            conn.execute(
                "UPDATE TarjetasPago SET Predeterminada=1 WHERE ID_Tarjeta=?", (siguiente["ID_Tarjeta"],)
            )
    conn.commit()
    conn.close()
    flash("Tarjeta eliminada.", "success")
    return redirect(url_for("ajustes", tab="tarjetas"))


@app.route("/ajustes/tarjetas/<int:tid>/predeterminada", methods=["POST"])
@login_required
def ajustes_tarjeta_predeterminada(tid):
    conn = get_connection()
    tarjeta = conn.execute(
        "SELECT * FROM TarjetasPago WHERE ID_Tarjeta=? AND ID_Usuario=?", (tid, session["user_id"])
    ).fetchone()
    if tarjeta:
        conn.execute("UPDATE TarjetasPago SET Predeterminada=0 WHERE ID_Usuario=?", (session["user_id"],))
        conn.execute("UPDATE TarjetasPago SET Predeterminada=1 WHERE ID_Tarjeta=?", (tid,))
        conn.commit()
        flash("Tarjeta predeterminada actualizada.", "success")
    conn.close()
    return redirect(url_for("ajustes", tab="tarjetas"))


# ---------------------------------------------------------------------------
# API auxiliar: tarjetas del usuario actual (usada por el POS)
# ---------------------------------------------------------------------------
@app.route("/api/tarjetas")
@login_required
def api_tarjetas():
    conn = get_connection()
    tarjetas = conn.execute(
        "SELECT * FROM TarjetasPago WHERE ID_Usuario=? ORDER BY Predeterminada DESC, ID_Tarjeta DESC",
        (session["user_id"],),
    ).fetchall()
    conn.close()
    return jsonify([
        {
            "id": t["ID_Tarjeta"],
            "alias": t["Alias"],
            "marca": t["Marca"],
            "ultimos4": t["Ultimos4"],
            "predeterminada": bool(t["Predeterminada"]),
        }
        for t in tarjetas
    ])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
