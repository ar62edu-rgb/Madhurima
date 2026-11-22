"""Shared business helpers: settings, financial years, numbering, stock movements, audit, period locks."""
import json
from datetime import date, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .gst import r2
from .models import (AuditLog, DailyClosing, FinancialYear, MonthlyClosing, Product, Setting,
                     StockMovement, User)

DEFAULT_SETTINGS: dict[str, str] = {
    # restaurant
    "restaurant_name": "Madhurima Family Restaurant",
    "address": "",
    "city": "",
    "pincode": "",
    "phone": "",
    "email": "",
    "gstin": "",
    "fssai": "",
    "state": "Kerala",
    "state_code": "32",
    "gst_registration_type": "REGULAR",  # REGULAR / COMPOSITION / UNREGISTERED
    # billing
    "bill_prefix": "MFR",
    "purchase_prefix": "PUR",
    "credit_note_prefix": "CN",
    "debit_note_prefix": "DN",
    "default_gst_rate": "5",
    "default_hsn": "996331",
    "prices_include_gst": "false",
    "round_off": "true",
    "allow_negative_stock": "true",
    "recipe_stock_deduction": "true",
    "lock_after_daily_closing": "true",
    "invoice_title": "TAX INVOICE",
    "invoice_footer": "Thank you! Visit again.",
    "print_format": "80",  # 58 / 80 / A4
    "print_copies": "1",
    "auto_print_kot": "true",
    "show_upi_qr_text": "",  # UPI ID shown on the bill for customers to pay
    "expense_categories": "Gas / Fuel,Electricity,Water,Salary,Rent,Repairs & Maintenance,Cleaning,"
                          "Transport,Vegetables (petty),Stationery,Internet / Phone,Miscellaneous",
    "cash_entry_categories": "Cash Added,Other Receipt,Owner Drawing,Bank Deposit,Petty Cash,Other Withdrawal",
    "low_stock_alert": "true",
}

INDIAN_STATES = [
    ("01", "Jammu and Kashmir"), ("02", "Himachal Pradesh"), ("03", "Punjab"), ("04", "Chandigarh"),
    ("05", "Uttarakhand"), ("06", "Haryana"), ("07", "Delhi"), ("08", "Rajasthan"), ("09", "Uttar Pradesh"),
    ("10", "Bihar"), ("11", "Sikkim"), ("12", "Arunachal Pradesh"), ("13", "Nagaland"), ("14", "Manipur"),
    ("15", "Mizoram"), ("16", "Tripura"), ("17", "Meghalaya"), ("18", "Assam"), ("19", "West Bengal"),
    ("20", "Jharkhand"), ("21", "Odisha"), ("22", "Chhattisgarh"), ("23", "Madhya Pradesh"), ("24", "Gujarat"),
    ("26", "Dadra and Nagar Haveli and Daman and Diu"), ("27", "Maharashtra"), ("29", "Karnataka"), ("30", "Goa"),
    ("31", "Lakshadweep"), ("32", "Kerala"), ("33", "Tamil Nadu"), ("34", "Puducherry"),
    ("35", "Andaman and Nicobar Islands"), ("36", "Telangana"), ("37", "Andhra Pradesh"), ("38", "Ladakh"),
    ("97", "Other Territory"),
]
STATE_NAMES = dict(INDIAN_STATES)


# ---------- settings ----------
def get_settings(db: Session) -> dict[str, str]:
    out = dict(DEFAULT_SETTINGS)
    for s in db.scalars(select(Setting)):
        out[s.key] = s.value
    return out


def setting_bool(s: dict, key: str) -> bool:
    return str(s.get(key, "")).lower() in ("1", "true", "yes", "on")


def save_settings(db: Session, values: dict):
    for k, v in values.items():
        if k not in DEFAULT_SETTINGS:
            continue
        row = db.get(Setting, k)
        if row:
            row.value = str(v)
        else:
            db.add(Setting(key=k, value=str(v)))


# ---------- financial year ----------
def fy_bounds(d: date) -> tuple[date, date, str]:
    start_year = d.year if d.month >= 4 else d.year - 1
    return date(start_year, 4, 1), date(start_year + 1, 3, 31), f"{start_year}-{str(start_year + 1)[2:]}"


