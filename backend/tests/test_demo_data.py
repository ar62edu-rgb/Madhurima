"""The demo-data script must keep working as the app changes, and must refuse a database that has users."""
import pytest

import demo_data
from app.db import SessionLocal


def test_demo_data_fills_fresh_database(api):
    with SessionLocal() as db:
        pw_admin, pw_cashier, stats = demo_data.run(db, days=9, open_days=2)
    assert stats["bills"] > 50 and stats["closed_days"] == 7
    assert stats["purchases"] and stats["debit_notes"] == 1 and stats["expenses"]
    api.login("admin", pw_admin)
    api.login("cashier1", pw_cashier)
    api.login("admin", pw_admin)
    assert len(api.get("/api/daily-closings")) == 7
    for name in ("gstr3b_summary", "b2b_sales", "hsn_summary", "stock_summary"):
        api.get(f"/api/reports/{name}")

    with SessionLocal() as db, pytest.raises(SystemExit):
        demo_data.run(db)


def test_demo_data_uses_existing_admin_before_any_transactions(admin):
    """The first-time setup screen was already used (admin + sample menu): build on that admin."""
    with SessionLocal() as db:
        pw_admin, pw_cashier, stats = demo_data.run(db, days=5, open_days=1, admin_username="admin")
    assert pw_admin is None
    assert stats["bills"] > 20
    admin.get("/api/auth/me")  # the existing admin's login still works
    with SessionLocal() as db, pytest.raises(SystemExit):
        demo_data.run(db, admin_username="admin")  # now it has transactions


def test_demo_data_refuses_unknown_admin(admin):
    with SessionLocal() as db, pytest.raises(SystemExit):
        demo_data.run(db, admin_username="nobody")
