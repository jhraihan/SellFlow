import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle,
    KeepTogether, PageBreak, HRFlowable, Preformatted, ListFlowable, ListItem,
    NextPageTemplate, CondPageBreak,
)

HERE = Path(__file__).parent
SRC = HERE / "PRD.md"
OUT = HERE / "ShopFlow_BD_PRD.pdf"

INK      = colors.HexColor("#14181F")
BODY     = colors.HexColor("#2B313B")
MUTED    = colors.HexColor("#6B7280")
BRAND    = colors.HexColor("#0F766E")
BRAND_LT = colors.HexColor("#E6F2F1")
ACCENT   = colors.HexColor("#B45309")
RULE     = colors.HexColor("#DCE0E6")
ZEBRA    = colors.HexColor("#F7F8FA")
CODE_BG  = colors.HexColor("#F4F5F7")

PAGE_W, PAGE_H = A4
LM = RM = 20 * mm
TM = 20 * mm
BM = 18 * mm
CONTENT_W = PAGE_W - LM - RM

def S(name, **kw):
    kw.setdefault("fontName", "Helvetica")
    kw.setdefault("textColor", BODY)
    kw.setdefault("fontSize", 9.4)
    kw.setdefault("leading", 14.2)
    return ParagraphStyle(name, **kw)

ST = {
    "title":    S("title", fontName="Helvetica-Bold", fontSize=30, leading=35,
                  textColor=INK, alignment=TA_LEFT, spaceAfter=4),
    "subtitle": S("subtitle", fontSize=13.5, leading=19, textColor=BRAND,
                  fontName="Helvetica-Bold", spaceAfter=14),
    "h1":       S("h1", fontName="Helvetica-Bold", fontSize=17, leading=21,
                  textColor=INK, spaceBefore=6, spaceAfter=7, keepWithNext=1),
    "h2":       S("h2", fontName="Helvetica-Bold", fontSize=12.2, leading=16,
                  textColor=BRAND, spaceBefore=13, spaceAfter=5,
                  keepWithNext=1),
    "h3":       S("h3", fontName="Helvetica-Bold", fontSize=10.4, leading=14,
                  textColor=INK, spaceBefore=10, spaceAfter=4,
                  keepWithNext=1),
    "body":     S("body", spaceAfter=7),
    "bullet":   S("bullet", leftIndent=10, spaceAfter=3),
    "quote":    S("quote", fontName="Helvetica-Oblique", fontSize=9.6, leading=14.5,
                  textColor=INK, leftIndent=9, rightIndent=6,
                  spaceBefore=4, spaceAfter=9),
    "cell":     S("cell", fontSize=8.6, leading=12.1),
    "cellb":    S("cellb", fontSize=8.6, leading=12.1, fontName="Helvetica-Bold",
                  textColor=INK),
    "cellsm":   S("cellsm", fontSize=7.6, leading=10.4),
    "cellsmb":  S("cellsmb", fontSize=7.6, leading=10.4, fontName="Helvetica-Bold",
                  textColor=INK),
    "th":       S("th", fontSize=8.2, leading=11, fontName="Helvetica-Bold",
                  textColor=colors.white),
    "tag":      S("tag", fontSize=7.8, leading=10.5, fontName="Helvetica-Bold",
                  textColor=colors.white, alignment=TA_CENTER),
    "toc":      S("toc", fontSize=9.6, leading=17, textColor=BODY),
    "meta":     S("meta", fontSize=9, leading=13.5),
    "metab":    S("metab", fontSize=9, leading=13.5, fontName="Helvetica-Bold",
                  textColor=INK),
}

CODE = ParagraphStyle("code", fontName="Courier", fontSize=7.5, leading=10.2,
                      textColor=INK, leftIndent=6)

def inline(t):
    t = (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
          .replace("৳", "Tk "))
    t = re.sub(r"\*\*(.+?)\*\*", r'<b>\1</b>', t)
    t = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<i>\1</i>", t)
    t = re.sub(r"`(.+?)`", r'<font face="Courier" size="8.4">\1</font>', t)
    return t

def P(text, style="body"):
    return Paragraph(inline(text), ST[style])

def cell(text, style="cell"):
    return Paragraph(inline(text), ST[style])

