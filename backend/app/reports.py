"""All reports. Each returns {title, columns, rows, totals, notes}. Columns: (key, label, type)
where type is text / date / num / money / pct. Numeric columns are totalled automatically unless listed in no_total."""
import calendar
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .gst import r2
from .models import (Bill, BillItem, Category, DailyClosing, Expense, Note, NoteItem, Product, Purchase,
                     PurchaseItem, StockMovement, Supplier, SupplierPayment)
from .services import STATE_NAMES, day_end, day_start, fy_bounds, get_settings

REGISTRY: dict[str, dict] = {}
NUMERIC = ("num", "money")


def report(name: str, title: str, group: str, dated: bool = True):
    def deco(fn):
        REGISTRY[name] = {"name": name, "title": title, "group": group, "dated": dated, "fn": fn}
        return fn
    return deco


def make(title, cols, rows, no_total=(), notes=None):
    totals = {}
    for key, _, typ in cols:
        if typ in NUMERIC and key not in no_total:
            totals[key] = r2(sum((r.get(key) or 0) for r in rows))
    return {"title": title, "columns": [{"key": k, "label": l, "type": t} for k, l, t in cols], "rows": rows,
            "totals": totals, "notes": notes or []}


def run(db: Session, name: str, f: date, t: date, params: dict) -> dict:
    r = REGISTRY[name]
    out = r["fn"](db, f, t, params)
    out["name"] = name
    out["group"] = r["group"]
    out["from"], out["to"] = f.isoformat(), t.isoformat()
    out["dated"] = r["dated"]
    return out


# ---------------- data helpers ----------------
def bills(db, f, t, status="ACTIVE"):
    stmt = select(Bill).where(Bill.bill_date >= day_start(f), Bill.bill_date < day_end(t)).order_by(Bill.id)
    if status:
        stmt = stmt.where(Bill.status == status)
    return list(db.scalars(stmt))


def bill_lines(db, f, t):
    stmt = select(BillItem, Bill).join(Bill, Bill.id == BillItem.bill_id).where(
        Bill.bill_date >= day_start(f), Bill.bill_date < day_end(t), Bill.status == "ACTIVE").order_by(Bill.id)
    return list(db.execute(stmt).all())


def notes(db, f, t, kind):
    return list(db.scalars(select(Note).where(Note.note_type == kind, Note.note_date >= f, Note.note_date <= t)
                           .order_by(Note.id)))


def note_lines(db, f, t, kind):
    stmt = select(NoteItem, Note).join(Note, Note.id == NoteItem.note_id).where(
        Note.note_type == kind, Note.note_date >= f, Note.note_date <= t)
    return list(db.execute(stmt).all())


def purchases(db, f, t):
    return list(db.scalars(select(Purchase).where(Purchase.invoice_date >= f, Purchase.invoice_date <= t,
                                                  Purchase.status == "ACTIVE").order_by(Purchase.invoice_date)))


def purchase_lines(db, f, t):
    stmt = select(PurchaseItem, Purchase).join(Purchase, Purchase.id == PurchaseItem.purchase_id).where(
        Purchase.invoice_date >= f, Purchase.invoice_date <= t, Purchase.status == "ACTIVE")
    return list(db.execute(stmt).all())


def dstr(d):
    return d.strftime("%d-%m-%Y")


def pos_name(code):
    return f"{code}-{STATE_NAMES.get(code, '')}" if code else ""


def add(acc: dict, key, **vals):
    row = acc.setdefault(key, defaultdict(float))
    for k, v in vals.items():
        row[k] += v or 0
    return row


# ======================= SALES =======================
@report("daily_sales", "Daily Sales Summary", "Sales")
def daily_sales(db, f, t, p):
    acc = {}
    for b in bills(db, f, t, status=None):
        key = b.bill_date.date()
        if b.status == "CANCELLED":
            add(acc, key, cancelled=1, cancelled_value=b.grand_total)
            continue
        add(acc, key, bills=1, gross=b.gross_amount, discount=b.item_discount + b.bill_discount,
            taxable=b.taxable_amount, exempt=b.exempt_amount, cgst=b.cgst, sgst=b.sgst, igst=b.igst,
            total=b.grand_total, cash=b.cash_amount, upi=b.upi_amount)
    rows = [{"date": dstr(k), **{x: r2(y) for x, y in v.items()}} for k, v in sorted(acc.items())]
    cols = [("date", "Date", "date"), ("bills", "Bills", "num"), ("gross", "Gross", "money"),
            ("discount", "Discount", "money"), ("taxable", "Taxable", "money"), ("exempt", "Exempt", "money"),
            ("cgst", "CGST", "money"), ("sgst", "SGST", "money"), ("igst", "IGST", "money"),
            ("total", "Net Sales", "money"), ("cash", "Cash", "money"), ("upi", "UPI", "money"),
            ("cancelled", "Cancelled", "num"), ("cancelled_value", "Cancelled Value", "money")]
    return make("Daily Sales Summary", cols, rows)


@report("sales_register", "Sales Register (Bill-wise)", "Sales")
def sales_register(db, f, t, p):
    rows = [{"bill_no": b.bill_no, "date": b.bill_date.strftime("%d-%m-%Y %H:%M"), "customer": b.customer_name,
             "gstin": b.customer_gstin, "type": b.invoice_type, "order_type": b.order_type,
             "taxable": b.taxable_amount, "exempt": b.exempt_amount, "cgst": b.cgst, "sgst": b.sgst, "igst": b.igst,
             "discount": r2(b.item_discount + b.bill_discount), "round_off": b.round_off, "total": b.grand_total,
             "mode": b.payment_mode, "cash": b.cash_amount, "upi": b.upi_amount}
            for b in bills(db, f, t)]
    cols = [("bill_no", "Bill No", "text"), ("date", "Date", "date"), ("customer", "Customer", "text"),
            ("gstin", "GSTIN", "text"), ("type", "B2B/B2C", "text"), ("order_type", "Order", "text"),
            ("discount", "Discount", "money"), ("taxable", "Taxable", "money"), ("exempt", "Exempt", "money"),
            ("cgst", "CGST", "money"), ("sgst", "SGST", "money"), ("igst", "IGST", "money"),
            ("round_off", "Round Off", "money"), ("total", "Total", "money"), ("mode", "Mode", "text"),
            ("cash", "Cash", "money"), ("upi", "UPI", "money")]
    return make("Sales Register", cols, rows)


