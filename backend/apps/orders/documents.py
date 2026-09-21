import io
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

INK = colors.HexColor("#14181F")
MUTED = colors.HexColor("#6B7280")
RULE = colors.HexColor("#D5D9DF")

LABEL_WIDTH = 100 * mm
LABEL_HEIGHT = 150 * mm


def _style(name, size=9, leading=12.5, bold=False, color=INK, align=None):
    style = ParagraphStyle(
        name,
        fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=size,
        leading=leading,
        textColor=color,
    )
    if align is not None:
        style.alignment = align
    return style


def _money(value):
    return f"Tk {Decimal(value or 0):,.2f}"


def build_invoice_pdf(order):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A5,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Invoice {order.order_number}",
    )

    store = order.store
    settings = getattr(store, "settings", None)
    width = A5[0] - 24 * mm

    story = []

    header = Table(
        [[
            Paragraph(store.name, _style("s", 15, 19, bold=True)),
            Paragraph(
                f"<b>INVOICE</b><br/>{order.order_number}",
                _style("i", 10, 14, align=TA_RIGHT),
            ),
        ]],
        colWidths=[width * 0.6, width * 0.4],
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.8, RULE),
    ]))
    story.append(header)
    story.append(Spacer(1, 8))

    contact = " · ".join(
        part for part in (store.contact_phone, store.district) if part
    )
    if settings and settings.invoice_header:
        story.append(Paragraph(settings.invoice_header, _style("h", 8.5, 12, color=MUTED)))
    if contact:
        story.append(Paragraph(contact, _style("c", 8.5, 12, color=MUTED)))
    story.append(Spacer(1, 10))

    meta = Table(
        [[
            Paragraph(
                "<b>Billed to</b><br/>"
                f"{order.recipient_name}<br/>"
                f"{order.recipient_phone}<br/>"
                f"{order.shipping_address}<br/>"
                f"{order.shipping_thana} {order.shipping_district}".strip(),
                _style("b", 8.5, 12.5),
            ),
            Paragraph(
                f"<b>Date</b> {order.created_at.strftime('%d %b %Y')}<br/>"
                f"<b>Status</b> {order.get_status_display()}<br/>"
                f"<b>Payment</b> {order.get_payment_status_display()}",
                _style("m", 8.5, 12.5, align=TA_RIGHT),
            ),
        ]],
        colWidths=[width * 0.58, width * 0.42],
    )
    meta.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(meta)
    story.append(Spacer(1, 12))

    rows = [[
        Paragraph("<b>Item</b>", _style("th", 8.5, 11, color=colors.white)),
        Paragraph("<b>Qty</b>", _style("th", 8.5, 11, color=colors.white, align=TA_CENTER)),
        Paragraph("<b>Price</b>", _style("th", 8.5, 11, color=colors.white, align=TA_RIGHT)),
        Paragraph("<b>Total</b>", _style("th", 8.5, 11, color=colors.white, align=TA_RIGHT)),
    ]]

    for item in order.items.all():
        name = item.product_name
        if item.variant_label:
            name = f"{name} ({item.variant_label})"
        rows.append([
            Paragraph(name, _style("n", 8.5, 12)),
            Paragraph(str(item.quantity), _style("q", 8.5, 12, align=TA_CENTER)),
            Paragraph(_money(item.unit_price), _style("p", 8.5, 12, align=TA_RIGHT)),
            Paragraph(_money(item.line_total), _style("t", 8.5, 12, align=TA_RIGHT)),
        ])

    items_table = Table(
        rows, colWidths=[width * 0.48, width * 0.12, width * 0.2, width * 0.2]
    )
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 10))

    totals = [["Subtotal", _money(order.subtotal)]]
    show_discount = not settings or settings.show_discount_on_invoice
    if order.discount_amount and show_discount:
        totals.append(["Discount", f"- {_money(order.discount_amount)}"])
    totals.append(["Delivery", _money(order.delivery_charge)])
    totals.append(["Total", _money(order.total_amount)])
    if order.advance_paid:
        totals.append(["Advance paid", f"- {_money(order.advance_paid)}"])
    totals.append(["Cash on delivery", _money(order.cod_amount)])

    totals_table = Table(
        [[
            Paragraph(label, _style("l", 9, 13, bold=(label == "Cash on delivery"))),
            Paragraph(
                value,
                _style("v", 9, 13, bold=(label == "Cash on delivery"), align=TA_RIGHT),
            ),
        ] for label, value in totals],
        colWidths=[width * 0.6, width * 0.4],
        hAlign="RIGHT",
    )
    totals_table.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, INK),
        ("TOPPADDING", (0, -1), (-1, -1), 6),
    ]))
    story.append(totals_table)

    if order.customer_note:
        story.append(Spacer(1, 10))
        story.append(
            Paragraph(
                f"<b>Note</b> {order.customer_note}",
                _style("cn", 8, 11, color=MUTED),
            )
        )

    if settings and settings.invoice_footer_note:
        story.append(Spacer(1, 12))
        story.append(
            Paragraph(settings.invoice_footer_note, _style("f", 8, 11, color=MUTED))
        )
    if settings and settings.invoice_terms:
        story.append(Spacer(1, 4))
        story.append(
            Paragraph(settings.invoice_terms, _style("tm", 7.5, 10, color=MUTED))
        )

    doc.build(story)
    buffer.seek(0)
    return buffer