def base_table_style(ncols, header=True, zebra_from=1):
    cmds = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
    ]
    if header:
        cmds += [
            ("BACKGROUND", (0, 0), (-1, 0), BRAND),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, BRAND),
            ("TOPPADDING", (0, 0), (-1, 0), 6),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ]
    for r in range(zebra_from, 400, 2):
        cmds.append(("ROWBACKGROUNDS", (0, zebra_from), (-1, -1),
                     [colors.white, ZEBRA]))
        break
    return TableStyle(cmds)

def mk_table(headers, rows, widths, small=False, repeat=1):
    cs, hs = ("cellsm", "th") if small else ("cell", "th")
    data = []
    if headers:
        data.append([Paragraph(inline(h), ST[hs]) for h in headers])
    for r in rows:
        data.append([c if hasattr(c, "wrap") else cell(str(c), cs) for c in r])
    t = Table(data, colWidths=widths, repeatRows=repeat if headers else 0,
              hAlign="LEFT")
    t.setStyle(base_table_style(len(widths), header=bool(headers)))
    return t

PRI_COLOR = {"P0": colors.HexColor("#B91C1C"),
             "P1": colors.HexColor("#B45309"),
             "P2": colors.HexColor("#4B5563")}

def pill(text, bg):
    t = Table([[Paragraph(text, ST["tag"])]], colWidths=[13 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t

PERM_HEAD = ["Capability", "Owner", "Manager", "Order", "Deliv.", "Acct."]
PERM_ROWS = [
    ("View orders",               "Y", "Y", "Y", "Y", "Y"),
    ("Create / edit orders",      "Y", "Y", "Y", "-", "-"),
    ("Confirm / cancel orders",   "Y", "Y", "Y", "-", "-"),
    ("Book shipments",            "Y", "Y", "Y", "-", "-"),
    ("Update shipment status",    "Y", "Y", "Y", "Y", "-"),
    ("Record returns",            "Y", "Y", "Y", "Y", "-"),
    ("View / edit products",      "Y", "Y", "View", "-", "-"),
    ("See cost price & margin",   "Y", "Y", "-", "-", "Y"),
    ("Manage customers",          "Y", "Y", "Y", "View", "View"),
    ("Export customer list",      "Y", "Y", "-", "-", "-"),
    ("Record payments",           "Y", "Y", "-", "-", "Y"),
    ("COD reconciliation",        "Y", "Y", "-", "-", "Y"),
    ("Manage expenses",           "Y", "Y", "-", "-", "Y"),
    ("View analytics & profit",    "Y", "Y", "-", "-", "Y"),
    ("Manage staff & roles",      "Y", "-", "-", "-", "-"),
    ("Courier credentials",       "Y", "-", "-", "-", "-"),
    ("Store settings",            "Y", "Y", "-", "-", "-"),
    ("Billing & plan",            "Y", "-", "-", "-", "-"),
    ("Delete store",              "Y", "-", "-", "-", "-"),
]

TRANS_HEAD = ["From", "Allowed next states"]
TRANS_ROWS = [
    ("Pending",          "Confirmed, Cancelled, On Hold"),
    ("Confirmed",        "Processing, Ready to Ship, Cancelled, On Hold"),
    ("Processing",       "Ready to Ship, Cancelled, On Hold"),
    ("Ready to Ship",    "Shipped, Cancelled, On Hold"),
    ("Shipped",          "Out for Delivery, Delivered, Returned"),
    ("Out for Delivery", "Delivered, Returned, Shipped (re-attempt)"),
    ("Delivered",        "Returned (post-delivery return window)"),
    ("On Hold",          "Pending, Confirmed, Cancelled"),
    ("Cancelled",        "terminal"),
    ("Returned",         "terminal"),
]

EP_HEAD = ["Method & path", "Purpose"]
EP_GROUPS = [
    ("Authentication", [
        ("POST   /auth/register/",               "Create user account"),
        ("POST   /auth/login/",                  "Obtain access + refresh tokens"),
        ("POST   /auth/refresh/",                "Rotate access token"),
        ("POST   /auth/logout/",                 "Blacklist refresh token"),
        ("POST   /auth/password/reset/",         "Request reset email"),
        ("GET    /auth/me/",                     "Current user + memberships"),
    ]),
    ("Stores & staff", [
        ("GET|POST   /stores/",                  "List own stores / create store"),
        ("GET|PATCH  /stores/{id}/",             "Store profile"),
        ("GET|PATCH  /stores/{id}/settings/",    "Delivery charges, invoice, SMS"),
        ("GET|POST   /stores/{id}/staff/",       "List / invite staff"),
        ("PATCH|DEL  /stores/{id}/staff/{uid}/", "Change role / revoke access"),
    ]),
    ("Catalog", [
        ("GET|POST   /categories/",              "Categories"),
        ("GET|POST   /products/",                "List (filter, search) / create"),
        ("GET|PATCH|DEL /products/{id}/",        "Product detail"),
        ("POST   /products/{id}/variants/",      "Add variant"),
        ("POST   /products/import/",             "CSV import (dry-run + commit)"),
        ("GET    /products/export/",             "CSV export"),
        ("GET    /stock/",                       "Stock levels, low-stock filter"),
        ("POST   /stock/adjust/",                "Manual adjustment with reason"),
        ("GET    /stock/movements/",             "Immutable stock ledger"),
    ]),
    ("Customers", [
        ("GET|POST   /customers/",               "List / create"),
        ("GET|PATCH  /customers/{id}/",          "Detail + metrics + risk"),
        ("GET    /customers/lookup/?phone=",     "Autofill during order entry"),
        ("GET    /customers/{id}/orders/",       "Order history"),
        ("POST   /customers/{id}/blacklist/",    "Blacklist / un-blacklist"),
    ]),
    ("Orders", [
        ("GET|POST   /orders/",                  "List (filters, search) / create"),
        ("GET|PATCH  /orders/{id}/",             "Detail / edit (pre-ship only)"),
        ("PATCH  /orders/{id}/status/",          "Transition status (state machine)"),
        ("POST   /orders/{id}/confirm/",         "Log call outcome + confirm"),
        ("POST   /orders/{id}/cancel/",          "Cancel with reason"),
        ("GET    /orders/{id}/history/",         "Status timeline"),
        ("GET    /orders/{id}/invoice/",         "Invoice PDF"),
        ("GET    /orders/{id}/label/",           "Parcel label PDF"),
        ("POST   /orders/bulk-status/",          "Bulk transition"),
        ("POST   /orders/check-duplicate/",      "Duplicate-order warning"),
    ]),
    ("Couriers & shipments", [
        ("GET    /couriers/",                    "Available couriers"),
        ("GET|POST   /store-couriers/",          "Enable courier, store credentials"),
        ("POST   /shipments/",                   "Book parcel (API or manual)"),
        ("GET    /shipments/",                   "List with COD / status filters"),
        ("GET    /shipments/{id}/",              "Detail + tracking history"),
        ("POST   /shipments/{id}/sync/",         "Force tracking refresh"),
        ("POST   /shipments/{id}/cancel/",       "Cancel with courier"),
        ("POST   /shipments/bulk-book/",         "Bulk booking + per-order report"),
        ("POST   /shipments/quote/",             "Delivery price quote"),
        ("POST   /webhooks/courier/{code}/",     "Courier status webhook (signed)"),
    ]),
    ("Payments & COD", [
        ("GET|POST   /payments/",                "Payment records"),
        ("GET    /payments/cod-ledger/",         "In transit / unsettled / overdue"),
        ("POST   /settlements/",                 "Upload courier statement"),
        ("GET    /settlements/{id}/preview/",    "Matched / unmatched / mismatch"),
        ("POST   /settlements/{id}/commit/",     "Commit reconciliation"),
    ]),
    ("Returns & expenses", [
        ("GET|POST   /returns/",                 "List / create return"),
        ("PATCH  /returns/{id}/",                "Update / resolve"),
        ("POST   /returns/{id}/restock/",        "Restock or write off items"),
        ("GET|POST   /expenses/",                "Expense records"),
    ]),
    ("Analytics", [
        ("GET    /analytics/dashboard/",         "KPI row + widgets (cached)"),
        ("GET    /analytics/sales/",             "Sales & profit by period"),
        ("GET    /analytics/products/",          "Product performance"),
        ("GET    /analytics/couriers/",          "Courier performance"),
        ("GET    /analytics/districts/",         "District performance"),
        ("GET    /analytics/returns/",           "Return analysis"),
        ("GET    /analytics/export/",            "CSV / Excel export"),
    ]),
    ("Public (unauthenticated)", [
        ("GET    /public/track/?code=&phone=",   "Customer order tracking"),
        ("POST   /public/stores/{slug}/orders/", "Public order form submission"),
    ]),
]

def parse(md):
    out = []
    lines = md.split("\n")
    i = 0
    meta = []
    buf = []
    bullets = []

    def flush_bullets():
        nonlocal bullets
        if bullets:
            out.append(ListFlowable(
                [ListItem(P(b, "bullet"), leftIndent=13, value="circle")
                 for b in bullets],
                bulletType="bullet", start="circle", bulletFontSize=6,
                leftIndent=13, bulletColor=BRAND, spaceAfter=7))
            bullets = []

    def flush_typed():
        nonlocal buf
        if not buf:
            return
        tag = buf[0][0]
        rows = [p for _, p in buf]
        buf = []
        out.append(render_typed(tag, rows))

    while i < len(lines):
        ln = lines[i]
        s = ln.strip()

        if s.startswith("```"):
            flush_bullets(); flush_typed()
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i].rstrip())
                i += 1
            i += 1
            out.append(code_block(code))
            continue

        m = re.match(r"^([A-Z]+)\|(.*)$", s)
        if m:
            flush_bullets()
            tag, rest = m.group(1), m.group(2)
            parts = [p.strip() for p in rest.split("|")]
            if buf and buf[0][0] != tag:
                flush_typed()
            if tag == "META":
                meta.append(parts)
            else:
                buf.append((tag, parts))
            i += 1
            continue

        flush_typed()

        if s == "PERMTABLE":
            flush_bullets()
            out.append(perm_table()); i += 1; continue
        if s == "TRANSITIONS":
            flush_bullets()
            out.append(mk_table(TRANS_HEAD, [(cell(a, "cellb"), cell(b))
                                             for a, b in TRANS_ROWS],
                                [38 * mm, CONTENT_W - 38 * mm]))
            out.append(Spacer(1, 9)); i += 1; continue
        if s == "ENDPOINTS":
            flush_bullets()
            out.extend(endpoint_tables()); i += 1; continue

        if s.startswith("### "):
            flush_bullets(); out.append(P(s[4:], "h3")); i += 1; continue
        if s.startswith("## "):
            flush_bullets(); out.append(P(s[3:], "h2")); i += 1; continue
        if s.startswith("# "):
            flush_bullets()
            title = s[2:]
            if re.match(r"^\d+\.", title) or title.startswith("Appendix"):
                out.append(SectionHead(title))
            else:
                out.append(P(title, "h1"))
            i += 1; continue
        if s.startswith("> "):
            flush_bullets(); out.append(callout(s[2:])); i += 1; continue
        if s == "---":
            i += 1; continue
        if re.match(r"^\d+\.\s", s):
            flush_bullets()
            out.append(Paragraph(inline(s), ST["bullet"])); i += 1; continue
        if s.startswith("- "):
            bullets.append(s[2:]); i += 1; continue
        if not s:
            flush_bullets(); i += 1; continue

        flush_bullets()
        out.append(P(s, "body"))
        i += 1

    flush_bullets(); flush_typed()
    return bind_headings(out), meta


