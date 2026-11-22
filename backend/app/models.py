"""Database tables. Money is stored as Float rounded to 2 decimals; dates are local (IST)."""
from datetime import datetime, date

from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> datetime:
    return datetime.now().replace(microsecond=0)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    full_name: Mapped[str] = mapped_column(String(100), default="")
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20), default="cashier")  # admin / manager / cashier
    can_edit_price: Mapped[bool] = mapped_column(Boolean, default=False)
    can_discount: Mapped[bool] = mapped_column(Boolean, default=True)
    can_cancel_bill: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class FinancialYear(Base):
    __tablename__ = "financial_years"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(20), unique=True)  # e.g. 2026-27
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    bill_seq: Mapped[int] = mapped_column(Integer, default=0)
    purchase_seq: Mapped[int] = mapped_column(Integer, default=0)
    credit_note_seq: Mapped[int] = mapped_column(Integer, default=0)
    debit_note_seq: Mapped[int] = mapped_column(Integer, default=0)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_by: Mapped[str | None] = mapped_column(String(50), nullable=True)


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    show_in_pos: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    subcategory: Mapped[str] = mapped_column(String(80), default="")
    product_type: Mapped[str] = mapped_column(String(20), default="MENU")  # MENU / RAW / PACKING / OTHER
    hsn: Mapped[str] = mapped_column(String(20), default="")
    unit: Mapped[str] = mapped_column(String(20), default="NOS")
    purchase_price: Mapped[float] = mapped_column(Float, default=0)
    selling_price: Mapped[float] = mapped_column(Float, default=0)
    gst_rate: Mapped[float] = mapped_column(Float, default=5)
    tax_category: Mapped[str] = mapped_column(String(20), default="TAXABLE")  # TAXABLE / EXEMPT / NIL / ZERO
    opening_stock: Mapped[float] = mapped_column(Float, default=0)
    current_stock: Mapped[float] = mapped_column(Float, default=0)
    min_stock: Mapped[float] = mapped_column(Float, default=0)
    max_stock: Mapped[float] = mapped_column(Float, default=0)
    track_stock: Mapped[bool] = mapped_column(Boolean, default=False)
    use_recipe: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    category = relationship("Category")


class RecipeItem(Base):
    __tablename__ = "recipe_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[float] = mapped_column(Float)  # ingredient units per 1 sold unit
    ingredient = relationship("Product", foreign_keys=[ingredient_id])


