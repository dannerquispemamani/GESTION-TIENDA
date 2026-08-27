"""
Gestión Comercial - Módulo de acceso a datos (DAL)
Base de datos: SQLite
"""
import sqlite3
import os
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tiendacontrol.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(reset=False):
    """Crea las tablas del sistema (script DDL) y un usuario admin por defecto."""
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = get_connection()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS Usuarios (
            ID_Usuario      INTEGER PRIMARY KEY AUTOINCREMENT,
            NombreCompleto  TEXT NOT NULL,
            Username        TEXT NOT NULL UNIQUE,
            Password_Hash   TEXT NOT NULL,
            Rol             TEXT NOT NULL CHECK (Rol IN ('Admin', 'Cajero')),
            Activo          INTEGER NOT NULL DEFAULT 1,
            Email           TEXT,
            Telefono        TEXT
        );

        CREATE TABLE IF NOT EXISTS TarjetasPago (
            ID_Tarjeta      INTEGER PRIMARY KEY AUTOINCREMENT,
            ID_Usuario      INTEGER NOT NULL,
            Alias           TEXT,
            Titular         TEXT NOT NULL,
            Marca           TEXT NOT NULL,
            Ultimos4        TEXT NOT NULL,
            MesExp          INTEGER NOT NULL,
            AnioExp         INTEGER NOT NULL,
            Predeterminada  INTEGER NOT NULL DEFAULT 0,
            FechaRegistro   TEXT NOT NULL,
            FOREIGN KEY (ID_Usuario) REFERENCES Usuarios (ID_Usuario)
        );

        CREATE TABLE IF NOT EXISTS Productos (
            ID_Producto     INTEGER PRIMARY KEY AUTOINCREMENT,
            Nombre          TEXT NOT NULL,
            Categoria       TEXT,
            Precio_Compra   REAL NOT NULL DEFAULT 0,
            Precio_Venta    REAL NOT NULL DEFAULT 0,
            Stock_Actual    INTEGER NOT NULL DEFAULT 0,
            Stock_Minimo    INTEGER NOT NULL DEFAULT 5,
            Activo          INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS Ventas (
            ID_Venta        INTEGER PRIMARY KEY AUTOINCREMENT,
            FechaHora       TEXT NOT NULL,
            Total           REAL NOT NULL,
            Monto_Pagado    REAL NOT NULL,
            Cambio          REAL NOT NULL,
            ID_Usuario      INTEGER NOT NULL,
            Metodo_Pago     TEXT NOT NULL DEFAULT 'Efectivo',
            Tarjeta_Info    TEXT,
            FOREIGN KEY (ID_Usuario) REFERENCES Usuarios (ID_Usuario)
        );

        CREATE TABLE IF NOT EXISTS DetalleVenta (
            ID_Detalle      INTEGER PRIMARY KEY AUTOINCREMENT,
            ID_Venta        INTEGER NOT NULL,
            ID_Producto     INTEGER NOT NULL,
            Cantidad        INTEGER NOT NULL,
            Precio_Unitario REAL NOT NULL,
            Subtotal        REAL NOT NULL,
            FOREIGN KEY (ID_Venta) REFERENCES Ventas (ID_Venta),
            FOREIGN KEY (ID_Producto) REFERENCES Productos (ID_Producto)
        );

        CREATE TABLE IF NOT EXISTS Compras (
            ID_Compra       INTEGER PRIMARY KEY AUTOINCREMENT,
            FechaHora       TEXT NOT NULL,
            Proveedor       TEXT,
            Total           REAL NOT NULL,
            ID_Usuario      INTEGER NOT NULL,
            FOREIGN KEY (ID_Usuario) REFERENCES Usuarios (ID_Usuario)
        );

        CREATE TABLE IF NOT EXISTS DetalleCompra (
            ID_Detalle      INTEGER PRIMARY KEY AUTOINCREMENT,
            ID_Compra       INTEGER NOT NULL,
            ID_Producto     INTEGER NOT NULL,
            Cantidad        INTEGER NOT NULL,
            Precio_Unitario REAL NOT NULL,
            Subtotal        REAL NOT NULL,
            FOREIGN KEY (ID_Compra) REFERENCES Compras (ID_Compra),
            FOREIGN KEY (ID_Producto) REFERENCES Productos (ID_Producto)
        );
        """
    )

    # Migración suave: agrega columnas nuevas a bases de datos ya existentes
    # (creadas por una versión anterior del sistema) sin perder datos.
    cols_usuarios = {row["name"] for row in cur.execute("PRAGMA table_info(Usuarios)")}
    if "Email" not in cols_usuarios:
        cur.execute("ALTER TABLE Usuarios ADD COLUMN Email TEXT")
    if "Telefono" not in cols_usuarios:
        cur.execute("ALTER TABLE Usuarios ADD COLUMN Telefono TEXT")

    cols_ventas = {row["name"] for row in cur.execute("PRAGMA table_info(Ventas)")}
    if "Metodo_Pago" not in cols_ventas:
        cur.execute("ALTER TABLE Ventas ADD COLUMN Metodo_Pago TEXT NOT NULL DEFAULT 'Efectivo'")
    if "Tarjeta_Info" not in cols_ventas:
        cur.execute("ALTER TABLE Ventas ADD COLUMN Tarjeta_Info TEXT")

    # Usuario administrador por defecto (solo si la tabla está vacía)
    cur.execute("SELECT COUNT(*) AS c FROM Usuarios")
    if cur.fetchone()["c"] == 0:
        cur.execute(
            "INSERT INTO Usuarios (NombreCompleto, Username, Password_Hash, Rol) VALUES (?,?,?,?)",
            ("Administrador", "admin", generate_password_hash("admin123"), "Admin"),
        )
        cur.execute(
            "INSERT INTO Usuarios (NombreCompleto, Username, Password_Hash, Rol) VALUES (?,?,?,?)",
            ("Cajero Demo", "cajero", generate_password_hash("cajero123"), "Cajero"),
        )

    # Productos de ejemplo (solo si la tabla está vacía)
    cur.execute("SELECT COUNT(*) AS c FROM Productos")
    if cur.fetchone()["c"] == 0:
        productos_demo = [
            ("Arroz 1kg", "Abarrotes", 5.50, 7.00, 40, 10),
            ("Aceite 1L", "Abarrotes", 9.00, 12.00, 25, 8),
            ("Coca Cola 2L", "Bebidas", 6.00, 8.50, 30, 10),
            ("Pan de molde", "Panadería", 4.00, 6.00, 15, 5),
            ("Leche 1L", "Lácteos", 4.50, 6.00, 8, 10),
            ("Detergente 1kg", "Limpieza", 7.00, 10.00, 3, 5),
        ]
        cur.executemany(
            """INSERT INTO Productos
               (Nombre, Categoria, Precio_Compra, Precio_Venta, Stock_Actual, Stock_Minimo)
               VALUES (?,?,?,?,?,?)""",
            productos_demo,
        )

    conn.commit()
    conn.close()


def luhn_valido(numero):
    """Valida un número de tarjeta con el algoritmo de Luhn (estándar de la industria)."""
    digitos = [int(d) for d in numero]
    total = 0
    for i, d in enumerate(reversed(digitos)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def detectar_marca(numero):
    """Detecta la marca de la tarjeta según su prefijo (IIN/BIN ranges públicos)."""
    if numero.startswith("4"):
        return "Visa"
    if numero[:2] in {"51", "52", "53", "54", "55"} or (
        len(numero) >= 4 and 2221 <= int(numero[:4]) <= 2720
    ):
        return "Mastercard"
    if numero[:2] in {"34", "37"}:
        return "American Express"
    if numero[:4] == "6011" or numero[:2] == "65":
        return "Discover"
    return "Tarjeta"


if __name__ == "__main__":
    init_db(reset=True)
    print(f"Base de datos inicializada en: {DB_PATH}")