@report("item_sales", "Item-wise Sales", "Sales")
def item_sales(db, f, t, p):
    cats = {c.id: c.name for c in db.scalars(select(Category))}
    prods = {x.id: x for x in db.scalars(select(Product))}
    acc = {}
    for it, b in bill_lines(db, f, t):
        pr = prods.get(it.product_id)
        add(acc, it.item_name, qty=it.qty, gross=it.gross, discount=it.discount + it.bill_discount_share,
            taxable=it.taxable, tax=it.cgst + it.sgst + it.igst, total=it.total, cost=it.cost)
        acc[it.item_name]["category"] = cats.get(pr.category_id, "") if pr else ""
    rows = []
    for name, v in sorted(acc.items(), key=lambda kv: -kv[1]["total"]):
        rows.append({"item": name, "category": v["category"], "qty": round(v["qty"], 3), "gross": r2(v["gross"]),
                     "discount": r2(v["discount"]), "taxable": r2(v["taxable"]), "tax": r2(v["tax"]),
                     "total": r2(v["total"]), "cost": r2(v["cost"]), "margin": r2(v["taxable"] - v["cost"])})
    cols = [("item", "Item", "text"), ("category", "Category", "text"), ("qty", "Qty", "num"),
            ("gross", "Gross", "money"), ("discount", "Discount", "money"), ("taxable", "Taxable", "money"),
            ("tax", "GST", "money"), ("total", "Total", "money"), ("cost", "Est. Cost", "money"),
            ("margin", "Est. Margin", "money")]
    return make("Item-wise Sales", cols, rows)


@report("category_sales", "Category-wise Sales", "Sales")
def category_sales(db, f, t, p):
    cats = {c.id: c.name for c in db.scalars(select(Category))}
    prods = {x.id: x for x in db.scalars(select(Product))}
    acc = {}
    for it, b in bill_lines(db, f, t):
        pr = prods.get(it.product_id)
        add(acc, cats.get(pr.category_id, "Uncategorised") if pr else "Uncategorised", qty=it.qty,
            taxable=it.taxable, tax=it.cgst + it.sgst + it.igst, total=it.total)
    grand = sum(v["total"] for v in acc.values()) or 1
    rows = [{"category": k, "qty": round(v["qty"], 3), "taxable": r2(v["taxable"]), "tax": r2(v["tax"]),
             "total": r2(v["total"]), "share": round(v["total"] * 100 / grand, 1)}
            for k, v in sorted(acc.items(), key=lambda kv: -kv[1]["total"])]
    cols = [("category", "Category", "text"), ("qty", "Qty", "num"), ("taxable", "Taxable", "money"),
            ("tax", "GST", "money"), ("total", "Total", "money"), ("share", "Share %", "pct")]
    return make("Category-wise Sales", cols, rows)


@report("payment_mode", "Cash vs UPI Sales", "Sales")
def payment_mode(db, f, t, p):
    acc = {}
    for b in bills(db, f, t):
        add(acc, b.bill_date.date(), cash_bills=1 if b.payment_mode == "CASH" else 0,
            upi_bills=1 if b.payment_mode == "UPI" else 0, split_bills=1 if b.payment_mode == "SPLIT" else 0,
            cash=b.cash_amount, upi=b.upi_amount, total=b.grand_total)
    rows = [{"date": dstr(k), **{x: r2(y) for x, y in v.items()}} for k, v in sorted(acc.items())]
    cols = [("date", "Date", "date"), ("cash_bills", "Cash Bills", "num"), ("upi_bills", "UPI Bills", "num"),
            ("split_bills", "Split Bills", "num"), ("cash", "Cash", "money"), ("upi", "UPI", "money"),
            ("total", "Total", "money")]
    return make("Cash vs UPI Sales", cols, rows)


@report("order_type_sales", "Dine-in / Takeaway / Delivery", "Sales")
def order_type_sales(db, f, t, p):
    acc = {}
    for b in bills(db, f, t):
        add(acc, b.order_type, bills=1, total=b.grand_total)
    rows = [{"order_type": k.replace("_", " ").title(), "bills": int(v["bills"]), "total": r2(v["total"]),
             "average": r2(v["total"] / v["bills"])} for k, v in acc.items()]
    return make("Order Type Sales", [("order_type", "Order Type", "text"), ("bills", "Bills", "num"),
                                     ("total", "Total", "money"), ("average", "Avg Bill", "money")], rows,
                no_total=("average",))


@report("cancelled_bills", "Cancelled Bills", "Sales")
def cancelled_bills(db, f, t, p):
    rows = [{"bill_no": b.bill_no, "date": b.bill_date.strftime("%d-%m-%Y %H:%M"), "customer": b.customer_name,
             "total": b.grand_total, "reason": b.cancel_reason, "cancelled_by": b.cancelled_by,
             "cancelled_at": b.cancelled_at.strftime("%d-%m-%Y %H:%M") if b.cancelled_at else ""}
            for b in bills(db, f, t, "CANCELLED")]
    cols = [("bill_no", "Bill No", "text"), ("date", "Bill Date", "date"), ("customer", "Customer", "text"),
            ("total", "Amount", "money"), ("reason", "Reason", "text"), ("cancelled_by", "By", "text"),
            ("cancelled_at", "Cancelled At", "date")]
    return make("Cancelled Bills", cols, rows)


@report("customer_sales", "Customer-wise Sales", "Sales")
def customer_sales(db, f, t, p):
    acc = {}
    for b in bills(db, f, t):
        add(acc, (b.customer_name or "Walk-in", b.customer_phone, b.customer_gstin), bills=1, total=b.grand_total)
    rows = [{"customer": k[0], "phone": k[1], "gstin": k[2], "bills": int(v["bills"]), "total": r2(v["total"])}
            for k, v in sorted(acc.items(), key=lambda kv: -kv[1]["total"])]
    return make("Customer-wise Sales", [("customer", "Customer", "text"), ("phone", "Phone", "text"),
                                        ("gstin", "GSTIN", "text"), ("bills", "Bills", "num"),
                                        ("total", "Total", "money")], rows)


# ======================= GST =======================
GST_COLS = [("taxable", "Taxable Value", "money"), ("cgst", "CGST", "money"), ("sgst", "SGST", "money"),
            ("igst", "IGST", "money")]


def _rate_rows(lines_iter):
    acc = {}
    for key, it in lines_iter:
        add(acc, key, taxable=it.taxable, cgst=it.cgst, sgst=it.sgst, igst=it.igst)
    return acc


