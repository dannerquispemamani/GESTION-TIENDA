# Gestión Comercial

Sistema de Gestión de Ventas e Inventario para Tiendas de Barrio y Minimarkets.
Implementación **funcional y ejecutable** del proyecto descrito en el informe
(Programación II), adaptada a **Python (Flask) + SQLite**, lo que permite correrlo
en cualquier sistema operativo sin depender de Windows/.NET, manteniendo la misma
arquitectura en capas (Presentación → Lógica de Negocio → Acceso a Datos → BD)
y el mismo modelo de base de datos relacional propuesto en el documento original.

## Funcionalidades implementadas

- **Login y roles** (Admin / Cajero) con contraseñas encriptadas (hash).
- **CRUD de productos** con categoría, precio de compra/venta, stock y stock mínimo.
- **Alertas automáticas de stock bajo** (dashboard + badge en el menú + reportes).
- **Punto de Venta (POS)**: carrito interactivo, cálculo automático de totales,
  cambio, validación de stock disponible y descuento automático de inventario.
- **Compras (reabastecimiento de inventario, solo Admin)**: interfaz tipo POS
  para registrar compras a proveedores; aumenta el stock automáticamente y
  actualiza el precio de costo del producto con el último precio pagado.
- **Historial de ventas y de compras**, ambos filtrables por fecha, con detalle
  de cada transacción.
- **Motor de reportes en PDF**: comprobante de venta, comprobante de compra,
  reporte de inventario y reporte de ventas por periodo (usando ReportLab).
- **Gestión de usuarios** (solo Admin): alta de usuarios, activar/desactivar,
  roles Admin/Cajero.
- **Ajustes de cuenta** (todos los usuarios): cambiar nombre de usuario y
  contraseña, vincular correo electrónico o número celular, y administrar
  tarjetas de crédito/débito (validación con algoritmo de Luhn, detección de
  marca y fecha de vencimiento; nunca se almacena el número completo ni el CVV).
- **Pago con tarjeta en el POS**: además de efectivo, se puede cobrar una venta
  seleccionando una tarjeta previamente registrada en Ajustes.
- Base de datos relacional normalizada: `Usuarios`, `Productos`, `Ventas`,
  `DetalleVenta`, `Compras`, `DetalleCompra`, `TarjetasPago`, tal como se
  definió en el diseño original (con las extensiones de Compras y Tarjetas).

## Instalación y ejecución

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. (Opcional) inicializar/reiniciar la base de datos con datos de ejemplo
python database.py

# 3. Ejecutar la aplicación
python app.py
```

Luego abre tu navegador en: **http://localhost:5000**

## Credenciales de acceso (demo)

| Usuario  | Contraseña | Rol           |
|----------|------------|---------------|
| admin    | admin123   | Administrador |
| cajero   | cajero123  | Cajero        |

## Estructura del proyecto

```
tiendacontrol/
├── app.py            # Rutas y lógica de negocio (BLL + UI/controlador)
├── database.py        # Acceso a datos (DAL) - esquema SQLite e inicialización
├── reports.py          # Motor de generación de reportes PDF
├── requirements.txt
├── templates/          # Vistas HTML (Jinja2)
└── static/css/          # Estilos
```

## Nota sobre el pago con tarjeta

El módulo de tarjetas es **totalmente funcional dentro del sistema**: valida el
número (algoritmo de Luhn), detecta la marca (Visa/Mastercard/Amex/Discover),
verifica la fecha de vencimiento y permite usarlas como método de pago en el
POS. Por seguridad (norma PCI-DSS) **nunca se guarda el número completo ni el
CVV**, solo la marca, los últimos 4 dígitos y el vencimiento.

Lo que este módulo **no hace** es procesar un cobro real contra un banco o
procesador de pagos: eso requiere integrar una pasarela de pago (Stripe,
PayPal, Culqi, etc.) con credenciales de una cuenta comercial real, algo que
debe contratarse por separado y configurarse con sus propias claves de API.

## Notas técnicas

- La base de datos se crea automáticamente (`tiendacontrol.db`) al ejecutar
  la aplicación por primera vez, con 2 usuarios y 6 productos de ejemplo.
- Para producción, cambia `app.secret_key` en `app.py` y usa un servidor WSGI
  como Gunicorn en vez del servidor de desarrollo de Flask.
- El diseño respeta la arquitectura en capas y el modelo entidad-relación del
  documento original; solo se sustituyó el stack .NET/C#/WPF por Python/Flask
  para que el proyecto sea inmediatamente ejecutable y verificable sin requerir
  Visual Studio ni Windows.
