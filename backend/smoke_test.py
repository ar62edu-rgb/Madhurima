"""End-to-end API smoke test against a running server (SMOKE_URL, default http://localhost:8000)."""
import json, os, sys, urllib.request, urllib.error
BASE = os.getenv("SMOKE_URL", "http://localhost:8000")
TOKEN = None
def call(method, path, body=None, raw=False):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Content-Type", "application/json")
    if TOKEN: req.add_header("Authorization", "Bearer " + TOKEN)
    try:
        with urllib.request.urlopen(req) as r:
            data = r.read()
            return data if raw else json.loads(data)
    except urllib.error.HTTPError as e:
        print("FAIL", method, path, e.code, e.read().decode()); sys.exit(1)
st = call("GET", "/api/auth/status")
if st["needs_setup"]:
    TOKEN = call("POST", "/api/auth/setup", {"restaurant_name": "Madhurima Family Restaurant", "username": "admin",
                                            "password": os.getenv("SMOKE_PW", "smoke-test-pw"), "load_sample_data": True})["token"]
else:
    TOKEN = call("POST", "/api/auth/login", {"username": "admin", "password": os.getenv("SMOKE_PW", "smoke-test-pw")})["token"]
call("PUT", "/api/settings", {"gstin": "32ABCDE1234F1Z5", "fssai": "11322000000000", "address": "MG Road, Kochi"})
prods = call("GET", "/api/products?pos=true")
bir = next(p for p in prods if p["name"] == "Chicken Biriyani")
tea = next(p for p in prods if p["name"] == "Tea")
body = {"items": [{"product_id": bir["id"], "qty": 2}, {"product_id": tea["id"], "qty": 3, "discount": 5}], "bill_discount": 10}
pv = call("POST", "/api/bills/preview", body)
t = pv["totals"]; print("preview", t)
body.update(cash_amount=t["grand_total"] - 100, upi_amount=100, upi_ref="UPI123", cash_tendered=t["grand_total"])
bill = call("POST", "/api/bills", body); print("bill", bill["bill_no"], bill["grand_total"], bill["payment_mode"])
sup = call("POST", "/api/suppliers", {"name": "Fresh Farms", "gstin": "32AAACF1111A1Z1"})
rice = next(p for p in call("GET", "/api/products?q=basmati"))
pur = call("POST", "/api/purchases", {"supplier_id": sup["id"], "supplier_invoice_no": "FF-1", "invoice_date": bill["bill_date"][:10],
      "items": [{"product_id": rice["id"], "qty": 10, "rate": 105, "gst_rate": 5}], "paid_cash": 500})
print("purchase", pur["purchase_no"], pur["grand_total"], pur["payment_status"])
call("POST", "/api/expenses", {"expense_date": bill["bill_date"][:10], "category": "Gas / Fuel", "amount": 250, "mode": "CASH"})
cn = call("POST", "/api/credit-notes", {"bill_id": bill["id"], "items": [{"bill_item_id": bill["items"][1]["id"], "qty": 1}], "reason": "Spilled tea"})
print("credit note", cn["note_no"], cn["total"])
dn = call("POST", f"/api/purchases/{pur['id']}/return", {"items": [{"purchase_item_id": pur["items"][0]["id"], "qty": 1}], "reason": "Damaged bag"})
print("debit note", dn["note_no"], dn["total"])
b2 = call("POST", "/api/bills", {"items": [{"product_id": tea["id"], "qty": 1}], "cash_amount": 16 if False else call("POST", "/api/bills/preview", {"items": [{"product_id": tea["id"], "qty": 1}]})["totals"]["grand_total"]})
call("POST", f"/api/bills/{b2['id']}/cancel", {"reason": "Wrong order"})
held = call("POST", "/api/held-orders", {"table_id": 1, "items": [{"product_id": tea["id"], "name": "Tea", "qty": 2, "rate": 15}]})
kot = call("POST", f"/api/held-orders/{held['id']}/kot"); print("kot", kot["kot_no"], kot["kot_items"])
day = call("GET", "/api/daily-closing"); print("expected cash", day["expected_cash"], "cash sales", day["cash_sales"])
dash = call("GET", "/api/dashboard"); print("dashboard", dash["cards"])
for r in call("GET", "/api/reports"):
    rep = call("GET", f"/api/reports/{r['name']}")
    assert "rows" in rep
for fmt in ("xlsx", "pdf"):
    data = call("GET", f"/api/reports/hsn_summary?format={fmt}", raw=True); print(fmt, len(data), "bytes")
bk = call("POST", "/api/backups"); print("backup", bk["name"])
call("POST", f"/api/backups/{bk['name']}/restore")
TOKEN = call("POST", "/api/auth/login", {"username": "admin", "password": os.getenv("SMOKE_PW", "smoke-test-pw")})["token"]
print("bills after restore", len(call("GET", "/api/bills")))
mv = call("GET", "/api/stock/movements"); print("movements", len(mv))
print("ALL OK")
