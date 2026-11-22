import calendar
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..gst import r2
from ..models import Bill, BillItem, Expense, Note, Product, Purchase, Supplier, User
from ..security import current_user
from ..services import day_end, day_start, parse_range
from .masters import supplier_balance

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _month_add(d: date, n: int) -> date:
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


@router.get("")
def dashboard(from_date: str | None = None, to_date: str | None = None, _: User = Depends(current_user),
              db: Session = Depends(get_db)):
    f, t = parse_range(from_date, to_date)
    rng = (Bill.bill_date >= day_start(f), Bill.bill_date < day_end(t))
    active = list(db.scalars(select(Bill).where(*rng, Bill.status == "ACTIVE")))
    cancelled = db.scalar(select(func.count(Bill.id)).where(*rng, Bill.status == "CANCELLED")) or 0
    cn_total = db.scalar(select(func.coalesce(func.sum(Note.total), 0)).where(
        Note.note_type == "CREDIT", Note.note_date >= f, Note.note_date <= t)) or 0
    purchases = list(db.scalars(select(Purchase).where(Purchase.invoice_date >= f, Purchase.invoice_date <= t,
                                                       Purchase.status == "ACTIVE")))
    expenses = list(db.scalars(select(Expense).where(Expense.expense_date >= f, Expense.expense_date <= t,
                                                     Expense.is_cancelled.is_(False))))
    tracked = list(db.scalars(select(Product).where(Product.track_stock.is_(True), Product.is_active.is_(True))))
    low = sorted([p for p in tracked if p.current_stock <= p.min_stock], key=lambda p: p.current_stock - p.min_stock)
    outstanding = sum(max(supplier_balance(db, s.id)["outstanding"], 0)
                      for s in db.scalars(select(Supplier).where(Supplier.is_active.is_(True))))

    sales = sum(b.grand_total for b in active)
    net_sales_ex_tax = sum(b.taxable_amount + b.exempt_amount for b in active)
    cost = sum(b.cost_amount for b in active)
    exp_total = sum(e.amount for e in expenses)
    cards = {
        "total_sales": r2(sales - cn_total), "cash_sales": r2(sum(b.cash_amount for b in active)),
        "upi_sales": r2(sum(b.upi_amount for b in active)),
        "gst_collected": r2(sum(b.total_tax for b in active)),
        "cgst": r2(sum(b.cgst for b in active)), "sgst": r2(sum(b.sgst for b in active)),
        "igst": r2(sum(b.igst for b in active)),
        "purchase_amount": r2(sum(p.grand_total for p in purchases)), "expenses": r2(exp_total),
        "stock_value": r2(sum(max(p.current_stock, 0) * p.purchase_price for p in tracked)),
        "low_stock_count": len(low), "total_bills": len(active), "cancelled_bills": cancelled,
        "credit_notes": r2(cn_total), "profit_estimate": r2(net_sales_ex_tax - cost - exp_total),
        "outstanding_supplier": r2(outstanding),
        "average_bill": r2(sales / len(active)) if active else 0,
    }

    # daily series in the range (max 120 days, else monthly is more useful)
    daily = defaultdict(lambda: {"sales": 0, "cash": 0, "upi": 0, "bills": 0})
    for b in active:
        d = daily[b.bill_date.date().isoformat()]
        d["sales"] += b.grand_total
        d["cash"] += b.cash_amount
        d["upi"] += b.upi_amount
        d["bills"] += 1
    daily_series = []
    if (t - f).days <= 120:
        d = f
        while d <= t:
            v = daily.get(d.isoformat(), {"sales": 0, "cash": 0, "upi": 0, "bills": 0})
            daily_series.append({"date": d.isoformat(), **{k: r2(x) for k, x in v.items()}})
            d += timedelta(days=1)

    # last 12 months ending at 'to' — sales, purchases, expenses, GST
    start = _month_add(date(t.year, t.month, 1), -11)
    m_end = date(t.year, t.month, calendar.monthrange(t.year, t.month)[1])
    months = {}
    for i in range(12):
        m = _month_add(start, i)
        months[(m.year, m.month)] = {"month": m.strftime("%b %y"), "sales": 0, "purchases": 0, "expenses": 0,
                                     "gst": 0, "cash": 0, "upi": 0}
    for b in db.scalars(select(Bill).where(Bill.bill_date >= day_start(start), Bill.bill_date < day_end(m_end),
                                           Bill.status == "ACTIVE")):
        m = months[(b.bill_date.year, b.bill_date.month)]
        m["sales"] += b.grand_total
        m["gst"] += b.total_tax
        m["cash"] += b.cash_amount
        m["upi"] += b.upi_amount
    for p in db.scalars(select(Purchase).where(Purchase.invoice_date >= start, Purchase.invoice_date <= m_end,
                                               Purchase.status == "ACTIVE")):
        months[(p.invoice_date.year, p.invoice_date.month)]["purchases"] += p.grand_total
    for e in db.scalars(select(Expense).where(Expense.expense_date >= start, Expense.expense_date <= m_end,
                                              Expense.is_cancelled.is_(False))):
        months[(e.expense_date.year, e.expense_date.month)]["expenses"] += e.amount
    monthly = [{k: (r2(v) if isinstance(v, float) else v) for k, v in m.items()} for m in months.values()]

    top = db.execute(select(BillItem.item_name, func.sum(BillItem.qty), func.sum(BillItem.total))
                     .join(Bill, Bill.id == BillItem.bill_id).where(*rng, Bill.status == "ACTIVE")
                     .group_by(BillItem.item_name).order_by(func.sum(BillItem.total).desc()).limit(10)).all()
    exp_cat = defaultdict(float)
    for e in expenses:
        exp_cat[e.category] += e.amount

    return {
        "from": f.isoformat(), "to": t.isoformat(), "cards": cards, "daily": daily_series, "monthly": monthly,
        "payment_split": [{"name": "Cash", "value": cards["cash_sales"]}, {"name": "UPI", "value": cards["upi_sales"]}],
        "gst_split": [{"name": "CGST", "value": cards["cgst"]}, {"name": "SGST", "value": cards["sgst"]},
                      {"name": "IGST", "value": cards["igst"]}],
        "top_items": [{"name": n, "qty": round(q or 0, 2), "amount": r2(a or 0)} for n, q, a in top],
        "expense_by_category": [{"name": k, "value": r2(v)} for k, v in sorted(exp_cat.items(), key=lambda x: -x[1])],
        "low_stock": [{"id": p.id, "name": p.name, "unit": p.unit, "stock": p.current_stock, "min": p.min_stock}
                      for p in low[:15]],
    }