@report("sales_gst_register", "Sales GST Register", "GST")
def sales_gst_register(db, f, t, p):
    acc = {}
    meta = {}
    for it, b in bill_lines(db, f, t):
        k = (b.id, it.gst_rate)
        meta[k] = b
        add(acc, k, taxable=it.taxable, cgst=it.cgst, sgst=it.sgst, igst=it.igst)
    rows = []
    for k, v in acc.items():
        b = meta[k]
        rows.append({"bill_no": b.bill_no, "date": dstr(b.bill_date), "customer": b.customer_name,
                     "gstin": b.customer_gstin, "pos": pos_name(b.place_of_supply), "rate": k[1],
                     **{x: r2(v[x]) for x in ("taxable", "cgst", "sgst", "igst")},
                     "total": r2(v["taxable"] + v["cgst"] + v["sgst"] + v["igst"]), "invoice_value": b.grand_total})
    cols = [("bill_no", "Invoice No", "text"), ("date", "Date", "date"), ("customer", "Customer", "text"),
            ("gstin", "GSTIN", "text"), ("pos", "Place of Supply", "text"), ("rate", "GST %", "pct"), *GST_COLS,
            ("total", "Total", "money"), ("invoice_value", "Invoice Value", "money")]
    return make("Sales GST Register", cols, rows, no_total=("invoice_value",))


@report("purchase_gst_register", "Purchase GST Register", "GST")
def purchase_gst_register(db, f, t, p):
    acc, meta = {}, {}
    for it, pu in purchase_lines(db, f, t):
        k = (pu.id, it.gst_rate)
        meta[k] = pu
        add(acc, k, taxable=it.taxable, cgst=it.cgst, sgst=it.sgst, igst=it.igst)
    rows = []
    for k, v in sorted(acc.items(), key=lambda kv: meta[kv[0]].invoice_date):
        pu = meta[k]
        rows.append({"date": dstr(pu.invoice_date), "purchase_no": pu.purchase_no, "supplier": pu.supplier.name,
                     "gstin": pu.supplier.gstin, "invoice_no": pu.supplier_invoice_no, "rate": k[1],
                     **{x: r2(v[x]) for x in ("taxable", "cgst", "sgst", "igst")},
                     "total": r2(v["taxable"] + v["cgst"] + v["sgst"] + v["igst"]), "invoice_value": pu.grand_total})
    cols = [("date", "Inv Date", "date"), ("purchase_no", "Purchase No", "text"), ("supplier", "Supplier", "text"),
            ("gstin", "GSTIN", "text"), ("invoice_no", "Supplier Inv No", "text"), ("rate", "GST %", "pct"),
            *GST_COLS, ("total", "Total", "money"), ("invoice_value", "Invoice Value", "money")]
    return make("Purchase GST Register", cols, rows, no_total=("invoice_value",))


def _summary_by_rate(main, minus):
    a = _rate_rows(main)
    b = _rate_rows(minus)
    rows = []
    for rate in sorted(set(a) | set(b)):
        x, y = a.get(rate, defaultdict(float)), b.get(rate, defaultdict(float))
        row = {"rate": rate, "gross_taxable": r2(x["taxable"]), "adj_taxable": r2(y["taxable"])}
        for k in ("taxable", "cgst", "sgst", "igst"):
            row[k] = r2(x[k] - y[k])
        row["total_tax"] = r2(row["cgst"] + row["sgst"] + row["igst"])
        rows.append(row)
    return rows


@report("output_gst_summary", "Output GST Summary (rate-wise)", "GST")
def output_gst_summary(db, f, t, p):
    rows = _summary_by_rate(((it.gst_rate, it) for it, _ in bill_lines(db, f, t)),
                            ((it.gst_rate, it) for it, _ in note_lines(db, f, t, "CREDIT")))
    cols = [("rate", "GST %", "pct"), ("gross_taxable", "Sales Taxable", "money"),
            ("adj_taxable", "Less Credit Notes", "money"), ("taxable", "Net Taxable", "money"),
            ("cgst", "CGST", "money"), ("sgst", "SGST", "money"), ("igst", "IGST", "money"),
            ("total_tax", "Total GST", "money")]
    return make("Output GST Summary", cols, rows)


@report("input_gst_summary", "Input GST Summary (rate-wise)", "GST")
def input_gst_summary(db, f, t, p):
    rows = _summary_by_rate(((it.gst_rate, it) for it, _ in purchase_lines(db, f, t)),
                            ((it.gst_rate, it) for it, _ in note_lines(db, f, t, "DEBIT")))
    cols = [("rate", "GST %", "pct"), ("gross_taxable", "Purchase Taxable", "money"),
            ("adj_taxable", "Less Debit Notes", "money"), ("taxable", "Net Taxable", "money"),
            ("cgst", "CGST", "money"), ("sgst", "SGST", "money"), ("igst", "IGST", "money"),
            ("total_tax", "Total Input GST", "money")]
    return make("Input GST Summary", cols, rows,
                notes=["Input tax credit eligibility depends on your GST scheme (e.g. restaurant services at 5% "
                       "are generally not eligible for ITC). Verify with your tax consultant."])


def _head_summary(db, f, t, head):
    acc = {}
    for b in bills(db, f, t):
        add(acc, b.bill_date.date(), output=getattr(b, head))
    for n in notes(db, f, t, "CREDIT"):
        add(acc, n.note_date, credit_notes=getattr(n, head))
    for pu in purchases(db, f, t):
        add(acc, pu.invoice_date, input=getattr(pu, head))
    for n in notes(db, f, t, "DEBIT"):
        add(acc, n.note_date, debit_notes=getattr(n, head))
    rows = []
    for d, v in sorted(acc.items()):
        out = v["output"] - v["credit_notes"]
        inp = v["input"] - v["debit_notes"]
        rows.append({"date": dstr(d), "output": r2(v["output"]), "credit_notes": r2(v["credit_notes"]),
                     "net_output": r2(out), "input": r2(v["input"]), "debit_notes": r2(v["debit_notes"]),
                     "net_input": r2(inp), "net": r2(out - inp)})
    label = head.upper()
    cols = [("date", "Date", "date"), ("output", f"Output {label}", "money"), ("credit_notes", "Less CN", "money"),
            ("net_output", "Net Output", "money"), ("input", f"Input {label}", "money"),
            ("debit_notes", "Less DN", "money"), ("net_input", "Net Input", "money"),
            ("net", "Net (Output - Input)", "money")]
    return make(f"{label} Summary", cols, rows)


@report("cgst_summary", "CGST Summary", "GST")
def cgst_summary(db, f, t, p):
    return _head_summary(db, f, t, "cgst")


@report("sgst_summary", "SGST Summary", "GST")
def sgst_summary(db, f, t, p):
    return _head_summary(db, f, t, "sgst")


@report("igst_summary", "IGST Summary", "GST")
def igst_summary(db, f, t, p):
    return _head_summary(db, f, t, "igst")