def _measure(flow, avail):
    if isinstance(flow, KeepTogether):
        total = 0
        for c in flow._content:
            total += _measure(c, avail)
        return total
    try:
        return flow.wrap(CONTENT_W, avail)[1]
    except Exception:
        return 0


def bind_headings(flows):
    AVAIL = PAGE_H - TM - BM
    res = []
    for i, f in enumerate(flows):
        style_name = getattr(getattr(f, "style", None), "name", "")
        is_head = isinstance(f, SectionHead) or (
            isinstance(f, Paragraph) and style_name in ("h1", "h2", "h3"))
        if is_head and i + 1 < len(flows):
            nxt = flows[i + 1]
            h = _measure(nxt, AVAIL)
            head_h = 26 * mm if isinstance(f, SectionHead) else 18 * mm
            chunk = h if isinstance(nxt, KeepTogether) else min(h, 45 * mm)
            res.append(CondPageBreak(min(head_h + chunk, AVAIL * 0.85)))
        res.append(f)
    return res


class SectionHead(Paragraph):
    def __init__(self, text):
        super().__init__(inline(text), ST["h1"])

def code_block(lines):
    txt = "\n".join(lines) if lines else " "
    pre = Preformatted(txt, CODE)
    t = Table([[pre]], colWidths=[CONTENT_W], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CODE_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return KeepTogether([t, Spacer(1, 9)]) if len(lines) < 26 else t

def callout(text):
    t = Table([[P(text, "quote")]], colWidths=[CONTENT_W], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BRAND_LT),
        ("LINEBEFORE", (0, 0), (0, -1), 2.6, BRAND),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return KeepTogether([t, Spacer(1, 9)])

def perm_table():
    w = [CONTENT_W - 5 * 17 * mm] + [17 * mm] * 5
    rows = []
    for r in PERM_ROWS:
        cs = [cell(r[0], "cellsmb")]
        for v in r[1:]:
            col = BRAND if v == "Y" else (MUTED if v == "-" else ACCENT)
            sym = "Yes" if v == "Y" else ("—" if v == "-" else v)
            cs.append(Paragraph(
                f"<b>{sym}</b>",
                ParagraphStyle("c", parent=ST["cellsm"],
                               alignment=TA_CENTER, textColor=col)))
        rows.append(cs)
    t = mk_table(PERM_HEAD, rows, w, small=True)
    return KeepTogether([t, Spacer(1, 9)]) if False else t

def endpoint_tables():
    out = []
    mono = ParagraphStyle("m", parent=ST["cellsm"], fontName="Courier",
                          fontSize=7.2, leading=10, textColor=INK)
    verb = ParagraphStyle("v", parent=mono, fontName="Courier-Bold",
                          textColor=BRAND)
    for group, eps in EP_GROUPS:
        rows = []
        for a, b in eps:
            m, _, path = a.partition(" ")
            rows.append((Paragraph(inline(m), verb),
                         Paragraph(inline(path.strip()), mono),
                         cell(b, "cellsm")))
        t = mk_table([group, "", "Purpose"], rows,
                     [17 * mm, 61 * mm, CONTENT_W - 78 * mm], small=True)
        out.append(t)
        out.append(Spacer(1, 8))
    return out

def two_col(rows, w1, styles=("cellb", "cell"), headers=None, small=False):
    data = [(cell(a, styles[0]), cell(b, styles[1])) for a, b in rows]
    return mk_table(headers, data, [w1, CONTENT_W - w1], small=small)

def render_typed(tag, rows):
    sp = Spacer(1, 9)

    if tag == "PAIN":
        return KeepTogether([two_col([(r[0], r[1]) for r in rows], 44 * mm,
                                     headers=["Pain point", "Impact"]), sp])
    if tag == "GOAL":
        data = [(pill(r[0], BRAND), cell(r[1])) for r in rows]
        return KeepTogether([mk_table(["", "Goal"], data,
                                      [16 * mm, CONTENT_W - 16 * mm]), sp])
    if tag == "NONGOAL":
        return KeepTogether([two_col([(r[0], r[1]) for r in rows], 44 * mm,
                                     headers=["Not in v1", "Rationale"]), sp])
    if tag == "METRIC":
        data = [(cell(r[0], "cellb"), cell(r[1]), cell(r[2], "cellb"))
                for r in rows]
        t = mk_table(["Area", "Metric", "Target"], data,
                     [26 * mm, CONTENT_W - 26 * mm - 30 * mm, 30 * mm])
        return KeepTogether([t, sp])
    if tag == "ROLEDEF":
        return KeepTogether([two_col([(r[0], r[1]) for r in rows], 32 * mm,
                                     headers=["Role", "Scope"]), sp])
    if tag == "REQ":
        data = []
        for r in rows:
            data.append((cell(r[0], "cellsmb"),
                         pill(r[1], PRI_COLOR.get(r[1], MUTED)),
                         cell(r[2], "cellsm")))
        t = mk_table(["ID", "Pri", "Requirement"], data,
                     [17 * mm, 14 * mm, CONTENT_W - 31 * mm], small=True)
        return t
    if tag in ("STATUS", "SIDEEFFECT"):
        head = ["Status", "Meaning"] if tag == "STATUS" else ["Transition", "Side effect"]
        return KeepTogether([two_col([(r[0], r[1]) for r in rows], 34 * mm,
                                     headers=head), sp])
    if tag == "ENTITY":
        data = [(cell(r[0], "cellsmb"), cell(r[1], "cellsm")) for r in rows]
        return mk_table(["Entity", "Fields & notes"], data,
                        [34 * mm, CONTENT_W - 34 * mm], small=True)
    if tag == "RELATION":
        return KeepTogether([two_col([(r[0], r[1]) for r in rows], 62 * mm,
                                     headers=["Relationship", "Rule"],
                                     small=True), sp])
    if tag == "INTEGRITY":
        return KeepTogether([mk_table(["Data integrity rule"],
                                      [(cell(r[0]),) for r in rows],
                                      [CONTENT_W]), sp])
    if tag in ("CONV", "STACK", "TECH", "UX", "ROUTE", "NFR", "PHASE"):
        heads = {
            "CONV":  ["Convention", "Rule"],
            "STACK": ["Layer", "Choice"],
            "TECH":  ["Layer", "Technology & rationale"],
            "UX":    ["Principle", "Requirement"],
            "ROUTE": ["Route", "Contents"],
            "NFR":   ["Requirement", "Target"],
            "PHASE": ["", ""],
        }[tag]
        w = {"CONV": 32, "STACK": 28, "TECH": 28, "UX": 42,
             "ROUTE": 62, "NFR": 30, "PHASE": 26}[tag] * mm
        hdr = None if tag == "PHASE" else heads
        t = two_col([(r[0], r[1]) for r in rows], w, headers=hdr,
                    small=tag in ("ROUTE", "ENTITY"))
        return KeepTogether([t, sp]) if len(rows) <= 6 else t
    if tag == "JOB":
        data = [(cell(r[0], "cellsmb"), cell(r[1], "cellsm"), cell(r[2], "cellsm"))
                for r in rows]
        t = mk_table(["Task", "Cadence", "Responsibility"], data,
                     [46 * mm, 22 * mm, CONTENT_W - 68 * mm], small=True)
        return KeepTogether([t, sp])
    if tag == "RISK":
        sev = {"Critical": colors.HexColor("#991B1B"),
               "High": colors.HexColor("#B45309"),
               "Medium": colors.HexColor("#4B5563")}
        data = [(cell(r[0], "cellsm"), pill(r[1], sev.get(r[1], MUTED)),
                 cell(r[2], "cellsm")) for r in rows]
        return mk_table(["Risk", "Sev.", "Mitigation"], data,
                        [56 * mm, 16 * mm, CONTENT_W - 72 * mm], small=True)
    if tag == "QUESTION":
        items = [ListItem(P(r[0], "bullet"), leftIndent=13, value="circle")
                 for r in rows]
        return ListFlowable(items, bulletType="bullet", start="circle",
                            bulletFontSize=6, leftIndent=13,
                            bulletColor=ACCENT, spaceAfter=9)
    if tag == "GLOSSARY":
        return two_col([(r[0], r[1]) for r in rows], 34 * mm,
                       headers=["Term", "Definition"])
    return two_col([(r[0], " — ".join(r[1:])) for r in rows], 40 * mm)

def cover(meta, title, subtitle):
    f = []
    f.append(Spacer(1, 42 * mm))
    band = Table([[Paragraph(
        '<font color="white" size="8.5"><b>PRODUCT REQUIREMENTS DOCUMENT</b></font>',
        ST["meta"])]], colWidths=[72 * mm], hAlign="LEFT")
    band.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BRAND),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    f.append(band)
    f.append(Spacer(1, 11 * mm))
    name, _, tagline = subtitle.partition(" — ")
    f.append(Paragraph(inline(name), ST["title"]))
    f.append(Spacer(1, 2))
    f.append(Paragraph(inline(tagline or title), ST["subtitle"]))
    f.append(HRFlowable(width="100%", thickness=1.1, color=RULE,
                        spaceBefore=6, spaceAfter=12))
    f.append(Paragraph(
        inline("A multi-tenant SaaS platform that turns Facebook and Instagram "
               "order chatter into a controlled order-to-cash pipeline: "
               "confirmation, inventory, courier booking, delivery tracking, "
               "COD reconciliation, returns, and true net profit."),
        S("lede", fontSize=10.6, leading=16.5, textColor=BODY)))
    f.append(Spacer(1, 14 * mm))
    rows = [(cell(k, "metab"), cell(v, "meta")) for k, v in
            [(m[0], m[1]) for m in meta]]
    t = Table(rows, colWidths=[34 * mm, CONTENT_W - 34 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
    ]))
    f.append(t)
    f.append(NextPageTemplate("main"))
    f.append(PageBreak())
    return f

