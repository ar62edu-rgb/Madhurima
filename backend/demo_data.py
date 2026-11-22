"""Fill a FRESH install with realistic demo data for manual testing (never use on a restaurant with real data).

It goes through the application's own route handlers, so bill numbers, GST, stock movements, audit log and
closings are exactly what the real screens would produce. To build a history it moves the app's clock back
to each past day while that day's entries are made.

Run inside the app container (from the project folder):
    docker compose exec -T app python - --yes < backend/demo_data.py > demo-admin.txt
    docker compose exec -T app python - --yes --admin <your-admin> < backend/demo_data.py > demo-admin.txt
The first form creates user "admin"; the second uses the admin you made on the first-time setup screen.
Generated passwords (admin in the first form, "cashier1" always) are printed once to stdout: keep them in
the git-ignored demo-admin.txt. It refuses to run on a database that already has bills, purchases or parties."""
import argparse
import random
import secrets
import sys
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select

from app import models
from app.db import Base, SessionLocal, engine
from app.models import Product, User
from app.routers import auth, billing, finance, masters, purchases, stock
from app.seed import seed_base, seed_sample

TIME_MODULES = [billing, finance, purchases, stock, masters]


# ---------------- clock control ----------------
_fake_now: datetime | None = None


class _FakeDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return _fake_now if _fake_now else datetime.now(tz)


class _FakeDate(date):
    @classmethod
    def today(cls):
        return _fake_now.date() if _fake_now else date.today()


@contextmanager
def clock():
    """Patch the app's notion of 'now' / 'today' while demo data is created."""
    import app.services as services
    saved = [(models, "datetime", models.datetime)] + [(m, "date", m.date) for m in TIME_MODULES + [services]]
    models.datetime = _FakeDateTime
    for m in TIME_MODULES + [services]:
        m.date = _FakeDate
    try:
        yield
    finally:
        for mod, name, val in saved:
            setattr(mod, name, val)


def set_time(d: date, hh: int, mm: int = 0):
    global _fake_now
    _fake_now = datetime.combine(d, time(hh % 24, mm % 60))


# ---------------- data ----------------
SUPPLIERS = [
    dict(name="Kochi Rice Traders", gstin="32AAKCR4521M1Z3", phone="9847000001", contact_person="Rafeeq"),
    dict(name="Malabar Poultry Farm", gstin="32ABMPF7788K1Z9", phone="9847000002", contact_person="Shaji"),
    dict(name="Ernakulam Spices & Oils", gstin="32AAESO1122L1Z4", phone="9847000003", contact_person="Jose"),
    dict(name="Bengaluru Pack Solutions", gstin="29AABCB3344P1Z7", phone="9845000004", contact_person="Ravi",
         opening_balance=1500),
    dict(name="Local Vegetable Market", gstin="", phone="9847000005", contact_person="Babu"),
]
CUSTOMERS = [
    dict(name="Infopark Tech Solutions Pvt Ltd", gstin="32AACCI9988Q1Z2", phone="9846100001",
         address="Infopark Phase 1, Kakkanad"),
    dict(name="Bangalore Events LLP", gstin="29AAJFB5566R1Z8", phone="9845100002", address="Indiranagar, Bengaluru"),
    dict(name="Anil Kumar", phone="9846100003"),
    dict(name="Sreeja Menon", phone="9846100004"),
    dict(name="Fathima Beevi", phone="9846100005"),
]
# supplier index, product name, qty, rate, gst
PURCHASE_PLAN = [
    (0, "Basmati Rice", 25, 108, 5),
    (1, "Chicken", 12, 215, 0),
    (2, "Biriyani Masala", 2, 590, 5),
    (2, "Cooking Oil", 15, 138, 5),
    (4, "Onion", 20, 38, 0),
    (3, "Parcel Container", 300, 6, 18),
]
EXPENSES = [("Gas / Fuel", 900, 1400), ("Vegetables (petty)", 300, 800), ("Cleaning", 100, 300),
            ("Transport", 150, 400)]
POPULAR = ["Chicken Biriyani", "Kerala Meals", "Tea", "Coffee", "Kerala Parotta", "Beef Fry", "Chicken Curry",
           "Masala Dosa", "Lime Juice", "Pazhampori", "Fish Curry Meals", "Veg Biriyani", "Chapathi",
           "Chicken 65", "Payasam", "Mineral Water 1L", "Mutton Biriyani", "Appam", "Idli (2 nos)"]


