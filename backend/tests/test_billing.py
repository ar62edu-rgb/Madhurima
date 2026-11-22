import pytest

from conftest import make_user, pay_exact


def stock(api, name):
    return next(p for p in api.get("/api/products") if p["name"] == name)["current_stock"]


def test_bill_matches_preview_and_is_numbered(admin, products):
    tea = products["Tea"]["id"]
    body = {"items": [{"product_id": tea, "qty": 3}]}
    pv = admin.post("/api/bills/preview", body)
    assert pv["supply_type"] == "INTRA"
    assert pv["totals"]["taxable"] == 45
    assert pv["totals"]["cgst"] == pv["totals"]["sgst"] == 1.13
    bill = admin.post("/api/bills", pay_exact(admin, body))
    assert bill["grand_total"] == pv["totals"]["grand_total"] == 47
    assert bill["payment_mode"] == "CASH"
    assert bill["bill_no"].startswith("MFR/") and bill["bill_no"].endswith("/00001")
    bill2 = admin.post("/api/bills", pay_exact(admin, body))
    assert bill2["bill_no"].endswith("/00002")
    assert bill["gst_breakup"] == [{"gst_rate": 5, "taxable": 45, "cgst": 1.13, "sgst": 1.13, "igst": 0}]


def test_split_payment_and_change(admin, products):
    body = {"items": [{"product_id": products["Chicken Biriyani"]["id"], "qty": 1}]}
    total = admin.post("/api/bills/preview", body)["totals"]["grand_total"]  # 189
    bill = admin.post("/api/bills", {**body, "cash_amount": total - 100, "upi_amount": 100, "upi_ref": "UTR1",
                                     "cash_tendered": 100})
    assert bill["payment_mode"] == "SPLIT"
    assert bill["change_returned"] == 100 - (total - 100)


def test_payment_must_match_total(admin, products):
    body = {"items": [{"product_id": products["Tea"]["id"], "qty": 1}], "cash_amount": 1}
    admin.post("/api/bills", body, expect=400)
    body = pay_exact(admin, {"items": [{"product_id": products["Tea"]["id"], "qty": 1}]})
    admin.post("/api/bills", {**body, "cash_tendered": 1}, expect=400)


def test_inter_state_customer_gets_igst(admin, products):
    body = {"items": [{"product_id": products["Kerala Meals"]["id"], "qty": 1}], "customer_gstin": "29AAACB1234C1Z1",
            "customer_name": "Bangalore Co"}
    bill = admin.post("/api/bills", pay_exact(admin, body))
    assert bill["supply_type"] == "INTER"
    assert bill["invoice_type"] == "B2B"
    assert (bill["igst"], bill["cgst"], bill["sgst"]) == (6, 0, 0)
    admin.post("/api/bills/preview", {**body, "customer_gstin": "29ABC"}, expect=400)


def test_prices_inclusive_setting(admin, products):
    admin.put("/api/settings", {"prices_include_gst": "true"})
    body = {"items": [{"product_id": products["Chicken Biriyani"]["id"], "qty": 1}]}
    bill = admin.post("/api/bills", pay_exact(admin, body))
    assert bill["grand_total"] == 180
    assert round(bill["taxable_amount"] + bill["total_tax"], 2) == 180


def test_composition_dealer_bills_without_tax(admin, products):
    admin.put("/api/settings", {"gst_registration_type": "COMPOSITION"})
    body = {"items": [{"product_id": products["Tea"]["id"], "qty": 2}]}
    bill = admin.post("/api/bills", pay_exact(admin, body))
    assert bill["total_tax"] == 0
    assert bill["grand_total"] == 30


def test_recipe_deducts_ingredients_and_cancel_restores(admin, products):
    rice_before = stock(admin, "Basmati Rice")
    chicken_before = stock(admin, "Chicken")
    body = {"items": [{"product_id": products["Chicken Biriyani"]["id"], "qty": 2}]}
    bill = admin.post("/api/bills", pay_exact(admin, body))
    assert stock(admin, "Basmati Rice") == pytest.approx(rice_before - 0.3)
    assert stock(admin, "Chicken") == pytest.approx(chicken_before - 0.4)
    assert bill["cost_amount"] > 0

    admin.post(f"/api/bills/{bill['id']}/cancel", {"reason": "Wrong order"})
    assert stock(admin, "Basmati Rice") == pytest.approx(rice_before)
    assert stock(admin, "Chicken") == pytest.approx(chicken_before)
    admin.post(f"/api/bills/{bill['id']}/cancel", {"reason": "Again"}, expect=400)
    assert admin.get(f"/api/bills/{bill['id']}")["status"] == "CANCELLED"


