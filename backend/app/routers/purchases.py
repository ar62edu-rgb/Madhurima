"""Purchases (stock in), purchase returns (debit notes), attachments, supplier payments."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import ATTACH_DIR, MAX_UPLOAD_MB
from ..db import get_db
from ..gst import Line, compute, r2
from ..models import Note, NoteItem, Product, Purchase, PurchaseItem, Supplier, SupplierPayment, User
from ..security import current_user, manager_up
from ..services import (audit, ensure_period_open, get_or_404, get_settings, move_stock, next_number, parse_range,
                        to_dict)
from .billing import note_out

router = APIRouter(prefix="/api", tags=["purchases"])

ALLOWED_EXT = {".pdf": b"%PDF", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff", ".png": b"\x89PNG"}


class PurchaseLineIn(BaseModel):
    product_id: int
    qty: float = Field(gt=0)
    rate: float = Field(ge=0)
    discount: float = Field(0, ge=0)
    gst_rate: float = Field(0, ge=0, le=40)


class PurchaseIn(BaseModel):
    supplier_id: int
    supplier_invoice_no: str = Field(min_length=1, max_length=50)
    invoice_date: date
    supply_type: str = Field("AUTO", pattern="^(AUTO|INTRA|INTER)$")
    items: list[PurchaseLineIn] = Field(min_length=1)
    other_charges: float = 0
    round_off: bool = True
    update_purchase_price: bool = True
    paid_cash: float = Field(0, ge=0)
    paid_upi: float = Field(0, ge=0)
    upi_ref: str = ""
    notes: str = ""


def _calc(db: Session, body: PurchaseIn):
    sup = get_or_404(db, Supplier, body.supplier_id, "Supplier")
    s = get_settings(db)
    if body.supply_type == "AUTO":
        inter = bool(sup.state_code and s.get("state_code") and sup.state_code != s.get("state_code"))
    else:
        inter = body.supply_type == "INTER"
    lines = [Line(qty=i.qty, rate=i.rate, discount=i.discount, gst_rate=i.gst_rate,
                  tax_category="TAXABLE" if i.gst_rate else "EXEMPT") for i in body.items]
    try:
        t = compute(lines, 0, False, inter, body.round_off, body.other_charges)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return sup, inter, lines, t


@router.post("/purchases/preview")
def preview_purchase(body: PurchaseIn, _: User = Depends(current_user), db: Session = Depends(get_db)):
    _, inter, lines, t = _calc(db, body)
    return {"supply_type": "INTER" if inter else "INTRA", "totals": t.__dict__,
            "lines": [ln.__dict__ for ln in lines]}


@router.post("/purchases")
def create_purchase(body: PurchaseIn, user: User = Depends(manager_up), db: Session = Depends(get_db)):
    ensure_period_open(db, body.invoice_date, user, "purchase")
    sup, inter, lines, t = _calc(db, body)
    dup = db.scalars(select(Purchase).where(Purchase.supplier_id == sup.id, Purchase.status == "ACTIVE",
                                            Purchase.supplier_invoice_no == body.supplier_invoice_no.strip())).first()
    if dup:
        raise HTTPException(400, f"Invoice {body.supplier_invoice_no} from {sup.name} is already entered ({dup.purchase_no})")
    if body.paid_cash + body.paid_upi > t.grand_total + 0.009:
        raise HTTPException(400, "Paid amount is more than the purchase total")
    fy, no = next_number(db, body.invoice_date, "purchase")
    pur = Purchase(purchase_no=no, fy_id=fy.id, supplier_id=sup.id, supplier_invoice_no=body.supplier_invoice_no.strip(),
                   invoice_date=body.invoice_date, supply_type="INTER" if inter else "INTRA", gross_amount=t.gross,
                   discount=t.item_discount, taxable_amount=r2(t.taxable + t.exempt), cgst=t.cgst, sgst=t.sgst,
                   igst=t.igst, total_tax=t.total_tax, other_charges=r2(body.other_charges), round_off=t.round_off,
                   grand_total=t.grand_total, notes=body.notes, created_by=user.username)
    db.add(pur)
    db.flush()
    for ln, it in zip(lines, body.items):
        p = db.scalars(select(Product).where(Product.id == it.product_id).with_for_update()).first()
        if not p:
            raise HTTPException(400, f"Product #{it.product_id} not found")
        pur.items.append(PurchaseItem(product_id=p.id, item_name=p.name, hsn=p.hsn, unit=p.unit, qty=ln.qty,
                                      rate=ln.rate, gross=ln.gross, discount=ln.discount, taxable=ln.taxable,
                                      gst_rate=ln.gst_rate, cgst=ln.cgst, sgst=ln.sgst, igst=ln.igst, total=ln.total))
        p.track_stock = True
        move_stock(db, p, ln.qty, "PURCHASE", no, f"{sup.name} inv {pur.supplier_invoice_no}", user.username, False)
        if body.update_purchase_price and ln.qty:
            p.purchase_price = r2(ln.taxable / ln.qty)
    for amount, mode, ref in ((body.paid_cash, "CASH", ""), (body.paid_upi, "UPI", body.upi_ref)):
        if amount > 0:
            db.add(SupplierPayment(supplier_id=sup.id, purchase_id=pur.id, payment_date=body.invoice_date,
                                   amount=r2(amount), mode=mode, reference=ref, remarks=f"Against {no}",
                                   created_by=user.username))
    audit(db, user, "CREATE_PURCHASE", "purchase", no, {"total": t.grand_total, "supplier": sup.name})
    db.commit()
    return purchase_out(db, pur)


def purchase_out(db: Session, p: Purchase) -> dict:
    d = to_dict(p)
    d["supplier_name"] = p.supplier.name if p.supplier else ""
    d["supplier_gstin"] = p.supplier.gstin if p.supplier else ""
    d["items"] = [to_dict(i) for i in p.items]
    paid = db.scalar(select(func.coalesce(func.sum(SupplierPayment.amount), 0))
                     .where(SupplierPayment.purchase_id == p.id, SupplierPayment.is_cancelled.is_(False))) or 0
    returns = db.scalar(select(func.coalesce(func.sum(Note.total), 0))
                        .where(Note.purchase_id == p.id, Note.settlement_mode == "ADJUST")) or 0
    d["paid_amount"] = r2(paid)
    d["return_amount"] = r2(returns)
    d["balance"] = r2(p.grand_total - paid - returns) if p.status == "ACTIVE" else 0
    d["payment_status"] = "CANCELLED" if p.status != "ACTIVE" else \
        ("PAID" if d["balance"] <= 0.009 else ("PARTIAL" if paid else "UNPAID"))
    d["debit_notes"] = [note_out(n) for n in db.scalars(select(Note).where(Note.purchase_id == p.id))]
    return d


@router.get("/purchases")
def list_purchases(from_date: str | None = None, to_date: str | None = None, supplier_id: int | None = None,
                   q: str = "", _: User = Depends(current_user), db: Session = Depends(get_db)):
    f, t = parse_range(from_date, to_date)
    stmt = select(Purchase).where(Purchase.invoice_date >= f, Purchase.invoice_date <= t).order_by(Purchase.id.desc())
    if supplier_id:
        stmt = stmt.where(Purchase.supplier_id == supplier_id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Purchase.purchase_no).like(like),
                              func.lower(Purchase.supplier_invoice_no).like(like)))
    out = []
    for p in db.scalars(stmt):
        d = purchase_out(db, p)
        d.pop("items")
        out.append(d)
    return out


@router.get("/purchases/{pid}")
def get_purchase(pid: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    return purchase_out(db, get_or_404(db, Purchase, pid, "Purchase"))


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


@router.post("/purchases/{pid}/cancel")
def cancel_purchase(pid: int, body: ReasonIn, user: User = Depends(manager_up), db: Session = Depends(get_db)):
    p = get_or_404(db, Purchase, pid, "Purchase")
    if p.status != "ACTIVE":
        raise HTTPException(400, "Purchase is already cancelled")
    if db.scalars(select(Note).where(Note.purchase_id == pid)).first():
        raise HTTPException(400, "This purchase has returns; it cannot be cancelled")
    ensure_period_open(db, p.invoice_date, user, "cancellation")
    for it in p.items:
        prod = db.scalars(select(Product).where(Product.id == it.product_id).with_for_update()).first()
        move_stock(db, prod, -it.qty, "PURCHASE_CANCEL", p.purchase_no, body.reason, user.username, False)
    for pay in db.scalars(select(SupplierPayment).where(SupplierPayment.purchase_id == pid)):
        pay.is_cancelled = True
        pay.remarks = (pay.remarks + " | purchase cancelled")[:300]
    p.status, p.cancel_reason = "CANCELLED", body.reason
    audit(db, user, "CANCEL_PURCHASE", "purchase", p.purchase_no, body.reason)
    db.commit()
    return purchase_out(db, p)


class ReturnLine(BaseModel):
    purchase_item_id: int
    qty: float = Field(gt=0)


class ReturnIn(BaseModel):
    items: list[ReturnLine] = Field(min_length=1)
    reason: str = Field(min_length=3)
    settlement_mode: str = Field("ADJUST", pattern="^(CASH|UPI|ADJUST)$")
    settlement_ref: str = ""


@router.post("/purchases/{pid}/return")
def purchase_return(pid: int, body: ReturnIn, user: User = Depends(manager_up), db: Session = Depends(get_db)):
    p = get_or_404(db, Purchase, pid, "Purchase")
    if p.status != "ACTIVE":
        raise HTTPException(400, "Cannot return items of a cancelled purchase")
    today = date.today()
    ensure_period_open(db, today, user, "purchase return")
    fy, no = next_number(db, today, "debit_note")
    note = Note(note_type="DEBIT", taxable=0, cgst=0, sgst=0, igst=0, total=0, note_no=no, fy_id=fy.id, note_date=today, purchase_id=p.id,
                ref_doc_no=p.supplier_invoice_no, ref_doc_date=p.invoice_date, party_name=p.supplier.name,
                party_gstin=p.supplier.gstin, place_of_supply=p.supplier.state_code, supply_type=p.supply_type,
                reason=body.reason, settlement_mode=body.settlement_mode, settlement_ref=body.settlement_ref,
                restock=True, created_by=user.username)
    items = {i.id: i for i in p.items}
    for ln in body.items:
        pi = items.get(ln.purchase_item_id)
        if not pi:
            raise HTTPException(400, "Item does not belong to this purchase")
        if ln.qty > pi.qty - pi.returned_qty + 0.0001:
            raise HTTPException(400, f"Return quantity for {pi.item_name} exceeds purchased quantity")
        f = ln.qty / pi.qty
        ni = NoteItem(product_id=pi.product_id, item_name=pi.item_name, hsn=pi.hsn, unit=pi.unit, qty=ln.qty,
                      rate=pi.rate, taxable=r2(pi.taxable * f), gst_rate=pi.gst_rate,
                      cgst=r2(pi.cgst * f), sgst=r2(pi.sgst * f), igst=r2(pi.igst * f), total=0)
        ni.total = r2(ni.taxable + ni.cgst + ni.sgst + ni.igst)
        note.items.append(ni)
        pi.returned_qty = round(pi.returned_qty + ln.qty, 3)
        for k in ("taxable", "cgst", "sgst", "igst"):
            setattr(note, k, r2(getattr(note, k) + getattr(ni, k)))
        prod = db.scalars(select(Product).where(Product.id == pi.product_id).with_for_update()).first()
        move_stock(db, prod, -ln.qty, "PURCHASE_RETURN", no, f"Return to {p.supplier.name}", user.username)
    note.total = r2(note.taxable + note.cgst + note.sgst + note.igst)
    db.add(note)
    audit(db, user, "PURCHASE_RETURN", "note", no, {"purchase": p.purchase_no, "total": note.total})
    db.commit()
    return note_out(note)


@router.post("/purchases/{pid}/attachment")
async def upload_attachment(pid: int, file: UploadFile = File(...), user: User = Depends(manager_up),
                            db: Session = Depends(get_db)):
    p = get_or_404(db, Purchase, pid, "Purchase")
    name = file.filename or "file"
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, "Only PDF, JPG or PNG files are allowed")
    data = await file.read(MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(400, f"File is larger than {MAX_UPLOAD_MB} MB")
    if not data.startswith(ALLOWED_EXT[ext]):
        raise HTTPException(400, "File content does not match its type")
    stored = f"{uuid.uuid4().hex}{ext}"
    (ATTACH_DIR / stored).write_bytes(data)
    if p.attachment_path:
        old = ATTACH_DIR / p.attachment_path
        if old.exists():
            old.unlink()
    p.attachment_path, p.attachment_name = stored, name[:200]
    audit(db, user, "UPLOAD_ATTACHMENT", "purchase", p.purchase_no, name)
    db.commit()
    return {"attachment_name": p.attachment_name}


@router.get("/purchases/{pid}/attachment")
def download_attachment(pid: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    p = get_or_404(db, Purchase, pid, "Purchase")
    path = (ATTACH_DIR / p.attachment_path).resolve() if p.attachment_path else None
    if not path or not path.exists() or path.parent != ATTACH_DIR.resolve():
        raise HTTPException(404, "No attachment")
    return FileResponse(path, filename=p.attachment_name)


# ---------------- supplier payments ----------------
class PaymentIn(BaseModel):
    supplier_id: int
    purchase_id: int | None = None
    payment_date: date
    amount: float = Field(gt=0)
    mode: str = Field(pattern="^(CASH|UPI)$")
    reference: str = ""
    remarks: str = ""


@router.get("/supplier-payments")
def list_payments(from_date: str | None = None, to_date: str | None = None, supplier_id: int | None = None,
                  _: User = Depends(current_user), db: Session = Depends(get_db)):
    f, t = parse_range(from_date, to_date)
    stmt = select(SupplierPayment).where(SupplierPayment.payment_date >= f, SupplierPayment.payment_date <= t) \
        .order_by(SupplierPayment.id.desc())
    if supplier_id:
        stmt = stmt.where(SupplierPayment.supplier_id == supplier_id)
    out = []
    for p in db.scalars(stmt):
        d = to_dict(p)
        d["supplier_name"] = p.supplier.name
        d["purchase_no"] = db.get(Purchase, p.purchase_id).purchase_no if p.purchase_id else ""
        out.append(d)
    return out


@router.post("/supplier-payments")
def create_payment(body: PaymentIn, user: User = Depends(manager_up), db: Session = Depends(get_db)):
    ensure_period_open(db, body.payment_date, user, "payment")
    get_or_404(db, Supplier, body.supplier_id, "Supplier")
    if body.purchase_id:
        pur = get_or_404(db, Purchase, body.purchase_id, "Purchase")
        if pur.supplier_id != body.supplier_id:
            raise HTTPException(400, "Purchase belongs to a different supplier")
        bal = purchase_out(db, pur)["balance"]
        if body.amount > bal + 0.009:
            raise HTTPException(400, f"Amount is more than the purchase balance ₹{bal:.2f}")
    p = SupplierPayment(**body.model_dump(), created_by=user.username)
    p.amount = r2(p.amount)
    db.add(p)
    audit(db, user, "SUPPLIER_PAYMENT", "supplier", body.supplier_id, body.model_dump(mode="json"))
    db.commit()
    return to_dict(p)


@router.post("/supplier-payments/{pid}/cancel")
def cancel_payment(pid: int, user: User = Depends(manager_up), db: Session = Depends(get_db)):
    p = get_or_404(db, SupplierPayment, pid, "Payment")
    ensure_period_open(db, p.payment_date, user, "cancellation")
    p.is_cancelled = True
    audit(db, user, "CANCEL_SUPPLIER_PAYMENT", "supplier_payment", pid)
    db.commit()
    return to_dict(p)
