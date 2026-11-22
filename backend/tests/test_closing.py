"""Daily / monthly closing: expected cash and period locks."""
from datetime import date, timedelta

from conftest import pay_exact

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
LAST_MONTH_END = TODAY.replace(day=1) - timedelta(days=1)


def tea_bill(api, products, qty=3, expect=200):
    body = pay_exact(api, {"items": [{"product_id": products["Tea"]["id"], "qty": qty}]})
    return api.post("/api/bills", body, expect=expect)


def expense(api, day, amount=20, expect=200):
    return api.post("/api/expenses", {"expense_date": day.isoformat(), "category": "Gas / Fuel", "amount": amount,
                                      "mode": "CASH"}, expect=expect)


def test_expected_cash_formula(admin, products):
    bill = tea_bill(admin, products)  # 47 cash
    upi_body = pay_exact(admin, {"items": [{"product_id": products["Coffee"]["id"], "qty": 1}]})
    admin.post("/api/bills", {**upi_body, "cash_amount": 0, "upi_amount": upi_body["cash_amount"]})
    expense(admin, TODAY, 20)
    admin.post("/api/cash-entries", {"entry_date": TODAY.isoformat(), "direction": "IN", "category": "Cash Added",
                                     "amount": 100})
    admin.post("/api/cash-entries", {"entry_date": TODAY.isoformat(), "direction": "OUT", "category": "Bank Deposit",
                                     "amount": 30})
    day = admin.get("/api/daily-closing")
    assert day["cash_sales"] == bill["grand_total"] == 47
    assert day["upi_sales"] == 21
    assert day["total_bills"] == 2
    assert day["expected_cash"] == 0 + 47 + 100 - 20 - 30

    closed = admin.post("/api/daily-closing", {"closing_date": TODAY.isoformat(), "opening_cash": 500,
                                               "actual_cash": 590})
    assert closed["expected_cash"] == 597
    assert closed["difference"] == -7
    assert closed["status"] == "CLOSED"


def test_closed_day_blocks_entries_until_reopened(admin, products):
    bill = tea_bill(admin, products)
    admin.post("/api/daily-closing", {"closing_date": TODAY.isoformat(), "opening_cash": 0, "actual_cash": 47})
    tea_bill(admin, products, expect=400)
    expense(admin, TODAY, expect=400)
    admin.post(f"/api/bills/{bill['id']}/cancel", {"reason": "Too late"}, expect=400)
    admin.post("/api/daily-closing", {"closing_date": TODAY.isoformat(), "opening_cash": 0, "actual_cash": 47},
               expect=400)

    admin.post(f"/api/daily-closing/{TODAY.isoformat()}/reopen")
    tea_bill(admin, products)
    expense(admin, TODAY)


def test_closing_rules(admin):
    tomorrow = (TODAY + timedelta(days=1)).isoformat()
    admin.post("/api/daily-closing", {"closing_date": tomorrow, "opening_cash": 0, "actual_cash": 0}, expect=400)
    admin.post("/api/daily-closing", {"closing_date": TODAY.isoformat(), "opening_cash": 0, "actual_cash": 0})
    # an earlier day cannot be closed after a later one
    admin.post("/api/daily-closing", {"closing_date": YESTERDAY.isoformat(), "opening_cash": 0, "actual_cash": 0},
               expect=400)


def test_closing_cash_is_carried_forward(admin):
    admin.post("/api/daily-closing", {"closing_date": YESTERDAY.isoformat(), "opening_cash": 0, "actual_cash": 750})
    day = admin.get("/api/daily-closing")
    assert day["carried_forward_cash"] == 750
    assert day["opening_cash"] == 750
    assert day["expected_cash"] == 750


def test_monthly_closing_locks_the_month(admin, products):
    y, m = LAST_MONTH_END.year, LAST_MONTH_END.month
    admin.post("/api/monthly-closing", {"year": TODAY.year, "month": TODAY.month}, expect=400)  # not ended yet
    mc = admin.post("/api/monthly-closing", {"year": y, "month": m})
    assert mc["status"] == "CLOSED"
    admin.post("/api/monthly-closing", {"year": y, "month": m}, expect=400)
    expense(admin, LAST_MONTH_END, expect=400)
    admin.post("/api/daily-closing", {"closing_date": LAST_MONTH_END.isoformat(), "opening_cash": 0,
                                      "actual_cash": 0}, expect=400)
    sup = admin.post("/api/suppliers", {"name": "Fresh Farms"})
    admin.post("/api/purchases", {"supplier_id": sup["id"], "supplier_invoice_no": "OLD-1",
                                  "invoice_date": LAST_MONTH_END.isoformat(),
                                  "items": [{"product_id": products["Onion"]["id"], "qty": 1, "rate": 40}]},
               expect=400)
    expense(admin, TODAY)  # current month is still open

    admin.post(f"/api/monthly-closing/{y}/{m}/reopen")
    expense(admin, LAST_MONTH_END)


def test_month_with_unclosed_bill_days_cannot_close(admin, products):
    tea_bill(admin, products)
    s = admin.get(f"/api/monthly-closing?year={TODAY.year}&month={TODAY.month}")
    assert s["unclosed_days"] == [TODAY.isoformat()]
    assert s["total_bills"] == 1
