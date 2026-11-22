"""Stock adjustments, reconciliation and the stock movement register."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Product, StockMovement, User
from ..security import current_user, manager_up
from ..services import (audit, day_end, day_start, ensure_period_open, get_or_404, move_stock, parse_range, r3,
                        to_dict)

router = APIRouter(prefix="/api/stock", tags=["stock"])

ADD_TYPES = {"ADDITION", "RETURN", "CORRECTION", "MANUAL", "OPENING"}
REDUCE_TYPES = {"REDUCTION", "WASTAGE", "DAMAGE", "EXPIRY", "CORRECTION", "MANUAL"}
MOVEMENT_TYPES = ["OPENING", "PURCHASE", "SALE", "SALE_CANCEL", "SALES_RETURN", "PURCHASE_RETURN",
                  "PURCHASE_CANCEL", "ADDITION", "REDUCTION", "WASTAGE", "DAMAGE", "EXPIRY", "CORRECTION",
                  "RETURN", "MANUAL", "RECONCILIATION"]


class AdjustIn(BaseModel):
    product_id: int
    movement_type: str
    direction: str = Field(pattern="^(ADD|REDUCE)$")
    qty: float = Field(gt=0)
    remarks: str = Field("", max_length=300)
    reference: str = ""


@router.get("/types")
def types():
    return MOVEMENT_TYPES


@router.post("/adjust")
def adjust(body: AdjustIn, user: User = Depends(manager_up), db: Session = Depends(get_db)):
    ensure_period_open(db, date.today(), user, "stock adjustment")
    allowed = ADD_TYPES if body.direction == "ADD" else REDUCE_TYPES
    if body.movement_type not in allowed:
        raise HTTPException(400, f"{body.movement_type} is not valid for {body.direction.lower()}")
    if body.movement_type in ("WASTAGE", "DAMAGE", "EXPIRY", "CORRECTION", "MANUAL") and not body.remarks.strip():
        raise HTTPException(400, "Please enter remarks for this adjustment")
    p = db.scalars(select(Product).where(Product.id == body.product_id).with_for_update()).first()
    if not p:
        raise HTTPException(404, "Product not found")
    p.track_stock = True
    change = body.qty if body.direction == "ADD" else -body.qty
    move_stock(db, p, change, body.movement_type, body.reference or "ADJ", body.remarks, user.username)
    if body.movement_type == "OPENING":
        p.opening_stock = r3(p.opening_stock + body.qty)
    audit(db, user, "STOCK_ADJUST", "product", p.code, body.model_dump())
    db.commit()
    return {"product_id": p.id, "current_stock": p.current_stock}


class CountLine(BaseModel):
    product_id: int
    physical_qty: float = Field(ge=0)


class ReconcileIn(BaseModel):
    counts: list[CountLine] = Field(min_length=1)
    remarks: str = "Physical stock count"


@router.post("/reconcile")
def reconcile(body: ReconcileIn, user: User = Depends(manager_up), db: Session = Depends(get_db)):
    ensure_period_open(db, date.today(), user, "stock reconciliation")
    ref = f"REC-{date.today():%Y%m%d}"
    result = []
    for c in body.counts:
        p = db.scalars(select(Product).where(Product.id == c.product_id).with_for_update()).first()
        if not p:
            continue
        diff = r3(c.physical_qty - p.current_stock)
        result.append({"product_id": p.id, "name": p.name, "system_qty": p.current_stock,
                       "physical_qty": c.physical_qty, "difference": diff,
                       "value_difference": round(diff * p.purchase_price, 2)})
        if diff:
            p.track_stock = True
            move_stock(db, p, diff, "RECONCILIATION", ref, body.remarks, user.username, False)
    audit(db, user, "STOCK_RECONCILE", "stock", ref, result)
    db.commit()
    return result


@router.get("/movements")
def movements(from_date: str | None = None, to_date: str | None = None, product_id: int | None = None,
              movement_type: str = "", _: User = Depends(current_user), db: Session = Depends(get_db)):
    f, t = parse_range(from_date, to_date)
    stmt = select(StockMovement).where(StockMovement.created_at >= day_start(f),
                                       StockMovement.created_at < day_end(t)).order_by(StockMovement.id.desc())
    if product_id:
        stmt = stmt.where(StockMovement.product_id == product_id)
    if movement_type:
        stmt = stmt.where(StockMovement.movement_type == movement_type)
    out = []
    for m in db.scalars(stmt.limit(5000)):
        d = to_dict(m)
        d["product_name"] = m.product.name
        d["unit"] = m.product.unit
        out.append(d)
    return out


@router.get("/product/{pid}")
def product_history(pid: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    p = get_or_404(db, Product, pid, "Product")
    rows = db.scalars(select(StockMovement).where(StockMovement.product_id == pid).order_by(StockMovement.id.desc())
                      .limit(2000))
    return {"product": to_dict(p), "movements": [to_dict(m) for m in rows]}