class Demo:
    def __init__(self, db, rnd: random.Random):
        self.db, self.rnd = db, rnd
        self.stats = {"bills": 0, "cancelled": 0, "credit_notes": 0, "purchases": 0, "debit_notes": 0,
                      "expenses": 0, "closed_days": 0, "closed_months": 0}

    def call(self, fn, *args):
        try:
            return fn(*args, user=self.admin, db=self.db)
        except HTTPException:
            self.db.rollback()
            raise

    # ----- setup -----
    def setup(self, admin_username: str | None = None):
        pw_cashier = secrets.token_urlsafe(12)
        if admin_username:
            pw_admin = None
            self.admin = self.db.scalars(select(User).where(User.username == admin_username.strip().lower())).one()
            if not self.db.scalars(select(Product).where(Product.name == "Chicken Biriyani")).first():
                seed_base(self.db)
                seed_sample(self.db, self.admin.username)
                self.db.commit()
        else:
            pw_admin = secrets.token_urlsafe(12)
            auth.setup(auth.SetupIn(restaurant_name="Madhurima Family Restaurant", full_name="Demo Admin",
                                    username="admin", password=pw_admin, load_sample_data=True), db=self.db)
            self.admin = self.db.scalars(select(User).where(User.username == "admin")).one()
        masters.write_settings({"address": "DEMO DATA - MG Road", "city": "Kochi", "pincode": "682011",
                                "phone": "0484-0000000", "gstin": "32ABCDE1234F1Z5", "fssai": "11300000000000",
                                "show_upi_qr_text": "madhurima@upi"}, user=self.admin, db=self.db)
        auth.create_user(auth.UserIn(username="cashier1", full_name="Demo Cashier", password=pw_cashier,
                                     role="cashier", can_discount=True), admin=self.admin, db=self.db)
        self.products = {p.name: p.id for p in self.db.scalars(select(Product))}
        self.suppliers = [self.call(masters.create_supplier, masters.SupplierIn(**s)) for s in SUPPLIERS]
        self.customers = [self.call(masters.create_customer, masters.PartyIn(**c)) for c in CUSTOMERS]
        self.tables = [t["name"] for t in masters.list_tables(_=self.admin, db=self.db)]
        return pw_admin, pw_cashier

    # ----- one bill -----
    def bill(self, d: date, hh: int, mm: int, customer=None):
        set_time(d, hh, mm)
        r = self.rnd
        names = r.sample(POPULAR[:12] if r.random() < 0.8 else POPULAR, r.randint(1, 4))
        items = [{"product_id": self.products[n], "qty": r.choice([1, 1, 1, 2, 2, 3])} for n in names]
        if r.random() < 0.08:
            items[0]["discount"] = 10
        body = {"items": items, "order_type": r.choice(["DINE_IN"] * 6 + ["TAKEAWAY"] * 3 + ["DELIVERY"])}
        if body["order_type"] == "DINE_IN":
            body["table_name"] = r.choice(self.tables)
        want_bill_discount = r.random() < 0.05
        if customer:
            body["customer_id"] = customer["id"]
            for it in items:
                it["qty"] *= r.choice([5, 8, 10])  # office / event orders are larger
        elif r.random() < 0.15:
            c = r.choice(self.customers[2:])
            body.update(customer_id=c["id"])
        total = self.call(billing.preview, billing.BillIn(**body))["totals"]["grand_total"]
        if want_bill_discount and total > 200:
            body["bill_discount"] = 20
            total = self.call(billing.preview, billing.BillIn(**body))["totals"]["grand_total"]
        kind = r.random()
        if kind < 0.5:
            body.update(cash_amount=total, cash_tendered=(int(total // 100) + 1) * 100 if total % 100 else total)
        elif kind < 0.85:
            body.update(upi_amount=total, upi_ref=f"4{r.randint(10**10, 10**11 - 1)}")
        else:
            cash = min(total, r.choice([100, 200, 500]))
            body.update(cash_amount=cash, upi_amount=round(total - cash, 2),
                        upi_ref=f"4{r.randint(10**10, 10**11 - 1)}")
            if body["upi_amount"] <= 0:
                body.pop("upi_ref")
                body["upi_amount"] = 0
        b = self.call(billing.create_bill, billing.BillIn(**body))
        self.stats["bills"] += 1
        return b

    # ----- one day -----
    def day(self, d: date, close: bool, idx: int):
        r = self.rnd
        weekend = d.weekday() >= 5
        n = r.randint(14, 22) if weekend else r.randint(9, 16)
        bills = []
        minutes = sorted(r.sample(range(8 * 60, 22 * 60), n))
        for m in minutes:
            bills.append(self.bill(d, m // 60, m % 60))
        if idx % 5 == 1:
            bills.append(self.bill(d, 13, 30, customer=self.customers[0]))  # intra-state B2B
        if idx % 9 == 4:
            bills.append(self.bill(d, 19, 45, customer=self.customers[1]))  # inter-state B2B -> IGST
        if idx % 4 == 2 and len(bills) > 3:
            b = bills.pop(r.randrange(len(bills)))
            set_time(d, 22, 5)
            self.call(billing.cancel_bill, b["id"], billing.CancelIn(reason=r.choice(
                ["Customer left before serving", "Wrong items entered", "Duplicate bill"])))
            self.stats["cancelled"] += 1
        if idx % 7 == 3 and bills:
            b = bills[0]
            set_time(d, 22, 10)
            self.call(billing.create_credit_note, billing.CreditIn(
                bill_id=b["id"], items=[{"bill_item_id": b["items"][0]["id"], "qty": 1}],
                reason="Item returned - not as ordered", settlement_mode="CASH" if b["cash_amount"] else "UPI"))
            self.stats["credit_notes"] += 1

        if idx % 4 == 0:
            set_time(d, 10, 15)
            for line_i, (sup_i, name, qty, rate, gst) in enumerate(PURCHASE_PLAN):
                if name == "Parcel Container" and idx % 9:
                    continue
                total_paid = r.random()
                sup = self.suppliers[sup_i]
                body = purchases.PurchaseIn(
                    supplier_id=sup["id"], supplier_invoice_no=f"{sup['name'][:3].upper()}-{d:%m%d}-{line_i}",
                    invoice_date=d, items=[{"product_id": self.products[name],
                                            "qty": max(1, round(qty * r.uniform(0.5, 0.8))), "rate": rate, "gst_rate": gst}])
                pur = self.call(purchases.create_purchase, body)
                if total_paid < 0.5:
                    paid = pur["grand_total"]
                elif total_paid < 0.8:
                    paid = round(pur["grand_total"] / 2)
                else:
                    paid = 0
                if paid:
                    self.call(purchases.create_payment, purchases.PaymentIn(
                        supplier_id=sup["id"], purchase_id=pur["id"], payment_date=d, amount=paid,
                        mode="CASH" if paid < 2000 else "UPI", reference="" if paid < 2000 else f"UTR{d:%m%d}{sup_i}"))
                self.stats["purchases"] += 1
                if idx == 8 and name == "Chicken":
                    set_time(d, 11, 0)
                    self.call(purchases.purchase_return, pur["id"], purchases.ReturnIn(
                        items=[{"purchase_item_id": pur["items"][0]["id"], "qty": 2}], reason="Spoiled on arrival"))
                    self.stats["debit_notes"] += 1
                    set_time(d, 10, 15)

        set_time(d, 16, 0)
        for cat, lo, hi in EXPENSES:
            if cat == "Gas / Fuel" and idx % 4:
                continue
            self.call(finance.create_expense, finance.ExpenseIn(
                expense_date=d, category=cat, amount=r.randrange(lo, hi, 10), mode=r.choice(["CASH", "CASH", "UPI"]),
                paid_to="Demo vendor"))
            self.stats["expenses"] += 1
        if d.day == 1:
            for cat, amt in (("Electricity", 8400), ("Rent", 25000), ("Internet / Phone", 1199)):
                self.call(finance.create_expense, finance.ExpenseIn(expense_date=d, category=cat, amount=amt,
                                                                    mode="UPI", reference=f"NEFT{d:%m%d}"))
                self.stats["expenses"] += 1
        if idx % 6 == 5:
            self.call(stock.adjust, stock.AdjustIn(product_id=self.products["Onion"], movement_type="WASTAGE",
                                                   direction="REDUCE", qty=1.5, remarks="Spoiled onions"))
        if idx % 7 == 0:
            self.call(finance.create_cash_entry, finance.CashEntryIn(
                entry_date=d, direction="OUT", category="Bank Deposit", amount=5000, remarks="Deposited to SBI"))

        if close:
            set_time(d, 23, 0)
            s = finance.day_summary(self.db, d)
            # first closing starts the till with a ₹10,000 float; later days carry the counted cash forward
            opening = s["opening_cash"] if s["previous_closing_date"] else 10000
            expected = finance.expected_cash(s, opening)
            diff = r.choice([0, 0, 0, -10, 20, -50])
            self.call(finance.close_day, finance.DailyCloseIn(
                closing_date=d, opening_cash=opening, actual_cash=max(expected + diff, 0),
                remarks="" if not diff else "Counted difference"))
            self.stats["closed_days"] += 1


def _has_transactions(db) -> bool:
    return any(db.scalar(select(func.count()).select_from(t)) for t in
               (models.Bill, models.Purchase, models.Expense, models.Note, models.CashEntry, models.DailyClosing,
                models.SupplierPayment, models.Supplier, models.Customer))


def run(db, days: int = 30, open_days: int = 3, seed: int = 2026, today: date | None = None,
        admin_username: str | None = None):
    """Creates the demo data. Returns (admin_password, cashier_password, stats).

    Empty database: creates the admin too (admin_password is generated).
    admin_username given: uses that existing admin (admin_password is None) — only allowed while the database
    has no transactions, suppliers or customers yet (e.g. right after the first-time setup screen)."""
    if admin_username:
        admin = db.scalars(select(User).where(User.username == admin_username.strip().lower())).first()
        if not admin or admin.role != "admin":
            raise SystemExit(f"No admin user named {admin_username!r}")
        if _has_transactions(db):
            raise SystemExit("This database already has bills, purchases, parties or closings. "
                             "Demo data is only for an empty install.")
    elif db.scalar(select(func.count(User.id))):
        raise SystemExit("This database already has users. Pass --admin <username> to use the existing admin "
                         "on an install that has no transactions yet.")
    today = today or date.today()
    demo = Demo(db, random.Random(seed))
    with clock():
        set_time(today - timedelta(days=days), 8, 0)
        pw_admin, pw_cashier = demo.setup(admin_username)
        start = today - timedelta(days=days)
        for i in range(days):
            d = start + timedelta(days=i)
            demo.day(d, close=i < days - open_days, idx=i)
        # close every finished month whose days are all closed
        first_open = start + timedelta(days=days - open_days)
        m = date(start.year, start.month, 1)
        while True:
            nxt = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
            if nxt > first_open or nxt > today:
                break
            set_time(nxt, 9, 0)
            demo.call(finance.close_month, finance.MonthCloseIn(year=m.year, month=m.month,
                                                                remarks="Demo month closed"))
            demo.stats["closed_months"] += 1
            m = nxt
    # a few bills and a running table order today, at the real time
    global _fake_now
    _fake_now = None
    for _ in range(3):
        demo.bill(today, datetime.now().hour, datetime.now().minute)
    billing.save_held(billing.HeldIn(table_id=1, items=[
        {"product_id": demo.products["Chicken Biriyani"], "name": "Chicken Biriyani", "qty": 2, "rate": 180},
        {"product_id": demo.products["Lime Juice"], "name": "Lime Juice", "qty": 2, "rate": 30}]),
        oid=None, user=demo.admin, db=db)
    return pw_admin, pw_cashier, demo.stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true", help="confirm: fill this empty database with demo data")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--admin", help="use this existing admin instead of creating one")
    args = ap.parse_args()
    if not args.yes:
        sys.exit("Add --yes to confirm. Only use this on a fresh, empty test install.")
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        pw_admin, pw_cashier, stats = run(db, days=args.days, admin_username=args.admin)
    print("Madhurima DEMO data loaded. Delete this file and wipe the data before real use.")
    if pw_admin:
        print(f"admin    password: {pw_admin}")
    print(f"cashier1 password: {pw_cashier}")
    print("Created:", ", ".join(f"{k}={v}" for k, v in stats.items()))


if __name__ == "__main__":
    main()
