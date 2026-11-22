"""Expenses, other cash/UPI entries, cash book, UPI register, daily and monthly closing.

Expected closing cash = Opening cash + Cash sales + Other cash in
                        - Cash expenses - Cash supplier payments - Cash refunds - Other cash out
"""
import calendar
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..gst import r2
from ..models import (Bill, CashEntry, DailyClosing, Expense, MonthlyClosing, Note, Purchase, SupplierPayment,
                      User, now)
from ..security import admin_only, current_user, manager_up
from ..services import (audit, day_end, day_start, ensure_period_open, get_or_404, get_settings, parse_range,
                        to_dict)

router = APIRouter(prefix="/api", tags=["finance"])


def _sum(db: Session, col, *where):
    return r2(db.scalar(select(func.coalesce(func.sum(col), 0)).where(*where)) or 0)


def day_summary(db: Session, d: date) -> dict:
    b_where = (Bill.bill_date >= day_start(d), Bill.bill_date < day_end(d), Bill.status == "ACTIVE")
    prev = db.scalars(select(DailyClosing).where(DailyClosing.closing_date < d)
                      .order_by(DailyClosing.closing_date.desc())).first()
    existing = db.scalars(select(DailyClosing).where(DailyClosing.closing_date == d)).first()
    s = {
        "date": d.isoformat(),
        "previous_closing_date": prev.closing_date.isoformat() if prev else None,
        "carried_forward_cash": prev.actual_cash if prev else 0,
        "cash_sales": _sum(db, Bill.cash_amount, *b_where),
        "upi_sales": _sum(db, Bill.upi_amount, *b_where),
        "total_sales": _sum(db, Bill.grand_total, *b_where),
        "total_tax": _sum(db, Bill.total_tax, *b_where),
        "total_bills": db.scalar(select(func.count(Bill.id)).where(*b_where)) or 0,
        "cancelled_bills": db.scalar(select(func.count(Bill.id)).where(
            Bill.bill_date >= day_start(d), Bill.bill_date < day_end(d), Bill.status == "CANCELLED")) or 0,
        "other_cash_in": _sum(db, CashEntry.amount, CashEntry.entry_date == d, CashEntry.direction == "IN",
                              CashEntry.mode == "CASH", CashEntry.is_cancelled.is_(False)),
        "other_cash_out": _sum(db, CashEntry.amount, CashEntry.entry_date == d, CashEntry.direction == "OUT",
                               CashEntry.mode == "CASH", CashEntry.is_cancelled.is_(False)),
        "upi_in_other": _sum(db, CashEntry.amount, CashEntry.entry_date == d, CashEntry.direction == "IN",
                             CashEntry.mode == "UPI", CashEntry.is_cancelled.is_(False)),
        "cash_expenses": _sum(db, Expense.amount, Expense.expense_date == d, Expense.mode == "CASH",
                              Expense.is_cancelled.is_(False)),
        "upi_expenses": _sum(db, Expense.amount, Expense.expense_date == d, Expense.mode == "UPI",
                             Expense.is_cancelled.is_(False)),
        "cash_supplier_payments": _sum(db, SupplierPayment.amount, SupplierPayment.payment_date == d,
                                       SupplierPayment.mode == "CASH", SupplierPayment.is_cancelled.is_(False)),
        "upi_supplier_payments": _sum(db, SupplierPayment.amount, SupplierPayment.payment_date == d,
                                      SupplierPayment.mode == "UPI", SupplierPayment.is_cancelled.is_(False)),
        "cash_refunds": _sum(db, Note.total, Note.note_date == d, Note.note_type == "CREDIT",
                             Note.settlement_mode == "CASH"),
        "upi_refunds": _sum(db, Note.total, Note.note_date == d, Note.note_type == "CREDIT",
                            Note.settlement_mode == "UPI"),
        "supplier_refunds_cash": _sum(db, Note.total, Note.note_date == d, Note.note_type == "DEBIT",
                                      Note.settlement_mode == "CASH"),
        "upi_out_other": _sum(db, CashEntry.amount, CashEntry.entry_date == d, CashEntry.direction == "OUT",
                              CashEntry.mode == "UPI", CashEntry.is_cancelled.is_(False)),
        "closing": to_dict(existing) if existing else None,
    }
    s["other_cash_in"] = r2(s["other_cash_in"] + s["supplier_refunds_cash"])
    s["opening_cash"] = existing.opening_cash if existing else s["carried_forward_cash"]
    s["expected_cash"] = expected_cash(s, s["opening_cash"])
    s["upi_out"] = r2(s["upi_expenses"] + s["upi_supplier_payments"] + s["upi_refunds"] + s["upi_out_other"])
    s["upi_net"] = r2(s["upi_sales"] + s["upi_in_other"] - s["upi_out"])
    return s


