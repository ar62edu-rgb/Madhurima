from datetime import date

import pytest

from conftest import make_user

TODAY = date.today().isoformat()
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def stock(api, pid):
    return api.get(f"/api/products/{pid}")["current_stock"]


@pytest.fixture
def supplier(admin):
    return admin.post("/api/suppliers", {"name": "Fresh Farms", "gstin": "32AAACF1111A1Z1"})


def purchase(api, supplier, product_id, inv="FF-1", qty=10, rate=105, gst=5, expect=200, **extra):
    return api.post("/api/purchases", {"supplier_id": supplier["id"], "supplier_invoice_no": inv,
                                       "invoice_date": TODAY,
                                       "items": [{"product_id": product_id, "qty": qty, "rate": rate,
                                                  "gst_rate": gst}], **extra}, expect=expect)


def test_purchase_adds_stock_and_tracks_payment(admin, products, supplier):
    rice = products["Basmati Rice"]["id"]
    before = stock(admin, rice)
    pur = purchase(admin, supplier, rice, paid_cash=500)
    assert pur["purchase_no"].startswith("PUR/")
    assert (pur["taxable_amount"], pur["cgst"], pur["sgst"], pur["igst"]) == (1050, 26.25, 26.25, 0)
    assert pur["grand_total"] == 1103  # 1102.50 rounded
    assert (pur["paid_amount"], pur["balance"], pur["payment_status"]) == (500, 603, "PARTIAL")
    assert stock(admin, rice) == pytest.approx(before + 10)
    assert admin.get(f"/api/products/{rice}")["purchase_price"] == 105

    admin.post("/api/supplier-payments", {"supplier_id": supplier["id"], "purchase_id": pur["id"],
                                          "payment_date": TODAY, "amount": 700, "mode": "UPI"}, expect=400)
    admin.post("/api/supplier-payments", {"supplier_id": supplier["id"], "purchase_id": pur["id"],
                                          "payment_date": TODAY, "amount": 603, "mode": "UPI"})
    assert admin.get(f"/api/purchases/{pur['id']}")["payment_status"] == "PAID"


def test_inter_state_supplier_uses_igst(admin, products):
    sup = admin.post("/api/suppliers", {"name": "Karnataka Traders", "gstin": "29AAACK2222B1Z2"})
    pur = purchase(admin, sup, products["Cooking Oil"]["id"], qty=1, rate=100, gst=18)
    assert (pur["supply_type"], pur["igst"], pur["cgst"]) == ("INTER", 18, 0)


def test_duplicate_invoice_and_overpayment_rejected(admin, products, supplier):
    rice = products["Basmati Rice"]["id"]
    purchase(admin, supplier, rice)
    purchase(admin, supplier, rice, qty=1, rate=1, expect=400)  # same supplier invoice number
    purchase(admin, supplier, rice, inv="FF-2", qty=1, rate=100, paid_cash=500, expect=400)


def test_purchase_return_and_cancel(admin, products, supplier):
    rice = products["Basmati Rice"]["id"]
    before = stock(admin, rice)
    pur = purchase(admin, supplier, rice)
    dn = admin.post(f"/api/purchases/{pur['id']}/return",
                    {"items": [{"purchase_item_id": pur["items"][0]["id"], "qty": 1}], "reason": "Damaged bag"})
    assert dn["note_no"].startswith("DN/")
    assert dn["taxable"] == 105
    assert stock(admin, rice) == pytest.approx(before + 9)
    p2 = admin.get(f"/api/purchases/{pur['id']}")
    assert p2["return_amount"] == dn["total"]
    assert p2["balance"] == round(pur["grand_total"] - dn["total"], 2)
    admin.post(f"/api/purchases/{pur['id']}/return",
               {"items": [{"purchase_item_id": pur["items"][0]["id"], "qty": 10}], "reason": "Too many"}, expect=400)
    admin.post(f"/api/purchases/{pur['id']}/cancel", {"reason": "Has return"}, expect=400)

    other = purchase(admin, supplier, rice, inv="FF-9", paid_cash=100)
    out = admin.post(f"/api/purchases/{other['id']}/cancel", {"reason": "Entered twice"})
    assert out["payment_status"] == "CANCELLED"
    assert stock(admin, rice) == pytest.approx(before + 9)
    # a cancelled invoice number can be entered again
    purchase(admin, supplier, rice, inv="FF-9")


def test_cashier_cannot_enter_purchases(admin, products, supplier):
    cashier = make_user(admin, "cashier1")
    purchase(cashier, supplier, products["Basmati Rice"]["id"], expect=403)


def test_attachment_upload_checks_content(admin, products, supplier):
    pur = purchase(admin, supplier, products["Onion"]["id"], qty=1, rate=40, gst=0)
    url = f"/api/purchases/{pur['id']}/attachment"
    admin.req("POST", url, files={"file": ("bill.png", PNG, "image/png")})
    r = admin.req("GET", url)
    assert r.content == PNG
    admin.req("POST", url, 400, files={"file": ("bill.png", b"not an image", "image/png")})
    admin.req("POST", url, 400, files={"file": ("bill.exe", b"MZ", "application/octet-stream")})


def test_stock_adjustment_and_reconcile(admin, products):
    onion = products["Onion"]["id"]
    before = stock(admin, onion)
    admin.post("/api/stock/adjust", {"product_id": onion, "movement_type": "WASTAGE", "direction": "REDUCE",
                                     "qty": 2}, expect=400)  # remarks required
    admin.post("/api/stock/adjust", {"product_id": onion, "movement_type": "WASTAGE", "direction": "REDUCE",
                                     "qty": 2, "remarks": "Rotten"})
    admin.post("/api/stock/adjust", {"product_id": onion, "movement_type": "WASTAGE", "direction": "ADD",
                                     "qty": 2, "remarks": "x"}, expect=400)
    assert stock(admin, onion) == pytest.approx(before - 2)
    res = admin.post("/api/stock/reconcile", {"counts": [{"product_id": onion, "physical_qty": 10}]})
    assert res[0]["difference"] == pytest.approx(10 - (before - 2))
    assert stock(admin, onion) == 10
    mv = admin.get(f"/api/stock/product/{onion}")["movements"]
    assert [m["movement_type"] for m in mv][:2] == ["RECONCILIATION", "WASTAGE"]
    for m in mv:
        assert m["closing_qty"] == pytest.approx(m["opening_qty"] + m["added_qty"] - m["reduced_qty"])