def test_negative_stock_can_be_blocked(admin, products):
    admin.put("/api/settings", {"allow_negative_stock": "false"})
    body = {"items": [{"product_id": products["Chicken Biriyani"]["id"], "qty": 1000}]}
    admin.post("/api/bills", pay_exact(admin, body), expect=400)


def test_cashier_permissions(admin, products):
    tea = products["Tea"]["id"]
    cashier = make_user(admin, "cashier1", can_discount=False, can_edit_price=False, can_cancel_bill=False)
    cashier.post("/api/bills/preview", {"items": [{"product_id": tea, "qty": 1, "discount": 1}]}, expect=403)
    cashier.post("/api/bills/preview", {"items": [{"product_id": tea, "qty": 1}], "bill_discount": 1}, expect=403)
    cashier.post("/api/bills/preview", {"items": [{"product_id": tea, "qty": 1, "rate": 1}]}, expect=403)
    bill = cashier.post("/api/bills", pay_exact(cashier, {"items": [{"product_id": tea, "qty": 1}]}))
    cashier.post(f"/api/bills/{bill['id']}/cancel", {"reason": "Mistake"}, expect=403)
    cashier.post("/api/credit-notes", {"bill_id": bill["id"], "reason": "Return",
                                      "items": [{"bill_item_id": bill["items"][0]["id"], "qty": 1}]}, expect=403)


def test_credit_note_limits_and_blocks_cancel(admin, products):
    body = {"items": [{"product_id": products["Tea"]["id"], "qty": 3}]}
    bill = admin.post("/api/bills", pay_exact(admin, body))
    item = bill["items"][0]["id"]
    cn = admin.post("/api/credit-notes", {"bill_id": bill["id"], "reason": "Spilled",
                                          "items": [{"bill_item_id": item, "qty": 1}]})
    assert cn["note_no"].startswith("CN/")
    assert cn["taxable"] == 15
    assert cn["total"] == round(cn["taxable"] + cn["cgst"] + cn["sgst"], 2)
    admin.post("/api/credit-notes", {"bill_id": bill["id"], "reason": "Too many",
                                     "items": [{"bill_item_id": item, "qty": 3}]}, expect=400)
    admin.post(f"/api/bills/{bill['id']}/cancel", {"reason": "Has note"}, expect=400)
    assert admin.get(f"/api/bills/{bill['id']}")["credit_notes"][0]["note_no"] == cn["note_no"]


def test_held_order_kot_flow(admin, products):
    tables = admin.get("/api/tables")
    tea = products["Tea"]
    held = admin.post("/api/held-orders", {"table_id": tables[0]["id"],
                                           "items": [{"product_id": tea["id"], "name": "Tea", "qty": 2, "rate": 15}]})
    admin.post("/api/held-orders", {"table_id": tables[0]["id"], "items": []}, expect=400)  # table busy
    kot = admin.post(f"/api/held-orders/{held['id']}/kot")
    assert kot["kot_items"] == [{"name": "Tea", "qty": 2, "note": ""}]
    admin.post(f"/api/held-orders/{held['id']}/kot", expect=400)  # nothing new
    body = pay_exact(admin, {"items": [{"product_id": tea["id"], "qty": 2}], "held_order_id": held["id"]})
    admin.post("/api/bills", body)
    assert admin.get("/api/held-orders") == []


def test_inactive_product_cannot_be_billed(admin, products):
    tea = admin.get(f"/api/products/{products['Tea']['id']}")
    fields = {k: tea[k] for k in ("code", "name", "category_id", "subcategory", "product_type", "hsn", "unit",
                                  "purchase_price", "selling_price", "gst_rate", "tax_category", "min_stock",
                                  "max_stock", "track_stock", "use_recipe")}
    admin.put(f"/api/products/{tea['id']}", {**fields, "is_active": False})
    admin.post("/api/bills/preview", {"items": [{"product_id": tea["id"], "qty": 1}]}, expect=400)