@report("taxable_sales", "Taxable Sales Report", "GST")
def taxable_sales(db, f, t, p):
    acc = {}
    for it, b in bill_lines(db, f, t):
        if it.tax_category == "TAXABLE":
            add(acc, (b.bill_date.date(), it.gst_rate), taxable=it.taxable, cgst=it.cgst, sgst=it.sgst, igst=it.igst)
    rows = [{"date": dstr(k[0]), "rate": k[1], **{x: r2(v[x]) for x in ("taxable", "cgst", "sgst", "igst")},
             "total": r2(v["taxable"] + v["cgst"] + v["sgst"] + v["igst"])} for k, v in sorted(acc.items())]
    return make("Taxable Sales", [("date", "Date", "date"), ("rate", "GST %", "pct"), *GST_COLS,
                                  ("total", "Total", "money")], rows)


@report("exempt_sales", "Exempt / Nil / Zero-rated Sales", "GST")
def exempt_sales(db, f, t, p):
    rows = [{"date": dstr(b.bill_date), "bill_no": b.bill_no, "item": it.item_name, "hsn": it.hsn,
             "category": it.tax_category, "qty": it.qty, "value": it.taxable}
            for it, b in bill_lines(db, f, t) if it.tax_category != "TAXABLE"]
    return make("Exempt / Nil / Zero-rated Sales",
                [("date", "Date", "date"), ("bill_no", "Bill No", "text"), ("item", "Item", "text"),
                 ("hsn", "HSN/SAC", "text"), ("category", "Type", "text"), ("qty", "Qty", "num"),
                 ("value", "Value", "money")], rows)


@report("hsn_summary", "HSN/SAC-wise Summary", "GST")
def hsn_summary(db, f, t, p):
    acc, desc = {}, {}
    for it, _ in bill_lines(db, f, t):
        k = (it.hsn or "-", it.unit, it.gst_rate)
        desc.setdefault(k, it.item_name)
        add(acc, k, qty=it.qty, taxable=it.taxable, cgst=it.cgst, sgst=it.sgst, igst=it.igst)
    for it, _ in note_lines(db, f, t, "CREDIT"):
        k = (it.hsn or "-", it.unit, it.gst_rate)
        desc.setdefault(k, it.item_name)
        add(acc, k, qty=-it.qty, taxable=-it.taxable, cgst=-it.cgst, sgst=-it.sgst, igst=-it.igst)
    rows = [{"hsn": k[0], "description": desc[k], "uqc": k[1], "qty": round(v["qty"], 3), "rate": k[2],
             "total_value": r2(v["taxable"] + v["cgst"] + v["sgst"] + v["igst"]),
             **{x: r2(v[x]) for x in ("taxable", "igst", "cgst", "sgst")}} for k, v in sorted(acc.items())]
    cols = [("hsn", "HSN/SAC", "text"), ("description", "Description", "text"), ("uqc", "UQC", "text"),
            ("qty", "Total Qty", "num"), ("rate", "Rate %", "pct"), ("total_value", "Total Value", "money"),
            ("taxable", "Taxable Value", "money"), ("igst", "IGST", "money"), ("cgst", "CGST", "money"),
            ("sgst", "SGST", "money")]
    return make("HSN/SAC-wise Summary (net of credit notes)", cols, rows, no_total=("qty",))


@report("b2b_sales", "B2B Sales (GSTR-1 Table 4)", "GST")
def b2b_sales(db, f, t, p):
    acc, meta = {}, {}
    for it, b in bill_lines(db, f, t):
        if b.invoice_type != "B2B":
            continue
        k = (b.id, it.gst_rate)
        meta[k] = b
        add(acc, k, taxable=it.taxable, cgst=it.cgst, sgst=it.sgst, igst=it.igst)
    rows = [{"gstin": meta[k].customer_gstin, "name": meta[k].customer_name, "invoice_no": meta[k].bill_no,
             "date": dstr(meta[k].bill_date), "invoice_value": meta[k].grand_total,
             "pos": pos_name(meta[k].place_of_supply), "reverse_charge": "N", "rate": k[1],
             **{x: r2(v[x]) for x in ("taxable", "igst", "cgst", "sgst")}} for k, v in acc.items()]
    cols = [("gstin", "GSTIN of Recipient", "text"), ("name", "Receiver Name", "text"),
            ("invoice_no", "Invoice No", "text"), ("date", "Invoice Date", "date"),
            ("invoice_value", "Invoice Value", "money"), ("pos", "Place of Supply", "text"),
            ("reverse_charge", "Reverse Charge", "text"), ("rate", "Rate", "pct"),
            ("taxable", "Taxable Value", "money"), ("igst", "IGST", "money"), ("cgst", "CGST", "money"),
            ("sgst", "SGST", "money")]
    return make("B2B Sales", cols, rows, no_total=("invoice_value",))


B2CL_LIMIT = 100000


@report("b2c_sales", "B2C Small Sales (GSTR-1 Table 7)", "GST")
def b2c_sales(db, f, t, p):
    acc = {}
    for it, b in bill_lines(db, f, t):
        if b.invoice_type == "B2B" or (b.supply_type == "INTER" and b.grand_total > B2CL_LIMIT):
            continue
        add(acc, ("OE", b.place_of_supply, it.gst_rate),
            taxable=it.taxable, cgst=it.cgst, sgst=it.sgst, igst=it.igst)
    rows = [{"type": k[0], "pos": pos_name(k[1]), "rate": k[2], **{x: r2(v[x]) for x in ("taxable", "igst", "cgst", "sgst")}}
            for k, v in sorted(acc.items())]
    cols = [("type", "Type", "text"), ("pos", "Place of Supply", "text"), ("rate", "Rate", "pct"),
            ("taxable", "Taxable Value", "money"), ("igst", "IGST", "money"), ("cgst", "CGST", "money"),
            ("sgst", "SGST", "money")]
    return make("B2C Small Sales (B2CS)", cols, rows)


@report("b2cl_sales", "B2C Large Inter-state (GSTR-1 Table 5)", "GST")
def b2cl_sales(db, f, t, p):
    rows = []
    for b in bills(db, f, t):
        if b.invoice_type == "B2C" and b.supply_type == "INTER" and b.grand_total > B2CL_LIMIT:
            rows.append({"invoice_no": b.bill_no, "date": dstr(b.bill_date), "invoice_value": b.grand_total,
                         "pos": pos_name(b.place_of_supply), "taxable": b.taxable_amount, "igst": b.igst})
    return make("B2C Large", [("invoice_no", "Invoice No", "text"), ("date", "Date", "date"),
                              ("invoice_value", "Invoice Value", "money"), ("pos", "Place of Supply", "text"),
                              ("taxable", "Taxable", "money"), ("igst", "IGST", "money")], rows,
                notes=[f"Inter-state B2C invoices above ₹{B2CL_LIMIT:,}. Check the current threshold notified by CBIC."])


