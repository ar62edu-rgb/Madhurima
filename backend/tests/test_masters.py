from datetime import date

from conftest import make_user, pay_exact

TODAY = date.today()
FY_START = TODAY.year if TODAY.month >= 4 else TODAY.year - 1


def test_financial_year_close_locks_its_dates(admin):
    current = next(f for f in admin.get("/api/financial-years") if f["is_current"])
    admin.post(f"/api/financial-years/{current['id']}/close", expect=400)  # not ended yet
    prev = admin.post("/api/financial-years", {"start_year": FY_START - 1})
    admin.post("/api/financial-years", {"start_year": FY_START - 1}, expect=400)
    admin.post(f"/api/financial-years/{prev['id']}/close")
    old_day = f"{FY_START - 1}-06-15"
    admin.post("/api/expenses", {"expense_date": old_day, "category": "Rent", "amount": 1000, "mode": "CASH"},
               expect=400)
    admin.post(f"/api/financial-years/{prev['id']}/reopen")
    admin.post("/api/expenses", {"expense_date": old_day, "category": "Rent", "amount": 1000, "mode": "CASH"})


def test_bill_numbering_uses_financial_year_name(admin, products):
    bill = admin.post("/api/bills", pay_exact(admin, {"items": [{"product_id": products["Tea"]["id"], "qty": 1}]}))
    fy = f"{FY_START}-{str(FY_START + 1)[2:]}"
    assert bill["bill_no"] == f"MFR/{fy[2:]}/00001"


def test_supplier_ledger_balance(admin, products):
    sup = admin.post("/api/suppliers", {"name": "Fresh Farms", "opening_balance": 1000})
    pur = admin.post("/api/purchases", {"supplier_id": sup["id"], "supplier_invoice_no": "A1",
                                        "invoice_date": TODAY.isoformat(),
                                        "items": [{"product_id": products["Onion"]["id"], "qty": 10, "rate": 40}],
                                        "paid_cash": 100})
    admin.post("/api/supplier-payments", {"supplier_id": sup["id"], "payment_date": TODAY.isoformat(),
                                          "amount": 500, "mode": "UPI", "reference": "UTR5"})
    led = admin.get(f"/api/suppliers/{sup['id']}/ledger")
    assert led["summary"]["outstanding"] == 1000 + pur["grand_total"] - 100 - 500 == 800
    assert led["entries"][-1]["balance"] == 800
    listed = next(s for s in admin.get("/api/suppliers") if s["id"] == sup["id"])
    assert listed["outstanding"] == 800


def test_customer_bill_history_and_gstin_state(admin, products):
    cust = admin.post("/api/customers", {"name": "Anil", "phone": "9876543210", "gstin": "32aaacb1234c1z1"})
    assert (cust["gstin"], cust["state_code"], cust["state"]) == ("32AAACB1234C1Z1", "32", "Kerala")
    admin.post("/api/customers", {"name": "Bad", "gstin": "32AA"}, expect=400)
    body = pay_exact(admin, {"items": [{"product_id": products["Tea"]["id"], "qty": 1}], "customer_id": cust["id"]})
    bill = admin.post("/api/bills", body)
    assert bill["customer_name"] == "Anil"
    assert bill["invoice_type"] == "B2B"
    assert [b["id"] for b in admin.get(f"/api/customers/{cust['id']}/bills")] == [bill["id"]]


def test_product_code_unique_and_recipe_rules(admin, products):
    admin.post("/api/products", {"code": "M001", "name": "Copy"}, expect=400)
    p = admin.post("/api/products", {"code": "N1", "name": "Ghee Roast", "selling_price": 90, "opening_stock": 5})
    assert p["current_stock"] == 5
    admin.put(f"/api/products/{p['id']}/recipe", [{"ingredient_id": p["id"], "quantity": 1}], expect=400)
    out = admin.put(f"/api/products/{p['id']}/recipe", [{"ingredient_id": products["Onion"]["id"], "quantity": 0.1}])
    assert out["use_recipe"] is True


def test_user_management(admin):
    me = admin.get("/api/auth/me")
    admin.put(f"/api/users/{me['id']}", {"username": "admin", "role": "cashier"}, expect=400)
    admin.post("/api/users", {"username": "admin", "password": "secret123", "role": "cashier"}, expect=400)
    admin.post("/api/users", {"username": "shortpw", "password": "123", "role": "cashier"}, expect=400)
    mgr = make_user(admin, "manager1", role="manager")
    mgr.get("/api/purchases")
    mgr.put("/api/settings", {"address": "x"}, expect=403)
    uid = next(u["id"] for u in admin.get("/api/users") if u["username"] == "manager1")
    admin.put(f"/api/users/{uid}", {"username": "manager1", "role": "manager", "is_active": False})
    mgr.get("/api/purchases", expect=401)  # deactivated user is logged out


def test_audit_log_records_actions(admin, products):
    admin.post("/api/bills", pay_exact(admin, {"items": [{"product_id": products["Tea"]["id"], "qty": 1}]}))
    logs = admin.get("/api/audit-logs")
    rows = logs if isinstance(logs, list) else logs.get("rows", [])
    actions = {r["action"] for r in rows}
    assert {"SETUP", "UPDATE_SETTINGS", "CREATE_BILL"} <= actions