def fy_for_date(db: Session, d: date, lock: bool = False) -> FinancialYear:
    q = select(FinancialYear).where(FinancialYear.start_date <= d, FinancialYear.end_date >= d)
    if lock:
        q = q.with_for_update()
    fy = db.scalars(q).first()
    if not fy:
        start, end, name = fy_bounds(d)
        fy = FinancialYear(name=name, start_date=start, end_date=end)
        db.add(fy)
        db.flush()
        if lock:
            fy = db.scalars(q).first()
    if fy.is_closed:
        raise HTTPException(400, f"Financial year {fy.name} is closed")
    return fy


def next_number(db: Session, d: date, kind: str) -> tuple[FinancialYear, str]:
    """Gap-free sequential numbering per financial year. kind: bill / purchase / credit_note / debit_note."""
    fy = fy_for_date(db, d, lock=True)
    field = f"{kind}_seq"
    setattr(fy, field, getattr(fy, field) + 1)
    s = get_settings(db)
    prefix = s.get(f"{kind}_prefix", kind.upper())
    width = 5 if kind == "bill" else 4
    return fy, f"{prefix}/{fy.name[2:]}/{getattr(fy, field):0{width}d}"


# ---------- period locks ----------
def ensure_period_open(db: Session, d: date, user: User | None = None, what: str = "entry"):
    fy = db.scalars(select(FinancialYear).where(FinancialYear.start_date <= d,
                                                 FinancialYear.end_date >= d)).first()
    if fy and fy.is_closed:
        raise HTTPException(400, f"Financial year {fy.name} is closed; this {what} cannot be changed")
    mc = db.scalars(select(MonthlyClosing).where(MonthlyClosing.year == d.year, MonthlyClosing.month == d.month,
                                                 MonthlyClosing.status == "CLOSED")).first()
    if mc:
        raise HTTPException(400, f"{d:%B %Y} is closed (monthly closing). Reopen it to make this {what}")
    s = get_settings(db)
    if setting_bool(s, "lock_after_daily_closing"):
        dc = db.scalars(select(DailyClosing).where(DailyClosing.closing_date == d,
                                                   DailyClosing.status == "CLOSED")).first()
        if dc:
            raise HTTPException(400, f"Day {d:%d-%m-%Y} is already closed. Reopen it in Daily Closing to make this {what}")


# ---------- stock ----------
def move_stock(db: Session, product: Product, change: float, movement_type: str, ref_no: str = "",
               remarks: str = "", user: str = "", check_negative: bool = True):
    if not change:
        return
    s = get_settings(db)
    opening = r3(product.current_stock)
    closing = r3(opening + change)
    if check_negative and closing < 0 and not setting_bool(s, "allow_negative_stock"):
        raise HTTPException(400, f"Not enough stock for {product.name} (available {opening} {product.unit})")
    product.current_stock = closing
    db.add(StockMovement(product_id=product.id, movement_type=movement_type, opening_qty=opening,
                         added_qty=r3(change) if change > 0 else 0, reduced_qty=r3(-change) if change < 0 else 0,
                         closing_qty=closing, ref_no=ref_no, remarks=remarks[:300], created_by=user))


def r3(x: float) -> float:
    return round(float(x or 0), 3)


# ---------- audit ----------
def audit(db: Session, user: User | str | None, action: str, entity: str = "", entity_id="", details=""):
    name = user.username if isinstance(user, User) else (user or "")
    if not isinstance(details, str):
        details = json.dumps(details, default=str)
    db.add(AuditLog(username=name, action=action, entity=entity, entity_id=str(entity_id), details=details[:4000]))


# ---------- misc ----------
def get_or_404(db: Session, model, obj_id, label: str = "Record"):
    obj = db.get(model, obj_id)
    if not obj:
        raise HTTPException(404, f"{label} not found")
    return obj


def user_can_cancel(user: User) -> bool:
    return user.role in ("admin", "manager") or user.can_cancel_bill

def to_dict(obj, exclude: set[str] | None = None) -> dict:
    out = {}
    for c in obj.__table__.columns:
        if exclude and c.key in exclude:
            continue
        v = getattr(obj, c.key)
        out[c.key] = v.isoformat() if isinstance(v, (date, datetime)) else v
    return out


def parse_range(from_date: str | None, to_date: str | None) -> tuple[date, date]:
    today = date.today()
    f = date.fromisoformat(from_date) if from_date else today
    t = date.fromisoformat(to_date) if to_date else f if from_date else today
    if t < f:
        f, t = t, f
    return f, t


def day_start(d: date) -> datetime:
    return datetime(d.year, d.month, d.day)


def day_end(d: date) -> datetime:
    return day_start(d) + timedelta(days=1)