def _note_register(db, f, t, kind):
    rows = [{"note_no": n.note_no, "date": dstr(n.note_date), "ref_doc": n.ref_doc_no,
             "ref_date": dstr(n.ref_doc_date) if n.ref_doc_date else "", "party": n.party_name,
             "gstin": n.party_gstin, "reason": n.reason, "taxable": n.taxable, "cgst": n.cgst, "sgst": n.sgst,
             "igst": n.igst, "total": n.total, "settlement": n.settlement_mode} for n in notes(db, f, t, kind)]
    cols = [("note_no", "Note No", "text"), ("date", "Date", "date"),
            ("ref_doc", "Against Invoice" if kind == "CREDIT" else "Supplier Invoice", "text"),
            ("ref_date", "Invoice Date", "date"), ("party", "Party", "text"), ("gstin", "GSTIN", "text"),
            ("reason", "Reason", "text"), *GST_COLS, ("total", "Total", "money"), ("settlement", "Settled By", "text")]
    return make("Credit Note Register" if kind == "CREDIT" else "Debit Note Register", cols, rows)


@report("credit_note_register", "Credit Note Register", "GST")
def credit_note_register(db, f, t, p):
    return _note_register(db, f, t, "CREDIT")


@report("debit_note_register", "Debit Note Register", "GST")
def debit_note_register(db, f, t, p):
    return _note_register(db, f, t, "DEBIT")


def _months(f, t):
    y, m = f.year, f.month
    while (y, m) <= (t.year, t.month):
        a = max(date(y, m, 1), f)
        b = min(date(y, m, calendar.monthrange(y, m)[1]), t)
        yield a, b
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def _gst_period_rows(db, f, t):
    rows = []
    for a, b in _months(f, t):
        bl = bills(db, a, b)
        cn = notes(db, a, b, "CREDIT")
        pu = purchases(db, a, b)
        dn = notes(db, a, b, "DEBIT")
        r = {"month": a.strftime("%b %Y"),
             "taxable_sales": r2(sum(x.taxable_amount for x in bl) - sum(x.taxable for x in cn)),
             "exempt_sales": r2(sum(x.exempt_amount for x in bl))}
        for h in ("cgst", "sgst", "igst"):
            out = sum(getattr(x, h) for x in bl) - sum(getattr(x, h) for x in cn)
            inp = sum(getattr(x, h) for x in pu) - sum(getattr(x, h) for x in dn)
            r[f"out_{h}"] = r2(out)
            r[f"in_{h}"] = r2(inp)
        r["total_output"] = r2(r["out_cgst"] + r["out_sgst"] + r["out_igst"])
        r["total_input"] = r2(r["in_cgst"] + r["in_sgst"] + r["in_igst"])
        r["net_payable"] = r2(r["total_output"] - r["total_input"])
        rows.append(r)
    cols = [("month", "Month", "text"), ("taxable_sales", "Taxable Sales", "money"),
            ("exempt_sales", "Exempt Sales", "money"), ("out_cgst", "Output CGST", "money"),
            ("out_sgst", "Output SGST", "money"), ("out_igst", "Output IGST", "money"),
            ("total_output", "Total Output", "money"), ("in_cgst", "Input CGST", "money"),
            ("in_sgst", "Input SGST", "money"), ("in_igst", "Input IGST", "money"),
            ("total_input", "Total Input", "money"), ("net_payable", "Net (before ITC rules)", "money")]
    return cols, rows


@report("gst_monthly_summary", "GST Monthly Summary", "GST")
def gst_monthly_summary(db, f, t, p):
    cols, rows = _gst_period_rows(db, f, t)
    return make("GST Monthly Summary", cols, rows,
                notes=["Net figure is indicative. Apply ITC eligibility and set-off rules before filing."])


@report("fy_gst_summary", "Financial Year GST Summary", "GST")
def fy_gst_summary(db, f, t, p):
    start, end, name = fy_bounds(f)
    cols, rows = _gst_period_rows(db, start, end)
    out = make(f"GST Summary – FY {name}", cols, rows,
               notes=["Covers the whole financial year containing the 'From' date."])
    out["fy"] = name
    return out


@report("gstr1_summary", "GSTR-1 Preparation Summary", "GST")
def gstr1_summary(db, f, t, p):
    bl = bills(db, f, t)
    lines = bill_lines(db, f, t)
    rows = []

    def sec(section, desc, count, taxable, igst, cgst, sgst):
        rows.append({"section": section, "description": desc, "count": count, "taxable": r2(taxable),
                     "igst": r2(igst), "cgst": r2(cgst), "sgst": r2(sgst)})

    b2b = [x for x in bl if x.invoice_type == "B2B"]
    sec("4A", "B2B invoices", len(b2b), sum(x.taxable_amount for x in b2b), sum(x.igst for x in b2b),
        sum(x.cgst for x in b2b), sum(x.sgst for x in b2b))
    b2cl = [x for x in bl if x.invoice_type == "B2C" and x.supply_type == "INTER" and x.grand_total > B2CL_LIMIT]
    sec("5", "B2C Large (inter-state)", len(b2cl), sum(x.taxable_amount for x in b2cl), sum(x.igst for x in b2cl), 0, 0)
    b2cs = [x for x in bl if x.invoice_type == "B2C" and x not in b2cl]
    sec("7", "B2C Small", len(b2cs), sum(x.taxable_amount for x in b2cs), sum(x.igst for x in b2cs),
        sum(x.cgst for x in b2cs), sum(x.sgst for x in b2cs))
    nil = [it for it, _ in lines if it.tax_category != "TAXABLE"]
    sec("8", "Nil rated / Exempt / Non-GST", len(nil), sum(x.taxable for x in nil), 0, 0, 0)
    cn = notes(db, f, t, "CREDIT")
    cdnr = [n for n in cn if n.party_gstin]
    cdnur = [n for n in cn if not n.party_gstin]
    sec("9B", "Credit notes – registered (CDNR)", len(cdnr), sum(n.taxable for n in cdnr),
        sum(n.igst for n in cdnr), sum(n.cgst for n in cdnr), sum(n.sgst for n in cdnr))
    sec("9B", "Credit notes – unregistered (CDNUR)", len(cdnur), sum(n.taxable for n in cdnur),
        sum(n.igst for n in cdnur), sum(n.cgst for n in cdnur), sum(n.sgst for n in cdnur))
    all_bills = bills(db, f, t, status=None)
    if all_bills:
        rows.append({"section": "13", "description": f"Invoices issued: {all_bills[0].bill_no} to {all_bills[-1].bill_no}",
                     "count": len(all_bills), "taxable": 0, "igst": 0, "cgst": 0, "sgst": 0})
        rows.append({"section": "13", "description": "Cancelled invoices",
                     "count": len([x for x in all_bills if x.status == "CANCELLED"]),
                     "taxable": 0, "igst": 0, "cgst": 0, "sgst": 0})
    cols = [("section", "Table", "text"), ("description", "Description", "text"), ("count", "Count", "num"),
            ("taxable", "Taxable Value", "money"), ("igst", "IGST", "money"), ("cgst", "CGST", "money"),
            ("sgst", "SGST", "money")]
    return make("GSTR-1 Summary", cols, rows, no_total=("count", "taxable", "igst", "cgst", "sgst"),
                notes=["Use the B2B, B2CS, B2CL, HSN and Credit Note reports for table-wise detail.",
                       "This application does not file returns. Upload/enter data on the official GST portal."])