def build_label_pdf(order, shipment=None):
    buffer = io.BytesIO()
    canvas = pdf_canvas.Canvas(buffer, pagesize=(LABEL_WIDTH, LABEL_HEIGHT))
    canvas.setTitle(f"Label {order.order_number}")

    margin = 6 * mm
    inner = LABEL_WIDTH - 2 * margin
    y = LABEL_HEIGHT - margin

    canvas.setFont("Helvetica-Bold", 13)
    canvas.drawString(margin, y - 10, order.store.name[:30])
    y -= 16

    canvas.setFont("Helvetica", 8)
    if order.store.contact_phone:
        canvas.drawString(margin, y - 8, order.store.contact_phone)
        y -= 12

    canvas.setLineWidth(1)
    canvas.line(margin, y - 4, margin + inner, y - 4)
    y -= 14

    canvas.setFont("Helvetica-Bold", 20)
    canvas.drawString(margin, y - 16, order.order_number)
    y -= 26

    if shipment is not None and shipment.consignment_id:
        canvas.setFont("Helvetica", 9)
        canvas.drawString(
            margin, y - 8,
            f"{shipment.courier_name}: {shipment.consignment_id}",
        )
        y -= 16

    canvas.setStrokeColor(RULE)
    canvas.line(margin, y - 2, margin + inner, y - 2)
    canvas.setStrokeColor(colors.black)
    y -= 14

    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(margin, y - 8, "DELIVER TO")
    y -= 16

    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(margin, y - 10, order.recipient_name[:32])
    y -= 16

    canvas.setFont("Helvetica-Bold", 13)
    canvas.drawString(margin, y - 10, order.recipient_phone)
    y -= 18

    canvas.setFont("Helvetica", 9.5)
    address_parts = [
        order.shipping_address,
        order.shipping_area,
        order.shipping_thana,
        order.shipping_district,
    ]
    address = ", ".join(part for part in address_parts if part)
    for line in _wrap(address, 44):
        canvas.drawString(margin, y - 8, line)
        y -= 12

    y -= 6
    canvas.setStrokeColor(RULE)
    canvas.line(margin, y, margin + inner, y)
    canvas.setStrokeColor(colors.black)
    y -= 18

    box_height = 20 * mm
    canvas.setLineWidth(1.5)
    canvas.rect(margin, y - box_height, inner, box_height)

    canvas.setFont("Helvetica", 9)
    canvas.drawCentredString(
        margin + inner / 2, y - 9 * mm, "COLLECT ON DELIVERY"
    )
    canvas.setFont("Helvetica-Bold", 20)
    canvas.drawCentredString(
        margin + inner / 2, y - 16 * mm, _money(order.cod_amount)
    )
    y -= box_height + 12

    canvas.setFont("Helvetica", 8)
    item_count = sum(item.quantity for item in order.items.all())
    canvas.drawString(margin, y, f"{item_count} item(s)")
    y -= 11

    for item in order.items.all()[:4]:
        label = f"- {item.product_name}"
        if item.variant_label:
            label += f" ({item.variant_label})"
        label += f" x{item.quantity}"
        canvas.drawString(margin, y, label[:52])
        y -= 10

    if order.customer_note:
        y -= 4
        canvas.setFont("Helvetica-Oblique", 7.5)
        for line in _wrap(f"Note: {order.customer_note}", 56)[:2]:
            canvas.drawString(margin, y, line)
            y -= 9

    canvas.showPage()
    canvas.save()
    buffer.seek(0)
    return buffer


def _wrap(text, width):
    if not text:
        return []
    words = str(text).split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines
