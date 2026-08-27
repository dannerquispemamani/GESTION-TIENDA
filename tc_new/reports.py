"""
Gestión Comercial - Motor de Reportes PDF
Genera comprobantes de venta y reportes gerenciales usando ReportLab.
"""
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TituloTC", fontSize=16, spaceAfter=6, textColor=colors.HexColor("#1a4d2e")))
    styles.add(ParagraphStyle(name="SubTC", fontSize=10, textColor=colors.grey, spaceAfter=12))
    styles.add(ParagraphStyle(name="FirmaTC", fontSize=8, textColor=colors.grey))
    return styles


def _pie_firma(canvas, doc):
    """Pie de página con la firma corporativa, dibujado en cada página del PDF."""
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawCentredString(
        doc.pagesize[0] / 2, 1.2 * cm,
        "Gestión Comercial — Sistema de Ventas e Inventario"
    )
    canvas.restoreState()


def generar_comprobante_pdf(venta, detalles):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=1.5 * cm)
    styles = _styles()
    elems = [
        Paragraph("Gestión Comercial", styles["TituloTC"]),
        Paragraph(f"Comprobante de Venta N.º {venta['ID_Venta']}", styles["SubTC"]),
        Paragraph(f"Fecha: {venta['FechaHora']}", styles["Normal"]),
        Paragraph(f"Atendido por: {venta['NombreCompleto']}", styles["Normal"]),
        Spacer(1, 0.5 * cm),
    ]

    data = [["Producto", "Cantidad", "P. Unitario", "Subtotal"]]
    for d in detalles:
        data.append([
            d["Nombre"], str(d["Cantidad"]),
            f"Bs {d['Precio_Unitario']:.2f}", f"Bs {d['Subtotal']:.2f}",
        ])
    tabla = Table(data, colWidths=[7 * cm, 2.5 * cm, 3 * cm, 3 * cm])
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a4d2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ]))
    elems.append(tabla)
    elems.append(Spacer(1, 0.7 * cm))
    elems.append(Paragraph(f"<b>Total: Bs {venta['Total']:.2f}</b>", styles["Normal"]))
    elems.append(Paragraph(f"Monto pagado: Bs {venta['Monto_Pagado']:.2f}", styles["Normal"]))
    elems.append(Paragraph(f"Cambio: Bs {venta['Cambio']:.2f}", styles["Normal"]))

    doc.build(elems, onFirstPage=_pie_firma, onLaterPages=_pie_firma)
    buffer.seek(0)
    return buffer


def generar_comprobante_compra_pdf(compra, detalles):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=1.5 * cm)
    styles = _styles()
    elems = [
        Paragraph("Gestión Comercial", styles["TituloTC"]),
        Paragraph(f"Comprobante de Compra N.º {compra['ID_Compra']}", styles["SubTC"]),
        Paragraph(f"Fecha: {compra['FechaHora']}", styles["Normal"]),
        Paragraph(f"Registrado por: {compra['NombreCompleto']}", styles["Normal"]),
    ]
    if compra["Proveedor"]:
        elems.append(Paragraph(f"Proveedor: {compra['Proveedor']}", styles["Normal"]))
    elems.append(Spacer(1, 0.5 * cm))

    data = [["Producto", "Cantidad", "P. Unitario", "Subtotal"]]
    for d in detalles:
        data.append([
            d["Nombre"], str(d["Cantidad"]),
            f"Bs {d['Precio_Unitario']:.2f}", f"Bs {d['Subtotal']:.2f}",
        ])
    tabla = Table(data, colWidths=[7 * cm, 2.5 * cm, 3 * cm, 3 * cm])
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a4d2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ]))
    elems.append(tabla)
    elems.append(Spacer(1, 0.7 * cm))
    elems.append(Paragraph(f"<b>Total de la compra: Bs {compra['Total']:.2f}</b>", styles["Normal"]))

    doc.build(elems, onFirstPage=_pie_firma, onLaterPages=_pie_firma)
    buffer.seek(0)
    return buffer


def generar_reporte_inventario_pdf(productos):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=1.5 * cm)
    styles = _styles()
    elems = [
        Paragraph("Gestión Comercial", styles["TituloTC"]),
        Paragraph("Reporte de Inventario Actual", styles["SubTC"]),
    ]

    data = [["Producto", "Categoría", "P. Compra", "P. Venta", "Stock", "Mínimo"]]
    total_valor = 0
    for p in productos:
        valor = p["Stock_Actual"] * p["Precio_Venta"]
        total_valor += valor
        alerta = p["Stock_Actual"] <= p["Stock_Minimo"]
        fila = [
            p["Nombre"], p["Categoria"] or "-",
            f"Bs {p['Precio_Compra']:.2f}", f"Bs {p['Precio_Venta']:.2f}",
            f"{p['Stock_Actual']}" + (" ⚠" if alerta else ""), str(p["Stock_Minimo"]),
        ]
        data.append(fila)

    tabla = Table(data, colWidths=[5.5 * cm, 3 * cm, 2.3 * cm, 2.3 * cm, 2 * cm, 2 * cm])
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a4d2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
    ]
    for i, p in enumerate(productos, start=1):
        if p["Stock_Actual"] <= p["Stock_Minimo"]:
            style_cmds.append(("TEXTCOLOR", (0, i), (-1, i), colors.red))
    tabla.setStyle(TableStyle(style_cmds))
    elems.append(tabla)
    elems.append(Spacer(1, 0.7 * cm))
    elems.append(Paragraph(f"<b>Valor total del inventario: Bs {total_valor:.2f}</b>", styles["Normal"]))

    doc.build(elems, onFirstPage=_pie_firma, onLaterPages=_pie_firma)
    buffer.seek(0)
    return buffer


def generar_reporte_ventas_pdf(ventas, desde, hasta):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=1.5 * cm)
    styles = _styles()
    periodo = f"{desde or 'inicio'} a {hasta or 'hoy'}"
    elems = [
        Paragraph("Gestión Comercial", styles["TituloTC"]),
        Paragraph(f"Reporte de Ventas — Periodo: {periodo}", styles["SubTC"]),
    ]

    data = [["N.º Venta", "Fecha", "Cajero", "Total"]]
    total_general = 0
    for v in ventas:
        total_general += v["Total"]
        data.append([str(v["ID_Venta"]), v["FechaHora"], v["NombreCompleto"], f"Bs {v['Total']:.2f}"])

    tabla = Table(data, colWidths=[3 * cm, 4.5 * cm, 5 * cm, 3 * cm])
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a4d2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (3, 0), (3, -1), "RIGHT"),
    ]))
    elems.append(tabla)
    elems.append(Spacer(1, 0.7 * cm))
    elems.append(Paragraph(f"<b>Total del periodo: Bs {total_general:.2f}</b>", styles["Normal"]))
    elems.append(Paragraph(f"Cantidad de ventas: {len(ventas)}", styles["Normal"]))

    doc.build(elems, onFirstPage=_pie_firma, onLaterPages=_pie_firma)
    buffer.seek(0)
    return buffer