class StockMovement(Base):
    __tablename__ = "stock_movements"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    movement_type: Mapped[str] = mapped_column(String(30))
    opening_qty: Mapped[float] = mapped_column(Float)
    added_qty: Mapped[float] = mapped_column(Float, default=0)
    reduced_qty: Mapped[float] = mapped_column(Float, default=0)
    closing_qty: Mapped[float] = mapped_column(Float)
    ref_no: Mapped[str] = mapped_column(String(60), default="")
    remarks: Mapped[str] = mapped_column(String(300), default="")
    created_by: Mapped[str] = mapped_column(String(50), default="")
    product = relationship("Product")


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str] = mapped_column(String(20), default="")
    email: Mapped[str] = mapped_column(String(120), default="")
    gstin: Mapped[str] = mapped_column(String(15), default="")
    address: Mapped[str] = mapped_column(String(300), default="")
    state: Mapped[str] = mapped_column(String(60), default="")
    state_code: Mapped[str] = mapped_column(String(2), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    contact_person: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(20), default="")
    email: Mapped[str] = mapped_column(String(120), default="")
    gstin: Mapped[str] = mapped_column(String(15), default="")
    address: Mapped[str] = mapped_column(String(300), default="")
    state: Mapped[str] = mapped_column(String(60), default="")
    state_code: Mapped[str] = mapped_column(String(2), default="")
    opening_balance: Mapped[float] = mapped_column(Float, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class DiningTable(Base):
    __tablename__ = "dining_tables"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30))
    area: Mapped[str] = mapped_column(String(40), default="Main Hall")
    seats: Mapped[int] = mapped_column(Integer, default=4)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class HeldOrder(Base):
    """A running (unbilled) order, e.g. for a dine-in table. No bill number is used until it is settled."""
    __tablename__ = "held_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[int | None] = mapped_column(ForeignKey("dining_tables.id"), nullable=True)
    order_type: Mapped[str] = mapped_column(String(20), default="DINE_IN")
    label: Mapped[str] = mapped_column(String(60), default="")
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    items_json: Mapped[str] = mapped_column(Text, default="[]")
    kot_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(50), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Bill(Base):
    __tablename__ = "bills"
    id: Mapped[int] = mapped_column(primary_key=True)
    bill_no: Mapped[str] = mapped_column(String(40), unique=True)
    fy_id: Mapped[int] = mapped_column(ForeignKey("financial_years.id"))
    bill_date: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    order_type: Mapped[str] = mapped_column(String(20), default="DINE_IN")
    table_name: Mapped[str] = mapped_column(String(30), default="")
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    customer_name: Mapped[str] = mapped_column(String(150), default="")
    customer_phone: Mapped[str] = mapped_column(String(20), default="")
    customer_gstin: Mapped[str] = mapped_column(String(15), default="")
    customer_address: Mapped[str] = mapped_column(String(300), default="")
    place_of_supply: Mapped[str] = mapped_column(String(2), default="")  # state code
    supply_type: Mapped[str] = mapped_column(String(10), default="INTRA")  # INTRA / INTER
    invoice_type: Mapped[str] = mapped_column(String(5), default="B2C")  # B2B / B2C
    prices_include_gst: Mapped[bool] = mapped_column(Boolean, default=False)
    gross_amount: Mapped[float] = mapped_column(Float, default=0)
    item_discount: Mapped[float] = mapped_column(Float, default=0)
    bill_discount: Mapped[float] = mapped_column(Float, default=0)
    taxable_amount: Mapped[float] = mapped_column(Float, default=0)
    exempt_amount: Mapped[float] = mapped_column(Float, default=0)
    cgst: Mapped[float] = mapped_column(Float, default=0)
    sgst: Mapped[float] = mapped_column(Float, default=0)
    igst: Mapped[float] = mapped_column(Float, default=0)
    total_tax: Mapped[float] = mapped_column(Float, default=0)
    round_off: Mapped[float] = mapped_column(Float, default=0)
    grand_total: Mapped[float] = mapped_column(Float, default=0)
    payment_mode: Mapped[str] = mapped_column(String(10), default="CASH")  # CASH / UPI / SPLIT
    cash_amount: Mapped[float] = mapped_column(Float, default=0)
    upi_amount: Mapped[float] = mapped_column(Float, default=0)
    upi_ref: Mapped[str] = mapped_column(String(60), default="")
    upi_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    cash_tendered: Mapped[float] = mapped_column(Float, default=0)
    change_returned: Mapped[float] = mapped_column(Float, default=0)
    cost_amount: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE")  # ACTIVE / CANCELLED
    cancel_reason: Mapped[str] = mapped_column(String(300), default="")
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_by: Mapped[str] = mapped_column(String(50), default="")
    print_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(String(300), default="")
    created_by: Mapped[str] = mapped_column(String(50), default="")
    items = relationship("BillItem", cascade="all, delete-orphan", order_by="BillItem.id")


class BillItem(Base):
    __tablename__ = "bill_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    item_name: Mapped[str] = mapped_column(String(150))
    hsn: Mapped[str] = mapped_column(String(20), default="")
    unit: Mapped[str] = mapped_column(String(20), default="NOS")
    qty: Mapped[float] = mapped_column(Float)
    rate: Mapped[float] = mapped_column(Float)
    gross: Mapped[float] = mapped_column(Float)
    discount: Mapped[float] = mapped_column(Float, default=0)
    bill_discount_share: Mapped[float] = mapped_column(Float, default=0)
    taxable: Mapped[float] = mapped_column(Float)
    gst_rate: Mapped[float] = mapped_column(Float)
    tax_category: Mapped[str] = mapped_column(String(20), default="TAXABLE")
    cgst: Mapped[float] = mapped_column(Float, default=0)
    sgst: Mapped[float] = mapped_column(Float, default=0)
    igst: Mapped[float] = mapped_column(Float, default=0)
    total: Mapped[float] = mapped_column(Float)
    cost: Mapped[float] = mapped_column(Float, default=0)
    returned_qty: Mapped[float] = mapped_column(Float, default=0)


