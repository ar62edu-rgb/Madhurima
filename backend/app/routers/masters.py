"""Settings, financial years, categories, products (+recipes), customers, suppliers, tables, audit log."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (AuditLog, Bill, Category, Customer, DiningTable, FinancialYear, Note, Product, Purchase,
                      RecipeItem, StockMovement, Supplier, SupplierPayment, User, now)
from ..security import admin_only, current_user, manager_up
from ..services import (DEFAULT_SETTINGS, INDIAN_STATES, audit, fy_bounds, get_or_404, get_settings, move_stock,
                        save_settings, to_dict)

router = APIRouter(prefix="/api", tags=["masters"])


# ---------------- settings ----------------
@router.get("/settings")
def read_settings(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return get_settings(db)


@router.put("/settings")
def write_settings(values: dict, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    unknown = [k for k in values if k not in DEFAULT_SETTINGS]
    if unknown:
        raise HTTPException(400, f"Unknown settings: {', '.join(unknown)}")
    gstin = str(values.get("gstin", "")).strip().upper()
    if gstin:
        if len(gstin) != 15:
            raise HTTPException(400, "GSTIN must be 15 characters")
        values["gstin"] = gstin
        values["state_code"] = gstin[:2]
    save_settings(db, values)
    audit(db, user, "UPDATE_SETTINGS", "settings", details=list(values.keys()))
    db.commit()
    return get_settings(db)


@router.get("/states")
def states():
    return [{"code": c, "name": n} for c, n in INDIAN_STATES]


# ---------------- financial years ----------------
@router.get("/financial-years")
def list_fy(_: User = Depends(current_user), db: Session = Depends(get_db)):
    today = date.today()
    start, end, name = fy_bounds(today)
    if not db.scalars(select(FinancialYear).where(FinancialYear.name == name)).first():
        db.add(FinancialYear(name=name, start_date=start, end_date=end))
        db.commit()
    rows = []
    for fy in db.scalars(select(FinancialYear).order_by(FinancialYear.start_date.desc())):
        d = to_dict(fy)
        d["is_current"] = fy.start_date <= today <= fy.end_date
        rows.append(d)
    return rows


class FyIn(BaseModel):
    start_year: int = Field(ge=2000, le=2100)


@router.post("/financial-years")
def create_fy(body: FyIn, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    start, end, name = fy_bounds(date(body.start_year, 4, 1))
    if db.scalars(select(FinancialYear).where(FinancialYear.name == name)).first():
        raise HTTPException(400, f"Financial year {name} already exists")
    fy = FinancialYear(name=name, start_date=start, end_date=end)
    db.add(fy)
    audit(db, user, "CREATE_FY", "financial_year", name)
    db.commit()
    return to_dict(fy)


@router.post("/financial-years/{fy_id}/close")
def close_fy(fy_id: int, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    fy = get_or_404(db, FinancialYear, fy_id, "Financial year")
    if fy.end_date >= date.today():
        raise HTTPException(400, "A financial year can be closed only after it ends")
    fy.is_closed, fy.closed_at, fy.closed_by = True, now(), user.username
    audit(db, user, "CLOSE_FY", "financial_year", fy.name)
    db.commit()
    return to_dict(fy)


@router.post("/financial-years/{fy_id}/reopen")
def reopen_fy(fy_id: int, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    fy = get_or_404(db, FinancialYear, fy_id, "Financial year")
    fy.is_closed, fy.closed_at, fy.closed_by = False, None, None
    audit(db, user, "REOPEN_FY", "financial_year", fy.name)
    db.commit()
    return to_dict(fy)


# ---------------- categories ----------------
class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    parent_id: int | None = None
    show_in_pos: bool = True
    sort_order: int = 0
    is_active: bool = True


@router.get("/categories")
def list_categories(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return [to_dict(c) for c in db.scalars(select(Category).order_by(Category.sort_order, Category.name))]


@router.post("/categories")
def create_category(body: CategoryIn, user: User = Depends(manager_up), db: Session = Depends(get_db)):
    c = Category(**body.model_dump())
    db.add(c)
    audit(db, user, "CREATE_CATEGORY", "category", body.name)
    db.commit()
    return to_dict(c)


@router.put("/categories/{cid}")
def update_category(cid: int, body: CategoryIn, user: User = Depends(manager_up), db: Session = Depends(get_db)):
    c = get_or_404(db, Category, cid, "Category")
    if body.parent_id == cid:
        raise HTTPException(400, "A category cannot be its own parent")
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    audit(db, user, "UPDATE_CATEGORY", "category", cid)
    db.commit()
    return to_dict(c)


# ---------------- products ----------------
class ProductIn(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=150)
    category_id: int | None = None
    subcategory: str = ""
    product_type: str = Field("MENU", pattern="^(MENU|RAW|PACKING|OTHER)$")
    hsn: str = ""
    unit: str = "NOS"
    purchase_price: float = Field(0, ge=0)
    selling_price: float = Field(0, ge=0)
    gst_rate: float = Field(5, ge=0, le=40)
    tax_category: str = Field("TAXABLE", pattern="^(TAXABLE|EXEMPT|NIL|ZERO)$")
    opening_stock: float = 0
    min_stock: float = 0
    max_stock: float = 0
    track_stock: bool = False
    use_recipe: bool = False
    is_active: bool = True


def product_out(p: Product) -> dict:
    d = to_dict(p)
    d["category_name"] = p.category.name if p.category else ""
    d["stock_value"] = round((p.current_stock or 0) * (p.purchase_price or 0), 2)
    d["low_stock"] = bool(p.track_stock and p.current_stock <= p.min_stock)
    return d


@router.get("/products")
def list_products(q: str = "", category_id: int | None = None, product_type: str = "", active_only: bool = False,
                  pos: bool = False, _: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(Product).order_by(Product.name)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Product.name).like(like), func.lower(Product.code).like(like)))
    if category_id:
        stmt = stmt.where(Product.category_id == category_id)
    if product_type:
        stmt = stmt.where(Product.product_type.in_(product_type.split(",")))
    if active_only or pos:
        stmt = stmt.where(Product.is_active.is_(True))
    if pos:
        stmt = stmt.where(Product.product_type.in_(["MENU", "OTHER"]))
    return [product_out(p) for p in db.scalars(stmt)]


@router.get("/products/next-code")
def next_code(product_type: str = "MENU", _: User = Depends(current_user), db: Session = Depends(get_db)):
    prefix = {"MENU": "M", "RAW": "R", "PACKING": "P"}.get(product_type, "O")
    n = db.scalar(select(func.count(Product.id)).where(Product.code.like(f"{prefix}%"))) or 0
    while True:
        n += 1
        code = f"{prefix}{n:03d}"
        if not db.scalars(select(Product).where(Product.code == code)).first():
            return {"code": code}


@router.get("/products/{pid}")
def get_product(pid: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    p = get_or_404(db, Product, pid, "Product")
    d = product_out(p)
    d["recipe"] = [{"ingredient_id": r.ingredient_id, "ingredient_name": r.ingredient.name,
                    "unit": r.ingredient.unit, "quantity": r.quantity}
                   for r in db.scalars(select(RecipeItem).where(RecipeItem.product_id == pid))]
    return d


def _check_code(db: Session, code: str, pid: int | None):
    other = db.scalars(select(Product).where(Product.code == code)).first()
    if other and other.id != pid:
        raise HTTPException(400, f"Product code {code} is already used by {other.name}")


@router.post("/products")
def create_product(body: ProductIn, user: User = Depends(manager_up), db: Session = Depends(get_db)):
    _check_code(db, body.code.strip(), None)
    data = body.model_dump()
    data["code"] = body.code.strip()
    p = Product(**data, current_stock=0)
    db.add(p)
    db.flush()
    if body.opening_stock:
        p.track_stock = True
        move_stock(db, p, body.opening_stock, "OPENING", "OPENING", "Opening stock entry", user.username, False)
    audit(db, user, "CREATE_PRODUCT", "product", p.code)
    db.commit()
    return product_out(p)


@router.put("/products/{pid}")
def update_product(pid: int, body: ProductIn, user: User = Depends(manager_up), db: Session = Depends(get_db)):
    p = get_or_404(db, Product, pid, "Product")
    _check_code(db, body.code.strip(), pid)
    changes = {}
    for k, v in body.model_dump(exclude={"opening_stock"}).items():
        if getattr(p, k) != v:
            changes[k] = [getattr(p, k), v]
            setattr(p, k, v)
    audit(db, user, "UPDATE_PRODUCT", "product", p.code, changes)
    db.commit()
    return product_out(p)


class RecipeLine(BaseModel):
    ingredient_id: int
    quantity: float = Field(gt=0)


@router.put("/products/{pid}/recipe")
def save_recipe(pid: int, lines: list[RecipeLine], user: User = Depends(manager_up), db: Session = Depends(get_db)):
    p = get_or_404(db, Product, pid, "Product")
    for r in db.scalars(select(RecipeItem).where(RecipeItem.product_id == pid)):
        db.delete(r)
    for ln in lines:
        ing = get_or_404(db, Product, ln.ingredient_id, "Ingredient")
        if ing.id == pid:
            raise HTTPException(400, "A product cannot be an ingredient of itself")
        if not ing.track_stock:
            ing.track_stock = True
        db.add(RecipeItem(product_id=pid, ingredient_id=ing.id, quantity=ln.quantity))
    p.use_recipe = bool(lines)
    audit(db, user, "SAVE_RECIPE", "product", p.code, [ln.model_dump() for ln in lines])
    db.commit()
    return get_product(pid, user, db)


# ---------------- customers ----------------
class PartyIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    phone: str = ""
    email: str = ""
    gstin: str = ""
    address: str = ""
    state: str = ""
    state_code: str = ""
    is_active: bool = True


class SupplierIn(PartyIn):
    contact_person: str = ""
    opening_balance: float = 0


def _norm_party(data: dict) -> dict:
    data["gstin"] = data.get("gstin", "").strip().upper()
    if data["gstin"]:
        if len(data["gstin"]) != 15:
            raise HTTPException(400, "GSTIN must be 15 characters")
        data["state_code"] = data["gstin"][:2]
    from ..services import STATE_NAMES
    if data.get("state_code") and not data.get("state"):
        data["state"] = STATE_NAMES.get(data["state_code"], "")
    return data


@router.get("/customers")
def list_customers(q: str = "", _: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(Customer).order_by(Customer.name)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Customer.name).like(like), Customer.phone.like(like),
                              func.lower(Customer.gstin).like(like)))
    return [to_dict(c) for c in db.scalars(stmt.limit(500))]


@router.post("/customers")
def create_customer(body: PartyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = Customer(**_norm_party(body.model_dump()))
    db.add(c)
    audit(db, user, "CREATE_CUSTOMER", "customer", body.name)
    db.commit()
    return to_dict(c)


@router.put("/customers/{cid}")
def update_customer(cid: int, body: PartyIn, user: User = Depends(manager_up), db: Session = Depends(get_db)):
    c = get_or_404(db, Customer, cid, "Customer")
    for k, v in _norm_party(body.model_dump()).items():
        setattr(c, k, v)
    audit(db, user, "UPDATE_CUSTOMER", "customer", cid)
    db.commit()
    return to_dict(c)


@router.get("/customers/{cid}/bills")
def customer_bills(cid: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    bills = db.scalars(select(Bill).where(Bill.customer_id == cid).order_by(Bill.bill_date.desc()).limit(500))
    return [to_dict(b) for b in bills]


# ---------------- suppliers ----------------
def supplier_balance(db: Session, sid: int) -> dict:
    s = db.get(Supplier, sid)
    purchases = db.scalar(select(func.coalesce(func.sum(Purchase.grand_total), 0))
                          .where(Purchase.supplier_id == sid, Purchase.status == "ACTIVE")) or 0
    paid = db.scalar(select(func.coalesce(func.sum(SupplierPayment.amount), 0))
                     .where(SupplierPayment.supplier_id == sid, SupplierPayment.is_cancelled.is_(False))) or 0
    returns = db.scalar(select(func.coalesce(func.sum(Note.total), 0))
                        .join(Purchase, Purchase.id == Note.purchase_id)
                        .where(Note.note_type == "DEBIT", Purchase.supplier_id == sid,
                               Note.settlement_mode == "ADJUST")) or 0
    return {"opening_balance": s.opening_balance, "purchases": round(purchases, 2), "paid": round(paid, 2),
            "returns": round(returns, 2),
            "outstanding": round(s.opening_balance + purchases - paid - returns, 2)}


@router.get("/suppliers")
def list_suppliers(q: str = "", _: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(Supplier).order_by(Supplier.name)
    if q:
        stmt = stmt.where(func.lower(Supplier.name).like(f"%{q.lower()}%"))
    out = []
    for s in db.scalars(stmt):
        d = to_dict(s)
        d.update(supplier_balance(db, s.id))
        out.append(d)
    return out


@router.post("/suppliers")
def create_supplier(body: SupplierIn, user: User = Depends(manager_up), db: Session = Depends(get_db)):
    s = Supplier(**_norm_party(body.model_dump()))
    db.add(s)
    audit(db, user, "CREATE_SUPPLIER", "supplier", body.name)
    db.commit()
    return to_dict(s)


@router.put("/suppliers/{sid}")
def update_supplier(sid: int, body: SupplierIn, user: User = Depends(manager_up), db: Session = Depends(get_db)):
    s = get_or_404(db, Supplier, sid, "Supplier")
    for k, v in _norm_party(body.model_dump()).items():
        setattr(s, k, v)
    audit(db, user, "UPDATE_SUPPLIER", "supplier", sid)
    db.commit()
    return to_dict(s)


@router.get("/suppliers/{sid}/ledger")
def supplier_ledger(sid: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    s = get_or_404(db, Supplier, sid, "Supplier")
    entries = []
    for p in db.scalars(select(Purchase).where(Purchase.supplier_id == sid, Purchase.status == "ACTIVE")):
        entries.append({"date": p.invoice_date.isoformat(), "type": "Purchase",
                        "ref": f"{p.purchase_no} / Inv {p.supplier_invoice_no}", "debit": 0, "credit": p.grand_total})
    for pay in db.scalars(select(SupplierPayment).where(SupplierPayment.supplier_id == sid,
                                                       SupplierPayment.is_cancelled.is_(False))):
        entries.append({"date": pay.payment_date.isoformat(), "type": f"Payment ({pay.mode})",
                        "ref": pay.reference or pay.remarks, "debit": pay.amount, "credit": 0})
    for n in db.scalars(select(Note).join(Purchase, Purchase.id == Note.purchase_id)
                        .where(Note.note_type == "DEBIT", Purchase.supplier_id == sid,
                               Note.settlement_mode == "ADJUST")):
        entries.append({"date": n.note_date.isoformat(), "type": "Purchase return", "ref": n.note_no,
                        "debit": n.total, "credit": 0})
    entries.sort(key=lambda e: e["date"])
    bal = s.opening_balance
    for e in entries:
        bal = round(bal + e["credit"] - e["debit"], 2)
        e["balance"] = bal
    return {"supplier": to_dict(s), "summary": supplier_balance(db, sid), "entries": entries}


# ---------------- dining tables ----------------
class TableIn(BaseModel):
    name: str = Field(min_length=1, max_length=30)
    area: str = "Main Hall"
    seats: int = 4
    is_active: bool = True


@router.get("/tables")
def list_tables(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return [to_dict(t) for t in db.scalars(select(DiningTable).order_by(DiningTable.area, DiningTable.id))]


@router.post("/tables")
def create_table(body: TableIn, user: User = Depends(manager_up), db: Session = Depends(get_db)):
    t = DiningTable(**body.model_dump())
    db.add(t)
    db.commit()
    return to_dict(t)


@router.put("/tables/{tid}")
def update_table(tid: int, body: TableIn, user: User = Depends(manager_up), db: Session = Depends(get_db)):
    t = get_or_404(db, DiningTable, tid, "Table")
    for k, v in body.model_dump().items():
        setattr(t, k, v)
    db.commit()
    return to_dict(t)


# ---------------- audit log ----------------
@router.get("/audit-logs")
def audit_logs(q: str = "", limit: int = 300, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 2000))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(AuditLog.action).like(like), func.lower(AuditLog.username).like(like),
                              func.lower(AuditLog.entity_id).like(like)))
    return [to_dict(a) for a in db.scalars(stmt)]


@router.get("/stock-movements/product/{pid}")
def product_movements(pid: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(StockMovement).where(StockMovement.product_id == pid)
                      .order_by(StockMovement.id.desc()).limit(1000))
    return [to_dict(m) for m in rows]