@report("gstr3b_summary", "GSTR-3B Preparation Summary", "GST")
def gstr3b_summary(db, f, t, p):
    lines = bill_lines(db, f, t)
    cn_lines = note_lines(db, f, t, "CREDIT")
    taxable = [it for it, _ in lines if it.tax_category == "TAXABLE"]
    zero = [it for it, _ in lines if it.tax_category == "ZERO"]
    nil = [it for it, _ in lines if it.tax_category in ("NIL", "EXEMPT")]
    cnt = [it for it, _ in cn_lines if it.tax_category == "TAXABLE"]
    pu, dn = purchases(db, f, t), notes(db, f, t, "DEBIT")

    def s(items, k):
        return sum(getattr(x, k) for x in items)

    rows = [
        {"section": "3.1(a)", "description": "Outward taxable supplies (net of credit notes)",
         "taxable": r2(s(taxable, "taxable") - s(cnt, "taxable")), "igst": r2(s(taxable, "igst") - s(cnt, "igst")),
         "cgst": r2(s(taxable, "cgst") - s(cnt, "cgst")), "sgst": r2(s(taxable, "sgst") - s(cnt, "sgst"))},
        {"section": "3.1(b)", "description": "Outward zero-rated supplies", "taxable": r2(s(zero, "taxable")),
         "igst": r2(s(zero, "igst")), "cgst": 0, "sgst": 0},
        {"section": "3.1(c)", "description": "Nil rated / exempted supplies", "taxable": r2(s(nil, "taxable")),
         "igst": 0, "cgst": 0, "sgst": 0},
        {"section": "4(A)(5)", "description": "All other ITC (purchases, before eligibility check)",
         "taxable": r2(s(pu, "taxable_amount")), "igst": r2(s(pu, "igst")), "cgst": r2(s(pu, "cgst")),
         "sgst": r2(s(pu, "sgst"))},
        {"section": "4(B)", "description": "ITC reversed – purchase returns (debit notes)",
         "taxable": r2(s(dn, "taxable")), "igst": r2(s(dn, "igst")), "cgst": r2(s(dn, "cgst")),
         "sgst": r2(s(dn, "sgst"))},
    ]
    cols = [("section", "Table", "text"), ("description", "Description", "text"),
            ("taxable", "Taxable Value", "money"), ("igst", "IGST", "money"), ("cgst", "CGST", "money"),
            ("sgst", "SGST", "money")]
    return make("GSTR-3B Summary", cols, rows, no_total=("taxable", "igst", "cgst", "sgst"),
                notes=["Restaurant services under 5% GST generally cannot claim ITC – confirm eligibility.",
                       "This application does not file returns. Reconcile and file on the official GST portal."])


# ======================= PURCHASE =======================
@report("purchase_register", "Purchase Register", "Purchases")
def purchase_register(db, f, t, p):
    paid = defaultdict(float)
    for pay in db.scalars(select(SupplierPayment).where(SupplierPayment.is_cancelled.is_(False),
                                                       SupplierPayment.purchase_id.is_not(None))):
        paid[pay.purchase_id] += pay.amount
    rows = [{"date": dstr(x.invoice_date), "purchase_no": x.purchase_no, "supplier": x.supplier.name,
             "invoice_no": x.supplier_invoice_no, "taxable": x.taxable_amount, "cgst": x.cgst, "sgst": x.sgst,
             "igst": x.igst, "total": x.grand_total, "paid": r2(paid[x.id]), "balance": r2(x.grand_total - paid[x.id])}
            for x in purchases(db, f, t)]
    cols = [("date", "Date", "date"), ("purchase_no", "Purchase No", "text"), ("supplier", "Supplier", "text"),
            ("invoice_no", "Supplier Inv", "text"), *GST_COLS, ("total", "Total", "money"),
            ("paid", "Paid (linked)", "money"), ("balance", "Balance", "money")]
    return make("Purchase Register", cols, rows)


@report("supplier_purchase", "Supplier-wise Purchases", "Purchases")
def supplier_purchase(db, f, t, p):
    acc = {}
    for x in purchases(db, f, t):
        add(acc, x.supplier.name, invoices=1, taxable=x.taxable_amount, tax=x.total_tax, total=x.grand_total)
    rows = [{"supplier": k, **{a: r2(b) for a, b in v.items()}} for k, v in sorted(acc.items(), key=lambda kv: -kv[1]["total"])]
    return make("Supplier-wise Purchases", [("supplier", "Supplier", "text"), ("invoices", "Invoices", "num"),
                                            ("taxable", "Taxable", "money"), ("tax", "GST", "money"),
                                            ("total", "Total", "money")], rows)


@report("purchase_items", "Item-wise Purchases", "Purchases")
def purchase_items(db, f, t, p):
    acc = {}
    for it, _ in purchase_lines(db, f, t):
        add(acc, (it.item_name, it.unit), qty=it.qty, taxable=it.taxable, tax=it.cgst + it.sgst + it.igst, total=it.total)
    rows = [{"item": k[0], "unit": k[1], "qty": round(v["qty"], 3), "avg_rate": r2(v["taxable"] / v["qty"]) if v["qty"] else 0,
             "taxable": r2(v["taxable"]), "tax": r2(v["tax"]), "total": r2(v["total"])} for k, v in sorted(acc.items())]
    return make("Item-wise Purchases", [("item", "Item", "text"), ("unit", "Unit", "text"), ("qty", "Qty", "num"),
                                        ("avg_rate", "Avg Rate", "money"), ("taxable", "Taxable", "money"),
                                        ("tax", "GST", "money"), ("total", "Total", "money")], rows,
                no_total=("avg_rate", "qty"))


