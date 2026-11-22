"""Excel (openpyxl) and PDF (reportlab) export of any report dict."""
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _period(rep):
    if not rep.get("dated", True):
        return "As on today"
    f = "-".join(reversed(rep["from"].split("-")))
    t = "-".join(reversed(rep["to"].split("-")))
    return f"Period: {f} to {t}"


def to_xlsx(rep: dict, settings: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = rep["title"][:31].replace("/", "-")
    cols = rep["columns"]
    ws.append([settings.get("restaurant_name", "")])
    ws.append([f"GSTIN: {settings.get('gstin', '')}"])
    ws.append([rep["title"]])
    ws.append([_period(rep)])
    ws.append([])
    ws["A1"].font = Font(bold=True, size=14)
    ws["A3"].font = Font(bold=True, size=12)
    ws.append([c["label"] for c in cols])
    head_row = ws.max_row
    for i in range(1, len(cols) + 1):
        cell = ws.cell(row=head_row, column=i)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="7A2E0E")
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    for r in rep["rows"]:
        ws.append([r.get(c["key"], "") for c in cols])
    if rep["totals"]:
        ws.append([("TOTAL" if i == 0 else rep["totals"].get(c["key"], "")) for i, c in enumerate(cols)])
        for i in range(1, len(cols) + 1):
            ws.cell(row=ws.max_row, column=i).font = Font(bold=True)
    for i, c in enumerate(cols, 1):
        letter = get_column_letter(i)
        if c["type"] == "money":
            for row in ws.iter_rows(min_row=head_row + 1, min_col=i, max_col=i):
                row[0].number_format = "#,##0.00"
        width = max([len(str(c["label"]))] + [len(str(r.get(c["key"], ""))) for r in rep["rows"][:500]]) + 2
        ws.column_dimensions[letter].width = min(max(width, 8), 45)
    ws.freeze_panes = ws.cell(row=head_row + 1, column=1)
    for n in rep.get("notes", []):
        ws.append([])
        ws.append([f"Note: {n}"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _fmt(v, typ):
    if v is None or v == "":
        return ""
    if typ == "money":
        return f"{v:,.2f}"
    if typ == "num":
        return f"{v:g}" if isinstance(v, (int, float)) else str(v)
    if typ == "pct":
        return f"{v:g}"
    return str(v)


def to_pdf(rep: dict, settings: dict) -> bytes:
    buf = io.BytesIO()
    cols = rep["columns"]
    wide = len(cols) > 6
    page = landscape(A4) if wide else A4
    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=10 * mm, rightMargin=10 * mm, topMargin=10 * mm,
                            bottomMargin=10 * mm, title=rep["title"])
    styles = getSampleStyleSheet()
    cell = styles["BodyText"].clone("cell", fontSize=7 if len(cols) > 10 else 8, leading=9)
    head = cell.clone("head", textColor=colors.white, fontName="Helvetica-Bold")
    story = [Paragraph(f"<b>{settings.get('restaurant_name', '')}</b>", styles["Title"]),
             Paragraph(f"GSTIN: {settings.get('gstin', '') or '-'} &nbsp; | &nbsp; {rep['title']} &nbsp; | &nbsp; "
                       f"{_period(rep)}", styles["Normal"]), Spacer(1, 4 * mm)]
    data = [[Paragraph(c["label"], head) for c in cols]]
    for r in rep["rows"]:
        data.append([Paragraph(_fmt(r.get(c["key"]), c["type"]).replace("₹", "Rs."), cell) for c in cols])
    if rep["totals"]:
        data.append([Paragraph("<b>TOTAL</b>" if i == 0 else f"<b>{_fmt(rep['totals'].get(c['key'], ''), c['type'])}</b>", cell)
                     for i, c in enumerate(cols)])
    avail = page[0] - 20 * mm
    weights = [2.2 if c["type"] == "text" else 1 for c in cols]
    widths = [avail * w / sum(weights) for w in weights]
    tbl = Table(data, colWidths=widths, repeatRows=1)
    style = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7A2E0E")),
             ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#BBBBBB")),
             ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FBF4EE")])]
    for i, c in enumerate(cols):
        if c["type"] in ("money", "num", "pct"):
            style.append(("ALIGN", (i, 0), (i, -1), "RIGHT"))
    tbl.setStyle(TableStyle(style))
    story.append(tbl)
    for n in rep.get("notes", []):
        story += [Spacer(1, 3 * mm), Paragraph(f"<i>Note: {n.replace('₹', 'Rs.')}</i>", styles["Normal"])]
    doc.build(story)
    return buf.getvalue()
