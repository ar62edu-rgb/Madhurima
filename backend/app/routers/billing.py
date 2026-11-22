"""POS billing: preview, create, list, cancel, reprint, running orders (tables/KOT), credit notes."""
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..gst import Line, compute, r2
from ..models import (Bill, BillItem, Customer, DiningTable, HeldOrder, Note, NoteItem, Product, RecipeItem, User,
                      now)
from ..security import current_user, manager_up
from ..services import (STATE_NAMES, audit, day_end, day_start, ensure_period_open, get_or_404, get_settings,
                        move_stock, next_number, parse_range, setting_bool, to_dict, user_can_cancel)

router = APIRouter(prefix="/api", tags=["billing"])


class BillLineIn(BaseModel):
    product_id: int
    qty: float = Field(gt=0)
    rate: float | None = Field(None, ge=0)
    discount: float = Field(0, ge=0)


class BillIn(BaseModel):
    items: list[BillLineIn] = Field(min_length=1)
    bill_discount: float = Field(0, ge=0)
    customer_id: int | None = None
    customer_name: str = ""
    customer_phone: str = ""
    customer_gstin: str = ""
    customer_address: str = ""
    customer_state_code: str = ""
    supply_type: str = Field("AUTO", pattern="^(AUTO|INTRA|INTER)$")
    order_type: str = Field("DINE_IN", pattern="^(DINE_IN|TAKEAWAY|DELIVERY)$")
    table_name: str = ""
    held_order_id: int | None = None
    cash_amount: float = Field(0, ge=0)
    upi_amount: float = Field(0, ge=0)
    upi_ref: str = ""
    cash_tendered: float = Field(0, ge=0)
    notes: str = ""