@report("supplier_outstanding", "Supplier Outstanding", "Purchases", dated=False)
def supplier_outstanding(db, f, t, p):
    from .routers.masters import supplier_balance
    rows = []
    for s in db.scalars(select(Supplier).order_by(Supplier.name)):
        b = supplier_balance(db, s.id)
        rows.append({"supplier": s.name, "phone": s.phone, "gstin": s.gstin, **b})
    return make("Supplier Outstanding", [("supplier", "Supplier", "text"), ("phone", "Phone", "text"),
                                         ("gstin", "GSTIN", "text"), ("opening_balance", "Opening", "money"),
                                         ("purchases", "Purchases", "money"), ("paid", "Paid", "money"),
                                         ("returns", "Returns", "money"), ("outstanding", "Outstanding", "money")], rows)


# ======================= STOCK =======================
@report("stock_summary", "Current Stock & Value", "Stock", dated=False)
def stock_summary(db, f, t, p):
    cats = {c.id: c.name for c in db.scalars(select(Category))}
    rows = [{"code": x.code, "name": x.name, "category": cats.get(x.category_id, ""), "type": x.product_type,
             "unit": x.unit, "stock": x.current_stock, "min": x.min_stock, "max": x.max_stock,
             "rate": x.purchase_price, "value": r2(x.current_stock * x.purchase_price),
             "status": "LOW" if x.current_stock <= x.min_stock else ("OVER" if x.max_stock and x.current_stock > x.max_stock else "OK")}
            for x in db.scalars(select(Product).where(Product.track_stock.is_(True), Product.is_active.is_(True))
                                .order_by(Product.name))]
    return make("Current Stock", [("code", "Code", "text"), ("name", "Product", "text"),
                                  ("category", "Category", "text"), ("type", "Type", "text"), ("unit", "Unit", "text"),
                                  ("stock", "Stock", "num"), ("min", "Min", "num"), ("max", "Max", "num"),
                                  ("rate", "Cost Rate", "money"), ("value", "Stock Value", "money"),
                                  ("status", "Status", "text")], rows,
                no_total=("stock", "min", "max", "rate"))


@report("low_stock", "Low Stock Items", "Stock", dated=False)
def low_stock(db, f, t, p):
    rows = [{"code": x.code, "name": x.name, "unit": x.unit, "stock": x.current_stock, "min": x.min_stock,
             "reorder": r2(max((x.max_stock or x.min_stock * 2) - x.current_stock, 0)),
             "value": r2(max((x.max_stock or x.min_stock * 2) - x.current_stock, 0) * x.purchase_price)}
            for x in db.scalars(select(Product).where(Product.track_stock.is_(True), Product.is_active.is_(True),
                                                      Product.current_stock <= Product.min_stock).order_by(Product.name))]
    return make("Low Stock Items", [("code", "Code", "text"), ("name", "Product", "text"), ("unit", "Unit", "text"),
                                    ("stock", "Stock", "num"), ("min", "Min Level", "num"),
                                    ("reorder", "Suggested Reorder", "num"), ("value", "Reorder Value", "money")],
                rows, no_total=("stock", "min", "reorder"))


@report("stock_movement", "Stock Movement Register", "Stock")
def stock_movement(db, f, t, p):
    stmt = select(StockMovement).where(StockMovement.created_at >= day_start(f),
                                       StockMovement.created_at < day_end(t)).order_by(StockMovement.id)
    if p.get("product_id"):
        stmt = stmt.where(StockMovement.product_id == int(p["product_id"]))
    rows = [{"id": m.id, "date": m.created_at.strftime("%d-%m-%Y %H:%M"), "product": m.product.name,
             "type": m.movement_type, "opening": m.opening_qty, "added": m.added_qty, "reduced": m.reduced_qty,
             "closing": m.closing_qty, "ref": m.ref_no, "remarks": m.remarks, "by": m.created_by}
            for m in db.scalars(stmt)]
    return make("Stock Movement Register", [("id", "Txn ID", "text"), ("date", "Date/Time", "date"),
                                            ("product", "Product", "text"), ("type", "Type", "text"),
                                            ("opening", "Opening", "num"), ("added", "Added", "num"),
                                            ("reduced", "Reduced", "num"), ("closing", "Closing", "num"),
                                            ("ref", "Reference", "text"), ("remarks", "Remarks", "text"),
                                            ("by", "Created By", "text")], rows,
                no_total=("opening", "closing", "added", "reduced"))


@report("stock_ledger", "Stock Ledger (period opening / in / out / closing)", "Stock")
def stock_ledger(db, f, t, p):
    rows = []
    for x in db.scalars(select(Product).where(Product.track_stock.is_(True)).order_by(Product.name)):
        ms = list(db.scalars(select(StockMovement).where(StockMovement.product_id == x.id,
                                                         StockMovement.created_at < day_end(t))
                             .order_by(StockMovement.id)))
        before = [m for m in ms if m.created_at < day_start(f)]
        inside = [m for m in ms if m.created_at >= day_start(f)]
        opening = before[-1].closing_qty if before else 0
        by_type = defaultdict(float)
        for m in inside:
            by_type[m.movement_type] += m.added_qty - m.reduced_qty
        closing = inside[-1].closing_qty if inside else opening
        loss = by_type["WASTAGE"] + by_type["DAMAGE"] + by_type["EXPIRY"]
        rows.append({"name": x.name, "unit": x.unit, "opening": round(opening, 3),
                     "purchase": round(by_type["PURCHASE"] + by_type["PURCHASE_RETURN"] + by_type["PURCHASE_CANCEL"], 3),
                     "sales": round(-(by_type["SALE"] + by_type["SALE_CANCEL"] + by_type["SALES_RETURN"]), 3),
                     "loss": round(-loss, 3),
                     "adjust": round(sum(v for k, v in by_type.items() if k in ("ADDITION", "REDUCTION", "CORRECTION",
                                                                              "MANUAL", "RETURN", "RECONCILIATION",
                                                                              "OPENING")), 3),
                     "closing": round(closing, 3), "value": r2(closing * x.purchase_price)})
    return make("Stock Ledger", [("name", "Product", "text"), ("unit", "Unit", "text"),
                                 ("opening", "Opening", "num"), ("purchase", "Purchased (net)", "num"),
                                 ("sales", "Consumed / Sold", "num"), ("loss", "Wastage/Damage/Expiry", "num"),
                                 ("adjust", "Adjustments", "num"), ("closing", "Closing", "num"),
                                 ("value", "Closing Value", "money")], rows,
                no_total=("opening", "purchase", "sales", "loss", "adjust", "closing"))