def expected_cash(s: dict, opening: float) -> float:
    return r2(opening + s["cash_sales"] + s["other_cash_in"] - s["cash_expenses"] - s["cash_supplier_payments"]
              - s["cash_refunds"] - s["other_cash_out"])


# ---------------- expenses ----------------
class ExpenseIn(BaseModel):
    expense_date: date
    category: str = Field(min_length=1, max_length=60)
    description: str = ""
    paid_to: str = ""
    amount: float = Field(gt=0)
    mode: str = Field(pattern="^(CASH|UPI)$")
    reference: str = ""


@router.get("/expenses")
def list_expenses(from_date: str | None = None, to_date: str | None = None, category: str = "",
                  _: User = Depends(current_user), db: Session = Depends(get_db)):
    f, t = parse_range(from_date, to_date)
    stmt = select(Expense).where(Expense.expense_date >= f, Expense.expense_date <= t).order_by(Expense.id.desc())
    if category:
        stmt = stmt.where(Expense.category == category)
    return [to_dict(e) for e in db.scalars(stmt)]


@router.post("/expenses")
def create_expense(body: ExpenseIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ensure_period_open(db, body.expense_date, user, "expense")
    e = Expense(**body.model_dump(), created_by=user.username)
    e.amount = r2(e.amount)
    db.add(e)
    audit(db, user, "CREATE_EXPENSE", "expense", "", body.model_dump(mode="json"))
    db.commit()
    return to_dict(e)


@router.post("/expenses/{eid}/cancel")
def cancel_expense(eid: int, user: User = Depends(manager_up), db: Session = Depends(get_db)):
    e = get_or_404(db, Expense, eid, "Expense")
    ensure_period_open(db, e.expense_date, user, "cancellation")
    e.is_cancelled = True
    audit(db, user, "CANCEL_EXPENSE", "expense", eid)
    db.commit()
    return to_dict(e)


# ---------------- other cash / UPI entries ----------------
class CashEntryIn(BaseModel):
    entry_date: date
    direction: str = Field(pattern="^(IN|OUT)$")
    mode: str = Field("CASH", pattern="^(CASH|UPI)$")
    category: str = Field(min_length=1, max_length=60)
    amount: float = Field(gt=0)
    reference: str = ""
    remarks: str = ""


@router.get("/cash-entries")
def list_cash_entries(from_date: str | None = None, to_date: str | None = None, _: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    f, t = parse_range(from_date, to_date)
    stmt = select(CashEntry).where(CashEntry.entry_date >= f, CashEntry.entry_date <= t).order_by(CashEntry.id.desc())
    return [to_dict(e) for e in db.scalars(stmt)]


@router.post("/cash-entries")
def create_cash_entry(body: CashEntryIn, user: User = Depends(manager_up), db: Session = Depends(get_db)):
    ensure_period_open(db, body.entry_date, user, "cash entry")
    e = CashEntry(**body.model_dump(), created_by=user.username)
    e.amount = r2(e.amount)
    db.add(e)
    audit(db, user, "CASH_ENTRY", "cash_entry", "", body.model_dump(mode="json"))
    db.commit()
    return to_dict(e)


@router.post("/cash-entries/{eid}/cancel")
def cancel_cash_entry(eid: int, user: User = Depends(manager_up), db: Session = Depends(get_db)):
    e = get_or_404(db, CashEntry, eid, "Entry")
    ensure_period_open(db, e.entry_date, user, "cancellation")
    e.is_cancelled = True
    audit(db, user, "CANCEL_CASH_ENTRY", "cash_entry", eid)
    db.commit()
    return to_dict(e)


# ---------------- cash book & UPI register ----------------
@router.get("/cash-book")
def cash_book(day: str | None = None, _: User = Depends(current_user), db: Session = Depends(get_db)):
    d = date.fromisoformat(day) if day else date.today()
    s = day_summary(db, d)
    txns = []
    for b in db.scalars(select(Bill).where(Bill.bill_date >= day_start(d), Bill.bill_date < day_end(d),
                                           Bill.status == "ACTIVE", Bill.cash_amount > 0).order_by(Bill.id)):
        txns.append({"time": b.bill_date.isoformat(), "type": "Cash sale", "ref": b.bill_no, "in": b.cash_amount,
                     "out": 0})
    for e in db.scalars(select(CashEntry).where(CashEntry.entry_date == d, CashEntry.mode == "CASH",
                                                CashEntry.is_cancelled.is_(False))):
        txns.append({"time": e.created_at.isoformat(), "type": e.category, "ref": e.remarks,
                     "in": e.amount if e.direction == "IN" else 0, "out": e.amount if e.direction == "OUT" else 0})
    for e in db.scalars(select(Expense).where(Expense.expense_date == d, Expense.mode == "CASH",
                                              Expense.is_cancelled.is_(False))):
        txns.append({"time": e.created_at.isoformat(), "type": f"Expense: {e.category}",
                     "ref": e.description or e.paid_to, "in": 0, "out": e.amount})
    for p in db.scalars(select(SupplierPayment).where(SupplierPayment.payment_date == d,
                                                      SupplierPayment.mode == "CASH",
                                                      SupplierPayment.is_cancelled.is_(False))):
        txns.append({"time": p.created_at.isoformat(), "type": "Supplier payment", "ref": p.supplier.name,
                     "in": 0, "out": p.amount})
    for n in db.scalars(select(Note).where(Note.note_date == d, Note.settlement_mode == "CASH")):
        credit = n.note_type == "CREDIT"
        txns.append({"time": n.created_at.isoformat(), "type": "Sales refund" if credit else "Supplier refund",
                     "ref": n.note_no, "in": 0 if credit else n.total, "out": n.total if credit else 0})
    txns.sort(key=lambda x: x["time"])
    bal = s["opening_cash"]
    for t in txns:
        bal = r2(bal + t["in"] - t["out"])
        t["balance"] = bal
    return {"summary": s, "transactions": txns}


@router.get("/upi-transactions")
def upi_transactions(from_date: str | None = None, to_date: str | None = None, _: User = Depends(current_user),
                     db: Session = Depends(get_db)):
    f, t = parse_range(from_date, to_date)
    rows = []
    for b in db.scalars(select(Bill).where(Bill.bill_date >= day_start(f), Bill.bill_date < day_end(t),
                                           Bill.status == "ACTIVE", Bill.upi_amount > 0).order_by(Bill.id)):
        rows.append({"date": b.bill_date.isoformat(), "direction": "IN", "type": "Sale", "ref_no": b.bill_no,
                     "upi_ref": b.upi_ref, "party": b.customer_name, "amount": b.upi_amount,
                     "verified": b.upi_verified, "bill_id": b.id})
    for e in db.scalars(select(CashEntry).where(CashEntry.entry_date >= f, CashEntry.entry_date <= t,
                                                CashEntry.mode == "UPI", CashEntry.is_cancelled.is_(False))):
        rows.append({"date": e.entry_date.isoformat(), "direction": e.direction, "type": e.category,
                     "ref_no": "", "upi_ref": e.reference, "party": e.remarks, "amount": e.amount})
    for e in db.scalars(select(Expense).where(Expense.expense_date >= f, Expense.expense_date <= t,
                                              Expense.mode == "UPI", Expense.is_cancelled.is_(False))):
        rows.append({"date": e.expense_date.isoformat(), "direction": "OUT", "type": f"Expense: {e.category}",
                     "ref_no": "", "upi_ref": e.reference, "party": e.paid_to, "amount": e.amount})
    for p in db.scalars(select(SupplierPayment).where(SupplierPayment.payment_date >= f,
                                                      SupplierPayment.payment_date <= t,
                                                      SupplierPayment.mode == "UPI",
                                                      SupplierPayment.is_cancelled.is_(False))):
        rows.append({"date": p.payment_date.isoformat(), "direction": "OUT", "type": "Supplier payment",
                     "ref_no": "", "upi_ref": p.reference, "party": p.supplier.name, "amount": p.amount})
    for n in db.scalars(select(Note).where(Note.note_date >= f, Note.note_date <= t, Note.settlement_mode == "UPI")):
        credit = n.note_type == "CREDIT"
        rows.append({"date": n.note_date.isoformat(), "direction": "OUT" if credit else "IN",
                     "type": "Sales refund" if credit else "Supplier refund", "ref_no": n.note_no,
                     "upi_ref": n.settlement_ref, "party": n.party_name, "amount": n.total})
    rows.sort(key=lambda r: r["date"])
    total_in = r2(sum(r["amount"] for r in rows if r["direction"] == "IN"))
    total_out = r2(sum(r["amount"] for r in rows if r["direction"] == "OUT"))
    unverified = r2(sum(r["amount"] for r in rows if r.get("verified") is False))
    return {"rows": rows, "total_in": total_in, "total_out": total_out, "net": r2(total_in - total_out),
            "unverified_sales": unverified}


# ---------------- daily closing ----------------
@router.get("/daily-closing")
def get_daily(day: str | None = None, _: User = Depends(current_user), db: Session = Depends(get_db)):
    return day_summary(db, date.fromisoformat(day) if day else date.today())


@router.get("/daily-closings")
def list_daily(from_date: str | None = None, to_date: str | None = None, _: User = Depends(current_user),
               db: Session = Depends(get_db)):
    f, t = parse_range(from_date or (date.today() - timedelta(days=31)).isoformat(), to_date)
    stmt = select(DailyClosing).where(DailyClosing.closing_date >= f, DailyClosing.closing_date <= t) \
        .order_by(DailyClosing.closing_date.desc())
    return [to_dict(c) for c in db.scalars(stmt)]


class DailyCloseIn(BaseModel):
    closing_date: date
    opening_cash: float = Field(ge=0)
    actual_cash: float = Field(ge=0)
    remarks: str = ""


@router.post("/daily-closing")
def close_day(body: DailyCloseIn, user: User = Depends(manager_up), db: Session = Depends(get_db)):
    if body.closing_date > date.today():
        raise HTTPException(400, "Cannot close a future date")
    if db.scalars(select(MonthlyClosing).where(MonthlyClosing.year == body.closing_date.year,
                                               MonthlyClosing.month == body.closing_date.month,
                                               MonthlyClosing.status == "CLOSED")).first():
        raise HTTPException(400, "This month is already closed")
    if db.scalars(select(DailyClosing).where(DailyClosing.closing_date > body.closing_date,
                                             DailyClosing.status == "CLOSED")).first():
        raise HTTPException(400, "A later day is already closed; reopen it first")
    s = day_summary(db, body.closing_date)
    dc = db.scalars(select(DailyClosing).where(DailyClosing.closing_date == body.closing_date)).first()
    if dc and dc.status == "CLOSED":
        raise HTTPException(400, "This day is already closed")
    if not dc:
        dc = DailyClosing(closing_date=body.closing_date)
        db.add(dc)
    exp = expected_cash(s, body.opening_cash)
    for k in ("cash_sales", "other_cash_in", "cash_expenses", "cash_supplier_payments", "cash_refunds",
              "other_cash_out", "upi_sales", "upi_in_other", "upi_out", "total_sales", "total_tax", "total_bills",
              "cancelled_bills"):
        setattr(dc, k, s[k])
    dc.opening_cash, dc.expected_cash, dc.actual_cash = r2(body.opening_cash), exp, r2(body.actual_cash)
    dc.difference = r2(body.actual_cash - exp)
    dc.remarks, dc.status, dc.closed_by, dc.closed_at = body.remarks, "CLOSED", user.username, now()
    audit(db, user, "DAILY_CLOSING", "daily_closing", body.closing_date, {"expected": exp, "actual": body.actual_cash})
    db.commit()
    try:
        from .backup import create_backup
        create_backup(db, "auto")
    except Exception:  # backup failure must never block closing
        pass
    return to_dict(dc)


@router.post("/daily-closing/{day}/reopen")
def reopen_day(day: str, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    d = date.fromisoformat(day)
    dc = db.scalars(select(DailyClosing).where(DailyClosing.closing_date == d)).first()
    if not dc:
        raise HTTPException(404, "Day is not closed")
    if db.scalars(select(MonthlyClosing).where(MonthlyClosing.year == d.year, MonthlyClosing.month == d.month,
                                               MonthlyClosing.status == "CLOSED")).first():
        raise HTTPException(400, "Reopen the month first")
    dc.status = "REOPENED"
    audit(db, user, "REOPEN_DAY", "daily_closing", day)
    db.commit()
    return to_dict(dc)


# ---------------- monthly closing ----------------
def month_summary(db: Session, year: int, month: int) -> dict:
    f = date(year, month, 1)
    t = date(year, month, calendar.monthrange(year, month)[1])
    bw = (Bill.bill_date >= day_start(f), Bill.bill_date < day_end(t), Bill.status == "ACTIVE")
    cn = (Note.note_type == "CREDIT", Note.note_date >= f, Note.note_date <= t)
    pw = (Purchase.invoice_date >= f, Purchase.invoice_date <= t, Purchase.status == "ACTIVE")
    dn = (Note.note_type == "DEBIT", Note.note_date >= f, Note.note_date <= t)
    out = {
        "year": year, "month": month, "from": f.isoformat(), "to": t.isoformat(),
        "total_sales": r2(_sum(db, Bill.grand_total, *bw) - _sum(db, Note.total, *cn)),
        "taxable_sales": r2(_sum(db, Bill.taxable_amount, *bw) - _sum(db, Note.taxable, *cn)),
        "output_cgst": r2(_sum(db, Bill.cgst, *bw) - _sum(db, Note.cgst, *cn)),
        "output_sgst": r2(_sum(db, Bill.sgst, *bw) - _sum(db, Note.sgst, *cn)),
        "output_igst": r2(_sum(db, Bill.igst, *bw) - _sum(db, Note.igst, *cn)),
        "purchases": r2(_sum(db, Purchase.grand_total, *pw) - _sum(db, Note.total, *dn)),
        "input_gst": r2(_sum(db, Purchase.total_tax, *pw) - _sum(db, Note.cgst + Note.sgst + Note.igst, *dn)),
        "expenses": _sum(db, Expense.amount, Expense.expense_date >= f, Expense.expense_date <= t,
                         Expense.is_cancelled.is_(False)),
        "cash_sales": _sum(db, Bill.cash_amount, *bw),
        "upi_sales": _sum(db, Bill.upi_amount, *bw),
        "cost_of_sales": _sum(db, Bill.cost_amount, *bw),
        "total_bills": db.scalar(select(func.count(Bill.id)).where(*bw)) or 0,
    }
    exempt = _sum(db, Bill.exempt_amount, *bw)
    out["profit_estimate"] = r2(out["taxable_sales"] + exempt - out["cost_of_sales"] - out["expenses"])
    days = {c.closing_date for c in db.scalars(select(DailyClosing).where(
        DailyClosing.closing_date >= f, DailyClosing.closing_date <= t, DailyClosing.status == "CLOSED"))}
    bill_days = {b.date() for b in db.scalars(select(Bill.bill_date).where(*bw))}
    out["unclosed_days"] = sorted(d.isoformat() for d in bill_days - days)
    mc = db.scalars(select(MonthlyClosing).where(MonthlyClosing.year == year, MonthlyClosing.month == month)).first()
    out["closing"] = to_dict(mc) if mc else None
    return out


@router.get("/monthly-closing")
def get_month(year: int, month: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    return month_summary(db, year, month)


@router.get("/monthly-closings")
def list_months(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return [to_dict(m) for m in db.scalars(select(MonthlyClosing).order_by(MonthlyClosing.year.desc(),
                                                                          MonthlyClosing.month.desc()))]


class MonthCloseIn(BaseModel):
    year: int
    month: int = Field(ge=1, le=12)
    remarks: str = ""


@router.post("/monthly-closing")
def close_month(body: MonthCloseIn, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    last = date(body.year, body.month, calendar.monthrange(body.year, body.month)[1])
    if last >= date.today():
        raise HTTPException(400, "A month can be closed only after it ends")
    s = month_summary(db, body.year, body.month)
    if s["unclosed_days"]:
        raise HTTPException(400, f"Close these days first: {', '.join(s['unclosed_days'][:10])}")
    mc = db.scalars(select(MonthlyClosing).where(MonthlyClosing.year == body.year,
                                                 MonthlyClosing.month == body.month)).first()
    if mc and mc.status == "CLOSED":
        raise HTTPException(400, "Month is already closed")
    if not mc:
        mc = MonthlyClosing(year=body.year, month=body.month)
        db.add(mc)
    for k in ("total_sales", "taxable_sales", "output_cgst", "output_sgst", "output_igst", "purchases", "input_gst",
              "expenses", "cash_sales", "upi_sales", "cost_of_sales", "profit_estimate", "total_bills"):
        setattr(mc, k, s[k])
    mc.remarks, mc.status, mc.closed_by, mc.closed_at = body.remarks, "CLOSED", user.username, now()
    audit(db, user, "MONTHLY_CLOSING", "monthly_closing", f"{body.year}-{body.month:02d}")
    db.commit()
    return to_dict(mc)


@router.post("/monthly-closing/{year}/{month}/reopen")
def reopen_month(year: int, month: int, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    mc = db.scalars(select(MonthlyClosing).where(MonthlyClosing.year == year, MonthlyClosing.month == month)).first()
    if not mc:
        raise HTTPException(404, "Month is not closed")
    mc.status = "REOPENED"
    audit(db, user, "REOPEN_MONTH", "monthly_closing", f"{year}-{month:02d}")
    db.commit()
    return to_dict(mc)