TOC_ITEMS = [
    "1. Executive Summary", "2. Problem Statement", "3. Goals & Non-Goals",
    "4. Success Metrics", "5. Personas", "6. Roles & Permissions",
    "7. Functional Requirements", "8. Order Lifecycle", "9. Data Model",
    "10. API Design", "11. Frontend Specification",
    "12. Technical Architecture", "13. Release Plan",
    "14. Risks & Mitigations", "15. Open Questions",
    "Appendix A — Profit Calculation", "Appendix B — Glossary",
]

def toc():
    f = [Paragraph("Contents", ST["h1"]),
         HRFlowable(width="100%", thickness=1.1, color=BRAND,
                    spaceBefore=2, spaceAfter=10)]
    for it in TOC_ITEMS:
        f.append(Paragraph(inline(it), ST["toc"]))
    f.append(PageBreak())
    return f

class PRDDoc(BaseDocTemplate):
    def __init__(self, path, **kw):
        super().__init__(path, pagesize=A4, leftMargin=LM, rightMargin=RM,
                         topMargin=TM, bottomMargin=BM,
                         title="ShopFlow BD — Product Requirements Document",
                         author="Jahid H. R.",
                         subject="F-commerce Order & Delivery Management Platform",
                         **kw)
        frame = Frame(LM, BM, CONTENT_W, PAGE_H - TM - BM, id="body",
                      leftPadding=0, rightPadding=0,
                      topPadding=0, bottomPadding=0)
        self.addPageTemplates([
            PageTemplate(id="cover", frames=[frame], onPage=self.cover_page),
            PageTemplate(id="main", frames=[frame], onPage=self.main_page),
        ])
        self.section = ""

    def afterFlowable(self, flowable):
        if isinstance(flowable, SectionHead):
            import html as _html
            self.section = _html.unescape(re.sub(r"<[^>]+>", "", flowable.text))

    def cover_page(self, canv, doc):
        canv.saveState()
        canv.setFillColor(BRAND)
        canv.rect(0, PAGE_H - 12 * mm, PAGE_W, 12 * mm, stroke=0, fill=1)
        canv.setFillColor(ACCENT)
        canv.rect(0, PAGE_H - 12 * mm, 46 * mm, 12 * mm, stroke=0, fill=1)
        canv.setFillColor(BRAND)
        canv.rect(0, 0, PAGE_W, 5 * mm, stroke=0, fill=1)
        canv.restoreState()

    def main_page(self, canv, doc):
        canv.saveState()
        canv.setFillColor(MUTED)
        canv.setFont("Helvetica", 7.6)
        canv.drawString(LM, PAGE_H - 13 * mm, "ShopFlow BD  ·  PRD v1.0")
        sec = self.section[:62]
        canv.drawRightString(PAGE_W - RM, PAGE_H - 13 * mm, sec)
        canv.setStrokeColor(RULE)
        canv.setLineWidth(0.5)
        canv.line(LM, PAGE_H - 15 * mm, PAGE_W - RM, PAGE_H - 15 * mm)
        canv.line(LM, BM - 5 * mm, PAGE_W - RM, BM - 5 * mm)
        canv.setFont("Helvetica", 7.6)
        canv.drawString(LM, BM - 9.5 * mm, "Confidential draft")
        canv.setFillColor(BRAND)
        canv.setFont("Helvetica-Bold", 8)
        canv.drawRightString(PAGE_W - RM, BM - 9.5 * mm, str(doc.page - 1))
        canv.restoreState()


def main():
    md = SRC.read_text(encoding="utf-8")
    body_lines = md.split("\n")
    title = body_lines[0].replace("# ", "").strip()
    subtitle = next(l for l in body_lines if l.startswith("## ")).replace("## ", "")
    md_body = "\n".join(l for l in body_lines
                        if not (l.startswith("# Product Requirements")
                                or l.startswith("## ShopFlow BD")))
    flows, meta = parse(md_body)

    doc = PRDDoc(str(OUT))
    story = cover(meta, title, subtitle)
    story += toc()
    story += flows
    doc.multiBuild(story)
    print(f"OK -> {OUT}  ({OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