@report("wastage", "Wastage / Damage / Expiry", "Stock")
def wastage(db, f, t, p):
    stmt = select(StockMovement).where(StockMovement.created_at >= day_start(f), StockMovement.created_at < day_end(t),
                                       StockMovement.movement_type.in_(["WASTAGE", "DAMAGE", "EXPIRY"]))
    rows = [{"date": dstr(m.created_at), "product": m.product.name, "type": m.movement_type, "qty": m.reduced_qty,
             "unit": m.product.unit, "value": r2(m.reduced_qty * m.product.purchase_price), "remarks": m.remarks,
             "by": m.created_by} for m in db.scalars(stmt)]
    return make("Wastage / Damage / Expiry", [("date", "Date", "date"), ("product", "Product", "text"),
                                              ("type", "Type", "text"), ("qty", "Qty", "num"), ("unit", "Unit", "text"),
                                              ("value", "Est. Value", "money"), ("remarks", "Remarks", "text"),
                                              ("by", "By", "text")], rows, no_total=("qty",))


# ======================= FINANCE =======================
@report("expense_register", "Expense Register", "Finance")
def expense_register(db, f, t, p):
    rows = [{"date": dstr(e.expense_date), "category": e.category, "description": e.description,
             "paid_to": e.paid_to, "mode": e.mode, "reference": e.reference, "amount": e.amount}
            for e in db.scalars(select(Expense).where(Expense.expense_date >= f, Expense.expense_date <= t,
                                                      Expense.is_cancelled.is_(False)).order_by(Expense.expense_date))]
    return make("Expense Register", [("date", "Date", "date"), ("category", "Category", "text"),
                                     ("description", "Description", "text"), ("paid_to", "Paid To", "text"),
                                     ("mode", "Mode", "text"), ("reference", "Ref", "text"),
                                     ("amount", "Amount", "money")], rows)


@report("expense_category", "Expense Summary by Category", "Finance")
def expense_category(db, f, t, p):
    acc = {}
    for e in db.scalars(select(Expense).where(Expense.expense_date >= f, Expense.expense_date <= t,
                                              Expense.is_cancelled.is_(False))):
        add(acc, e.category, entries=1, cash=e.amount if e.mode == "CASH" else 0,
            upi=e.amount if e.mode == "UPI" else 0, total=e.amount)
    rows = [{"category": k, **{a: r2(b) for a, b in v.items()}} for k, v in sorted(acc.items(), key=lambda kv: -kv[1]["total"])]
    return make("Expenses by Category", [("category", "Category", "text"), ("entries", "Entries", "num"),
                                         ("cash", "Cash", "money"), ("upi", "UPI", "money"),
                                         ("total", "Total", "money")], rows)


@report("cash_summary", "Day-wise Cash & UPI Summary", "Finance")
def cash_summary(db, f, t, p):
    from .routers.finance import day_summary
    rows = []
    d = f
    while d <= t and len(rows) < 400:
        s = day_summary(db, d)
        if any(s[k] for k in ("cash_sales", "upi_sales", "cash_expenses", "other_cash_in", "other_cash_out",
                              "cash_supplier_payments", "upi_out")) or s["closing"]:
            c = s["closing"] or {}
            rows.append({"date": dstr(d), "opening": s["opening_cash"], "cash_sales": s["cash_sales"],
                         "other_in": s["other_cash_in"], "expenses": s["cash_expenses"],
                         "supplier": s["cash_supplier_payments"], "refunds": s["cash_refunds"],
                         "other_out": s["other_cash_out"], "expected": s["expected_cash"],
                         "actual": c.get("actual_cash", 0), "difference": c.get("difference", 0),
                         "upi_sales": s["upi_sales"], "upi_out": s["upi_out"],
                         "status": c.get("status", "OPEN")})
        d += timedelta(days=1)
    return make("Cash & UPI Summary", [("date", "Date", "date"), ("opening", "Opening", "money"),
                                       ("cash_sales", "Cash Sales", "money"), ("other_in", "Other In", "money"),
                                       ("expenses", "Expenses", "money"), ("supplier", "Supplier Paid", "money"),
                                       ("refunds", "Refunds", "money"), ("other_out", "Other Out", "money"),
                                       ("expected", "Expected Closing", "money"), ("actual", "Actual", "money"),
                                       ("difference", "Difference", "money"), ("upi_sales", "UPI Sales", "money"),
                                       ("upi_out", "UPI Out", "money"), ("status", "Status", "text")], rows,
                no_total=("opening", "expected", "actual"))


@report("daily_closing_report", "Daily Closing Register", "Finance")
def daily_closing_report(db, f, t, p):
    rows = [{"date": dstr(c.closing_date), "opening": c.opening_cash, "expected": c.expected_cash,
             "actual": c.actual_cash, "difference": c.difference, "sales": c.total_sales, "bills": c.total_bills,
             "status": c.status, "by": c.closed_by, "remarks": c.remarks}
            for c in db.scalars(select(DailyClosing).where(DailyClosing.closing_date >= f, DailyClosing.closing_date <= t)
                                .order_by(DailyClosing.closing_date))]
    return make("Daily Closing Register", [("date", "Date", "date"), ("opening", "Opening Cash", "money"),
                                           ("expected", "Expected", "money"), ("actual", "Actual", "money"),
                                           ("difference", "Difference", "money"), ("sales", "Total Sales", "money"),
                                           ("bills", "Bills", "num"), ("status", "Status", "text"),
                                           ("by", "Closed By", "text"), ("remarks", "Remarks", "text")], rows,
                no_total=("opening", "expected", "actual"))


@report("profit_loss", "Profit & Loss Estimate", "Finance")
def profit_loss(db, f, t, p):
    bl = bills(db, f, t)
    cn = notes(db, f, t, "CREDIT")
    sales = sum(b.taxable_amount + b.exempt_amount for b in bl) - sum(n.taxable for n in cn)
    cost = sum(b.cost_amount for b in bl)
    exp_rows = expense_category(db, f, t, p)["rows"]
    expenses = sum(r["total"] for r in exp_rows)
    waste = sum(r["value"] for r in wastage(db, f, t, p)["rows"])
    rows = [{"head": "Net sales (excluding GST, after credit notes)", "amount": r2(sales)},
            {"head": "Less: estimated cost of food sold (recipe / purchase price)", "amount": r2(-cost)},
            {"head": "Gross profit (estimate)", "amount": r2(sales - cost)}]
    rows += [{"head": f"Less expense: {r['category']}", "amount": -r["total"]} for r in exp_rows]
    rows.append({"head": "Wastage / damage / expiry (value, for information)", "amount": r2(-waste)})
    rows.append({"head": "Net profit (estimate, excluding wastage line)", "amount": r2(sales - cost - expenses)})
    return make("Profit & Loss Estimate", [("head", "Particulars", "text"), ("amount", "Amount", "money")], rows,
                no_total=("amount",), notes=["Estimate only. Cost uses current product purchase prices / recipes."])


def catalogue() -> list[dict]:
    return [{k: v for k, v in r.items() if k != "fn"} for r in REGISTRY.values()]