def _build(db: Session, body: BillIn, user: User, lock: bool = False):
    s = get_settings(db)
    regular = s.get("gst_registration_type", "REGULAR") == "REGULAR"
    inclusive = setting_bool(s, "prices_include_gst")

    customer = db.get(Customer, body.customer_id) if body.customer_id else None
    gstin = (body.customer_gstin or (customer.gstin if customer else "")).strip().upper()
    if gstin and len(gstin) != 15:
        raise HTTPException(400, "Customer GSTIN must be 15 characters")
    pos = (gstin[:2] if gstin else "") or body.customer_state_code or (customer.state_code if customer else "") \
        or s.get("state_code", "")
    if body.supply_type == "AUTO":
        inter = bool(pos and s.get("state_code") and pos != s.get("state_code"))
    else:
        inter = body.supply_type == "INTER"

    can_price = user.role == "admin" or user.can_edit_price
    can_disc = user.role in ("admin", "manager") or user.can_discount
    lines, products = [], []
    for it in body.items:
        q = select(Product).where(Product.id == it.product_id)
        p = db.scalars(q.with_for_update() if lock else q).first()
        if not p or not p.is_active:
            raise HTTPException(400, f"Product #{it.product_id} is not available")
        rate = p.selling_price if it.rate is None else it.rate
        if abs(rate - p.selling_price) > 0.001 and not can_price:
            raise HTTPException(403, f"You are not allowed to change the price of {p.name}")
        if it.discount and not can_disc:
            raise HTTPException(403, "You are not allowed to give discounts")
        lines.append(Line(qty=it.qty, rate=rate, discount=it.discount,
                          gst_rate=p.gst_rate if regular else 0,
                          tax_category=p.tax_category if regular else "EXEMPT"))
        products.append(p)
    if body.bill_discount and not can_disc:
        raise HTTPException(403, "You are not allowed to give discounts")
    try:
        totals = compute(lines, body.bill_discount, inclusive, inter, setting_bool(s, "round_off"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return s, customer, gstin, pos, inter, inclusive, lines, products, totals


@router.post("/bills/preview")
def preview(body: BillIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _, _, _, pos, inter, inclusive, lines, products, t = _build(db, body, user)
    return {
        "supply_type": "INTER" if inter else "INTRA", "place_of_supply": pos, "prices_include_gst": inclusive,
        "totals": t.__dict__,
        "lines": [{"product_id": p.id, "name": p.name, "qty": ln.qty, "rate": ln.rate, "gross": ln.gross,
                   "discount": ln.discount, "bill_discount_share": ln.bill_discount_share, "taxable": ln.taxable,
                   "gst_rate": ln.gst_rate, "cgst": ln.cgst, "sgst": ln.sgst, "igst": ln.igst, "total": ln.total}
                  for ln, p in zip(lines, products)],
    }


def _deduct_for_sale(db: Session, p: Product, qty: float, ref: str, user: str, s: dict, sign: int = -1,
                     mtype: str = "SALE") -> float:
    """Deduct stock (or recipe ingredients) for a sale; returns cost of goods. sign=+1 reverses."""
    recipe = list(db.scalars(select(RecipeItem).where(RecipeItem.product_id == p.id))) \
        if p.use_recipe and setting_bool(s, "recipe_stock_deduction") else []
    cost = 0.0
    if recipe:
        for r in recipe:
            ing = db.scalars(select(Product).where(Product.id == r.ingredient_id).with_for_update()).first()
            use = round(r.quantity * qty, 3)
            cost += use * (ing.purchase_price or 0)
            move_stock(db, ing, sign * use, mtype, ref, f"Recipe: {p.name} x {qty:g}", user, sign < 0)
    else:
        cost = qty * (p.purchase_price or 0)
        if p.track_stock:
            move_stock(db, p, sign * qty, mtype, ref, "", user, sign < 0)
    return r2(cost)


@router.post("/bills")
def create_bill(body: BillIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    today = date.today()
    ensure_period_open(db, today, user, "bill")
    s, customer, gstin, pos, inter, inclusive, lines, products, t = _build(db, body, user, lock=True)

    cash, upi = r2(body.cash_amount), r2(body.upi_amount)
    if abs(cash + upi - t.grand_total) > 0.009:
        raise HTTPException(400, f"Payment total ₹{cash + upi:.2f} does not match bill amount ₹{t.grand_total:.2f}")
    if body.cash_tendered and body.cash_tendered < cash:
        raise HTTPException(400, "Cash received is less than the cash amount")

    fy, bill_no = next_number(db, today, "bill")
    mode = "SPLIT" if cash and upi else ("UPI" if upi else "CASH")
    bill = Bill(
        bill_no=bill_no, fy_id=fy.id, bill_date=now(), order_type=body.order_type, table_name=body.table_name,
        customer_id=customer.id if customer else None,
        customer_name=body.customer_name or (customer.name if customer else ""),
        customer_phone=body.customer_phone or (customer.phone if customer else ""),
        customer_gstin=gstin, customer_address=body.customer_address or (customer.address if customer else ""),
        place_of_supply=pos, supply_type="INTER" if inter else "INTRA", invoice_type="B2B" if gstin else "B2C",
        prices_include_gst=inclusive, gross_amount=t.gross, item_discount=t.item_discount,
        bill_discount=t.bill_discount, taxable_amount=t.taxable, exempt_amount=t.exempt, cgst=t.cgst, sgst=t.sgst,
        igst=t.igst, total_tax=t.total_tax, round_off=t.round_off, grand_total=t.grand_total, payment_mode=mode,
        cash_amount=cash, upi_amount=upi, upi_ref=body.upi_ref.strip(), cash_tendered=body.cash_tendered or cash,
        change_returned=r2(max((body.cash_tendered or cash) - cash, 0)), notes=body.notes,
        created_by=user.username)
    db.add(bill)
    db.flush()
    total_cost = 0.0
    for ln, p in zip(lines, products):
        cost = _deduct_for_sale(db, p, ln.qty, bill_no, user.username, s)
        total_cost += cost
        bill.items.append(BillItem(
            product_id=p.id, item_name=p.name, hsn=p.hsn or s.get("default_hsn", ""), unit=p.unit, qty=ln.qty,
            rate=ln.rate, gross=ln.gross, discount=ln.discount, bill_discount_share=ln.bill_discount_share,
            taxable=ln.taxable, gst_rate=ln.gst_rate, tax_category=ln.tax_category, cgst=ln.cgst, sgst=ln.sgst,
            igst=ln.igst, total=ln.total, cost=cost))
    bill.cost_amount = r2(total_cost)
    if body.held_order_id:
        held = db.get(HeldOrder, body.held_order_id)
        if held:
            db.delete(held)
    audit(db, user, "CREATE_BILL", "bill", bill_no, {"total": t.grand_total, "mode": mode})
    db.commit()
    return bill_out(db, bill)


def bill_out(db: Session, b: Bill) -> dict:
    d = to_dict(b)
    d["items"] = [to_dict(i) for i in b.items]
    d["place_of_supply_name"] = STATE_NAMES.get(b.place_of_supply, "")
    d["credit_notes"] = [to_dict(n) for n in db.scalars(select(Note).where(Note.bill_id == b.id))]
    # GST breakup by rate for the invoice
    rates: dict[float, dict] = {}
    for i in b.items:
        r = rates.setdefault(i.gst_rate, {"gst_rate": i.gst_rate, "taxable": 0, "cgst": 0, "sgst": 0, "igst": 0})
        for k in ("taxable", "cgst", "sgst", "igst"):
            r[k] = r2(r[k] + getattr(i, k))
    d["gst_breakup"] = sorted(rates.values(), key=lambda x: x["gst_rate"])
    return d


@router.get("/bills")
def list_bills(from_date: str | None = None, to_date: str | None = None, q: str = "", status: str = "",
               payment_mode: str = "", _: User = Depends(current_user), db: Session = Depends(get_db)):
    f, t = parse_range(from_date, to_date)
    stmt = select(Bill).where(Bill.bill_date >= day_start(f), Bill.bill_date < day_end(t)) \
        .order_by(Bill.id.desc()).limit(3000)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Bill.bill_no).like(like), func.lower(Bill.customer_name).like(like),
                              Bill.customer_phone.like(like), func.lower(Bill.upi_ref).like(like)))
    if status:
        stmt = stmt.where(Bill.status == status)
    if payment_mode:
        stmt = stmt.where(Bill.payment_mode == payment_mode)
    return [to_dict(b) for b in db.scalars(stmt)]


@router.get("/bills/{bid}")
def get_bill(bid: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    return bill_out(db, get_or_404(db, Bill, bid, "Bill"))


@router.get("/bills/by-number/{bill_no:path}")
def get_bill_by_no(bill_no: str, _: User = Depends(current_user), db: Session = Depends(get_db)):
    b = db.scalars(select(Bill).where(Bill.bill_no == bill_no)).first()
    if not b:
        raise HTTPException(404, "Bill not found")
    return bill_out(db, b)


@router.post("/bills/{bid}/printed")
def mark_printed(bid: int, duplicate: bool = False, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    b = get_or_404(db, Bill, bid, "Bill")
    b.print_count += 1
    if b.print_count > 1:
        audit(db, user, "DUPLICATE_PRINT" if duplicate else "REPRINT", "bill", b.bill_no)
    db.commit()
    return {"print_count": b.print_count}


class CancelIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


@router.post("/bills/{bid}/cancel")
def cancel_bill(bid: int, body: CancelIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user_can_cancel(user):
        raise HTTPException(403, "You are not allowed to cancel bills")
    b = get_or_404(db, Bill, bid, "Bill")
    if b.status == "CANCELLED":
        raise HTTPException(400, "Bill is already cancelled")
    if db.scalars(select(Note).where(Note.bill_id == bid)).first():
        raise HTTPException(400, "This bill has a credit note; it cannot be cancelled")
    ensure_period_open(db, b.bill_date.date(), user, "cancellation")
    s = get_settings(db)
    for it in b.items:
        p = db.get(Product, it.product_id) if it.product_id else None
        if p:
            _deduct_for_sale(db, p, it.qty, b.bill_no, user.username, s, sign=+1, mtype="SALE_CANCEL")
    b.status, b.cancel_reason, b.cancelled_at, b.cancelled_by = "CANCELLED", body.reason, now(), user.username
    audit(db, user, "CANCEL_BILL", "bill", b.bill_no, {"reason": body.reason, "total": b.grand_total})
    db.commit()
    return bill_out(db, b)


@router.post("/bills/{bid}/upi-verified")
def toggle_upi_verified(bid: int, verified: bool = True, user: User = Depends(current_user),
                        db: Session = Depends(get_db)):
    b = get_or_404(db, Bill, bid, "Bill")
    b.upi_verified = verified
    audit(db, user, "UPI_VERIFY" if verified else "UPI_UNVERIFY", "bill", b.bill_no)
    db.commit()
    return to_dict(b)


# ---------------- running orders (tables / KOT) ----------------
class HeldLine(BaseModel):
    product_id: int
    name: str
    qty: float = Field(gt=0)
    rate: float | None = None
    discount: float = 0
    kot_qty: float = 0
    note: str = ""


class HeldIn(BaseModel):
    table_id: int | None = None
    order_type: str = "DINE_IN"
    label: str = ""
    customer_id: int | None = None
    items: list[HeldLine]


def held_out(db: Session, h: HeldOrder) -> dict:
    d = to_dict(h)
    d["items"] = json.loads(h.items_json or "[]")
    d["table_name"] = db.get(DiningTable, h.table_id).name if h.table_id else ""
    d["amount"] = r2(sum((i.get("rate") or 0) * i["qty"] - (i.get("discount") or 0) for i in d["items"]))
    return d


@router.get("/held-orders")
def list_held(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return [held_out(db, h) for h in db.scalars(select(HeldOrder).order_by(HeldOrder.id))]


@router.post("/held-orders")
def save_held(body: HeldIn, oid: int | None = None, user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    if body.table_id:
        other = db.scalars(select(HeldOrder).where(HeldOrder.table_id == body.table_id)).first()
        if other and other.id != oid:
            raise HTTPException(400, "That table already has a running order")
    h = db.get(HeldOrder, oid) if oid else None
    if not h:
        h = HeldOrder(created_by=user.username)
        db.add(h)
    h.table_id, h.order_type, h.label, h.customer_id = body.table_id, body.order_type, body.label, body.customer_id
    h.items_json = json.dumps([i.model_dump() for i in body.items])
    h.updated_at = now()
    db.commit()
    return held_out(db, h)


@router.post("/held-orders/{oid}/kot")
def make_kot(oid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Returns the items not yet sent to the kitchen and marks them as sent."""
    h = get_or_404(db, HeldOrder, oid, "Order")
    items = json.loads(h.items_json or "[]")
    new_items = []
    for i in items:
        pending = round(i["qty"] - (i.get("kot_qty") or 0), 3)
        if pending > 0:
            new_items.append({"name": i["name"], "qty": pending, "note": i.get("note", "")})
        elif pending < 0:
            new_items.append({"name": i["name"], "qty": pending, "note": "CANCEL / REDUCE"})
        i["kot_qty"] = i["qty"]
    if not new_items:
        raise HTTPException(400, "No new items to send to the kitchen")
    h.items_json = json.dumps(items)
    h.kot_count += 1
    db.commit()
    d = held_out(db, h)
    d["kot_items"] = new_items
    d["kot_no"] = f"{h.id}-{h.kot_count}"
    d["kot_time"] = now().isoformat()
    return d


@router.delete("/held-orders/{oid}")
def delete_held(oid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    h = get_or_404(db, HeldOrder, oid, "Order")
    audit(db, user, "DISCARD_ORDER", "held_order", oid, h.items_json)
    db.delete(h)
    db.commit()
    return {"ok": True}


# ---------------- credit notes (sales return) ----------------
class CreditLine(BaseModel):
    bill_item_id: int
    qty: float = Field(gt=0)


class CreditIn(BaseModel):
    bill_id: int
    items: list[CreditLine] = Field(min_length=1)
    reason: str = Field(min_length=3)
    settlement_mode: str = Field("CASH", pattern="^(CASH|UPI|ADJUST)$")
    settlement_ref: str = ""
    restock: bool = False


@router.post("/credit-notes")
def create_credit_note(body: CreditIn, user: User = Depends(manager_up), db: Session = Depends(get_db)):
    b = get_or_404(db, Bill, body.bill_id, "Bill")
    if b.status != "ACTIVE":
        raise HTTPException(400, "Credit notes can be raised only against active bills")
    today = date.today()
    ensure_period_open(db, today, user, "credit note")
    fy, no = next_number(db, today, "credit_note")
    note = Note(note_type="CREDIT", taxable=0, cgst=0, sgst=0, igst=0, total=0, note_no=no, fy_id=fy.id, note_date=today, bill_id=b.id, ref_doc_no=b.bill_no,
                ref_doc_date=b.bill_date.date(), party_name=b.customer_name, party_gstin=b.customer_gstin,
                place_of_supply=b.place_of_supply, supply_type=b.supply_type, reason=body.reason,
                settlement_mode=body.settlement_mode, settlement_ref=body.settlement_ref, restock=body.restock,
                created_by=user.username)
    items = {i.id: i for i in b.items}
    s = get_settings(db)
    for ln in body.items:
        bi = items.get(ln.bill_item_id)
        if not bi:
            raise HTTPException(400, "Item does not belong to this bill")
        if ln.qty > bi.qty - bi.returned_qty + 0.0001:
            raise HTTPException(400, f"Return quantity for {bi.item_name} exceeds billed quantity")
        f = ln.qty / bi.qty
        ni = NoteItem(product_id=bi.product_id, item_name=bi.item_name, hsn=bi.hsn, unit=bi.unit, qty=ln.qty,
                      rate=bi.rate, taxable=r2(bi.taxable * f), gst_rate=bi.gst_rate, tax_category=bi.tax_category,
                      cgst=r2(bi.cgst * f), sgst=r2(bi.sgst * f), igst=r2(bi.igst * f), total=0)
        ni.total = r2(ni.taxable + ni.cgst + ni.sgst + ni.igst)
        note.items.append(ni)
        bi.returned_qty = round(bi.returned_qty + ln.qty, 3)
        for k in ("taxable", "cgst", "sgst", "igst"):
            setattr(note, k, r2(getattr(note, k) + getattr(ni, k)))
        p = db.get(Product, bi.product_id) if bi.product_id else None
        if body.restock and p and p.track_stock and not p.use_recipe:
            move_stock(db, p, ln.qty, "SALES_RETURN", no, f"Return against {b.bill_no}", user.username, False)
    note.total = r2(note.taxable + note.cgst + note.sgst + note.igst)
    db.add(note)
    audit(db, user, "CREATE_CREDIT_NOTE", "note", no, {"bill": b.bill_no, "total": note.total})
    db.commit()
    return note_out(note)


def note_out(n: Note) -> dict:
    d = to_dict(n)
    d["items"] = [to_dict(i) for i in n.items]
    return d


@router.get("/notes")
def list_notes(note_type: str = "CREDIT", from_date: str | None = None, to_date: str | None = None,
               _: User = Depends(current_user), db: Session = Depends(get_db)):
    f, t = parse_range(from_date, to_date)
    stmt = select(Note).where(Note.note_type == note_type, Note.note_date >= f, Note.note_date <= t) \
        .order_by(Note.id.desc())
    return [note_out(n) for n in db.scalars(stmt)]


@router.get("/notes/{nid}")
def get_note(nid: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    return note_out(get_or_404(db, Note, nid, "Note"))
