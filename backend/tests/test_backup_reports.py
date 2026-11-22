import io
import zipfile
from datetime import date

import pytest

from conftest import ADMIN_PW, pay_exact

TODAY = date.today().isoformat()


def tea_bill(api, products, qty=1):
    return api.post("/api/bills", pay_exact(api, {"items": [{"product_id": products["Tea"]["id"], "qty": qty}]}))


def bill_count(api):
    return len(api.get("/api/bills"))


def test_backup_and_restore_round_trip(admin, products):
    first = tea_bill(admin, products)
    bk = admin.post("/api/backups")
    assert bk["kind"] == "manual"
    tea_bill(admin, products)
    assert bill_count(admin) == 2

    out = admin.post(f"/api/backups/{bk['name']}/restore")
    assert out["ok"] is True
    admin.login("admin", ADMIN_PW)
    assert bill_count(admin) == 1
    kinds = {b["kind"] for b in admin.get("/api/backups")["backups"]}
    assert {"manual", "pre-restore"} <= kinds

    # numbering and database ids continue correctly after a restore
    nxt = tea_bill(admin, products)
    assert nxt["bill_no"].endswith("/00002")
    assert nxt["id"] > first["id"]
    admin.post("/api/products", {"code": "NEW1", "name": "New Dish", "selling_price": 50})


def test_upload_restore_of_downloaded_backup(admin, products):
    tea_bill(admin, products)
    bk = admin.post("/api/backups")
    raw = admin.req("GET", f"/api/backups/{bk['name']}/download").content
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert "data.json" in z.namelist()
    tea_bill(admin, products)
    admin.req("POST", "/api/backups/upload-restore", files={"file": ("backup.zip", raw, "application/zip")})
    admin.login("admin", ADMIN_PW)
    assert bill_count(admin) == 1


def test_invalid_backups_are_rejected(admin, products):
    tea_bill(admin, products)
    admin.req("POST", "/api/backups/upload-restore", 400, files={"file": ("x.zip", b"garbage", "application/zip")})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("data.json", '{"format": 1, "tables": {"users": []}}')
    admin.req("POST", "/api/backups/upload-restore", 400, files={"file": ("x.zip", buf.getvalue(), "application/zip")})
    assert bill_count(admin) == 1  # nothing was changed
    admin.post("/api/backups/not-a-backup.zip/restore", expect=400)
    admin.req("GET", "/api/backups/madhurima_manual_20000101_000000.zip/download", 404)


def test_backup_delete(admin):
    bk = admin.post("/api/backups")
    admin.req("DELETE", f"/api/backups/{bk['name']}")
    assert admin.get("/api/backups")["backups"] == []


@pytest.fixture
def busy_day(admin, products):
    """A day with sales (cash, UPI, B2B, inter-state, cancelled), a credit note, a purchase, a debit note,
    an expense and a stock adjustment, so every report has rows to work on."""
    tea_bill(admin, products, qty=3)
    b = admin.post("/api/bills", pay_exact(admin, {"items": [{"product_id": products["Chicken Biriyani"]["id"],
                                                              "qty": 2}], "customer_gstin": "29AAACB1234C1Z1",
                                                   "customer_name": "Bangalore Co"}))
    big = pay_exact(admin, {"items": [{"product_id": products["Mutton Biriyani"]["id"], "qty": 1000}],
                            "customer_state_code": "33"})
    admin.post("/api/bills", {**big, "cash_amount": 0, "upi_amount": big["cash_amount"], "upi_ref": "UTR9"})
    c = tea_bill(admin, products)
    admin.post(f"/api/bills/{c['id']}/cancel", {"reason": "Wrong order"})
    admin.post("/api/credit-notes", {"bill_id": b["id"], "reason": "Returned",
                                     "items": [{"bill_item_id": b["items"][0]["id"], "qty": 1}]})
    sup = admin.post("/api/suppliers", {"name": "Fresh Farms", "gstin": "32AAACF1111A1Z1"})
    pur = admin.post("/api/purchases", {"supplier_id": sup["id"], "supplier_invoice_no": "FF-1", "invoice_date": TODAY,
                                        "items": [{"product_id": products["Basmati Rice"]["id"], "qty": 10,
                                                   "rate": 105, "gst_rate": 5}], "paid_cash": 500})
    admin.post(f"/api/purchases/{pur['id']}/return", {"items": [{"purchase_item_id": pur["items"][0]["id"],
                                                                 "qty": 1}], "reason": "Damaged"})
    admin.post("/api/expenses", {"expense_date": TODAY, "category": "Gas / Fuel", "amount": 250, "mode": "CASH"})
    admin.post("/api/stock/adjust", {"product_id": products["Onion"]["id"], "movement_type": "WASTAGE",
                                     "direction": "REDUCE", "qty": 1, "remarks": "Rotten"})
    return admin


def test_every_report_runs_in_every_format(busy_day):
    reports = busy_day.get("/api/reports")
    assert len(reports) >= 40
    for rep in reports:
        out = busy_day.get(f"/api/reports/{rep['name']}")
        assert {"title", "columns", "rows", "totals"} <= set(out), rep["name"]
        for fmt, magic in (("xlsx", b"PK"), ("pdf", b"%PDF")):
            r = busy_day.req("GET", f"/api/reports/{rep['name']}?format={fmt}")
            assert r.content.startswith(magic), (rep["name"], fmt)
    busy_day.get("/api/reports/no_such_report", expect=404)
    busy_day.get("/api/reports/hsn_summary?format=doc", expect=400)


def test_gst_reports_agree_with_bills(busy_day):
    bills = [b for b in busy_day.get("/api/bills") if b["status"] == "ACTIVE"]
    notes = busy_day.get("/api/notes?note_type=CREDIT")
    expected_tax = round(sum(b["total_tax"] for b in bills) - sum(n["cgst"] + n["sgst"] + n["igst"] for n in notes), 2)
    out = busy_day.get("/api/reports/output_gst_summary")
    t = out["totals"]
    tax = round(sum(t.get(k, 0) for k in ("cgst", "sgst", "igst")), 2)
    assert tax == pytest.approx(expected_tax, abs=0.02)


def test_b2cl_lists_large_inter_state_b2c_invoice(busy_day):
    rows = busy_day.get("/api/reports/b2cl_sales")["rows"]
    assert len(rows) == 1


def test_dashboard_loads(busy_day):
    d = busy_day.get("/api/dashboard")
    assert d["cards"]
    busy_day.get(f"/api/dashboard?from_date={TODAY[:8]}01&to_date={TODAY}")