class Purchase(Base):
    __tablename__ = "purchases"
    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_no: Mapped[str] = mapped_column(String(40), unique=True)
    fy_id: Mapped[int] = mapped_column(ForeignKey("financial_years.id"))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    supplier_invoice_no: Mapped[str] = mapped_column(String(50))
    invoice_date: Mapped[date] = mapped_column(Date, index=True)
    supply_type: Mapped[str] = mapped_column(String(10), default="INTRA")
    gross_amount: Mapped[float] = mapped_column(Float, default=0)
    discount: Mapped[float] = mapped_column(Float, default=0)
    taxable_amount: Mapped[float] = mapped_column(Float, default=0)
    cgst: Mapped[float] = mapped_column(Float, default=0)
    sgst: Mapped[float] = mapped_column(Float, default=0)
    igst: Mapped[float] = mapped_column(Float, default=0)
    total_tax: Mapped[float] = mapped_column(Float, default=0)
    other_charges: Mapped[float] = mapped_column(Float, default=0)
    round_off: Mapped[float] = mapped_column(Float, default=0)
    grand_total: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE")  # ACTIVE / CANCELLED
    cancel_reason: Mapped[str] = mapped_column(String(300), default="")
    attachment_path: Mapped[str] = mapped_column(String(300), default="")
    attachment_name: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(String(300), default="")
    created_by: Mapped[str] = mapped_column(String(50), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    supplier = relationship("Supplier")
    items = relationship("PurchaseItem", cascade="all, delete-orphan", order_by="PurchaseItem.id")


class PurchaseItem(Base):
    __tablename__ = "purchase_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(ForeignKey("purchases.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    item_name: Mapped[str] = mapped_column(String(150))
    hsn: Mapped[str] = mapped_column(String(20), default="")
    unit: Mapped[str] = mapped_column(String(20), default="NOS")
    qty: Mapped[float] = mapped_column(Float)
    rate: Mapped[float] = mapped_column(Float)
    gross: Mapped[float] = mapped_column(Float)
    discount: Mapped[float] = mapped_column(Float, default=0)
    taxable: Mapped[float] = mapped_column(Float)
    gst_rate: Mapped[float] = mapped_column(Float)
    cgst: Mapped[float] = mapped_column(Float, default=0)
    sgst: Mapped[float] = mapped_column(Float, default=0)
    igst: Mapped[float] = mapped_column(Float, default=0)
    total: Mapped[float] = mapped_column(Float)
    returned_qty: Mapped[float] = mapped_column(Float, default=0)


class Note(Base):
    """Credit note (sales return / reduction against a bill) or debit note (purchase return)."""
    __tablename__ = "notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    note_type: Mapped[str] = mapped_column(String(10))  # CREDIT / DEBIT
    note_no: Mapped[str] = mapped_column(String(40), unique=True)
    fy_id: Mapped[int] = mapped_column(ForeignKey("financial_years.id"))
    note_date: Mapped[date] = mapped_column(Date, index=True)
    bill_id: Mapped[int | None] = mapped_column(ForeignKey("bills.id"), nullable=True)
    purchase_id: Mapped[int | None] = mapped_column(ForeignKey("purchases.id"), nullable=True)
    ref_doc_no: Mapped[str] = mapped_column(String(50), default="")
    ref_doc_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    party_name: Mapped[str] = mapped_column(String(150), default="")
    party_gstin: Mapped[str] = mapped_column(String(15), default="")
    place_of_supply: Mapped[str] = mapped_column(String(2), default="")
    supply_type: Mapped[str] = mapped_column(String(10), default="INTRA")
    reason: Mapped[str] = mapped_column(String(300), default="")
    taxable: Mapped[float] = mapped_column(Float, default=0)
    cgst: Mapped[float] = mapped_column(Float, default=0)
    sgst: Mapped[float] = mapped_column(Float, default=0)
    igst: Mapped[float] = mapped_column(Float, default=0)
    total: Mapped[float] = mapped_column(Float, default=0)
    settlement_mode: Mapped[str] = mapped_column(String(10), default="CASH")  # CASH / UPI / ADJUST
    settlement_ref: Mapped[str] = mapped_column(String(60), default="")
    restock: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(50), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    items = relationship("NoteItem", cascade="all, delete-orphan", order_by="NoteItem.id")


class NoteItem(Base):
    __tablename__ = "note_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    item_name: Mapped[str] = mapped_column(String(150))
    hsn: Mapped[str] = mapped_column(String(20), default="")
    unit: Mapped[str] = mapped_column(String(20), default="NOS")
    qty: Mapped[float] = mapped_column(Float)
    rate: Mapped[float] = mapped_column(Float)
    taxable: Mapped[float] = mapped_column(Float)
    gst_rate: Mapped[float] = mapped_column(Float)
    tax_category: Mapped[str] = mapped_column(String(20), default="TAXABLE")
    cgst: Mapped[float] = mapped_column(Float, default=0)
    sgst: Mapped[float] = mapped_column(Float, default=0)
    igst: Mapped[float] = mapped_column(Float, default=0)
    total: Mapped[float] = mapped_column(Float)


class SupplierPayment(Base):
    __tablename__ = "supplier_payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    purchase_id: Mapped[int | None] = mapped_column(ForeignKey("purchases.id"), nullable=True)
    payment_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[float] = mapped_column(Float)
    mode: Mapped[str] = mapped_column(String(10))  # CASH / UPI
    reference: Mapped[str] = mapped_column(String(60), default="")
    remarks: Mapped[str] = mapped_column(String(300), default="")
    is_cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(50), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    supplier = relationship("Supplier")


class Expense(Base):
    __tablename__ = "expenses"
    id: Mapped[int] = mapped_column(primary_key=True)
    expense_date: Mapped[date] = mapped_column(Date, index=True)
    category: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(String(300), default="")
    paid_to: Mapped[str] = mapped_column(String(120), default="")
    amount: Mapped[float] = mapped_column(Float)
    mode: Mapped[str] = mapped_column(String(10))  # CASH / UPI
    reference: Mapped[str] = mapped_column(String(60), default="")
    is_cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(50), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class CashEntry(Base):
    """Other money in/out that is not a sale, expense or supplier payment (e.g. cash added, bank deposit)."""
    __tablename__ = "cash_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    direction: Mapped[str] = mapped_column(String(3))  # IN / OUT
    mode: Mapped[str] = mapped_column(String(10), default="CASH")  # CASH / UPI
    category: Mapped[str] = mapped_column(String(60))
    amount: Mapped[float] = mapped_column(Float)
    reference: Mapped[str] = mapped_column(String(60), default="")
    remarks: Mapped[str] = mapped_column(String(300), default="")
    is_cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(50), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class DailyClosing(Base):
    __tablename__ = "daily_closings"
    id: Mapped[int] = mapped_column(primary_key=True)
    closing_date: Mapped[date] = mapped_column(Date, unique=True)
    opening_cash: Mapped[float] = mapped_column(Float, default=0)
    cash_sales: Mapped[float] = mapped_column(Float, default=0)
    other_cash_in: Mapped[float] = mapped_column(Float, default=0)
    cash_expenses: Mapped[float] = mapped_column(Float, default=0)
    cash_supplier_payments: Mapped[float] = mapped_column(Float, default=0)
    cash_refunds: Mapped[float] = mapped_column(Float, default=0)
    other_cash_out: Mapped[float] = mapped_column(Float, default=0)
    expected_cash: Mapped[float] = mapped_column(Float, default=0)
    actual_cash: Mapped[float] = mapped_column(Float, default=0)
    difference: Mapped[float] = mapped_column(Float, default=0)
    upi_sales: Mapped[float] = mapped_column(Float, default=0)
    upi_in_other: Mapped[float] = mapped_column(Float, default=0)
    upi_out: Mapped[float] = mapped_column(Float, default=0)
    total_sales: Mapped[float] = mapped_column(Float, default=0)
    total_tax: Mapped[float] = mapped_column(Float, default=0)
    total_bills: Mapped[int] = mapped_column(Integer, default=0)
    cancelled_bills: Mapped[int] = mapped_column(Integer, default=0)
    remarks: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(10), default="CLOSED")  # CLOSED / REOPENED
    closed_by: Mapped[str] = mapped_column(String(50), default="")
    closed_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class MonthlyClosing(Base):
    __tablename__ = "monthly_closings"
    __table_args__ = (UniqueConstraint("year", "month"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    total_sales: Mapped[float] = mapped_column(Float, default=0)
    taxable_sales: Mapped[float] = mapped_column(Float, default=0)
    output_cgst: Mapped[float] = mapped_column(Float, default=0)
    output_sgst: Mapped[float] = mapped_column(Float, default=0)
    output_igst: Mapped[float] = mapped_column(Float, default=0)
    purchases: Mapped[float] = mapped_column(Float, default=0)
    input_gst: Mapped[float] = mapped_column(Float, default=0)
    expenses: Mapped[float] = mapped_column(Float, default=0)
    cash_sales: Mapped[float] = mapped_column(Float, default=0)
    upi_sales: Mapped[float] = mapped_column(Float, default=0)
    cost_of_sales: Mapped[float] = mapped_column(Float, default=0)
    profit_estimate: Mapped[float] = mapped_column(Float, default=0)
    total_bills: Mapped[int] = mapped_column(Integer, default=0)
    remarks: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(10), default="CLOSED")
    closed_by: Mapped[str] = mapped_column(String(50), default="")
    closed_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    username: Mapped[str] = mapped_column(String(50), default="")
    action: Mapped[str] = mapped_column(String(50))
    entity: Mapped[str] = mapped_column(String(50), default="")
    entity_id: Mapped[str] = mapped_column(String(50), default="")
    details: Mapped[str] = mapped_column(Text, default="")
