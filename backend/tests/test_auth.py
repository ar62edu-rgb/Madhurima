from conftest import ADMIN_PW, make_user


def test_first_run_setup_then_locked(api):
    assert api.get("/api/auth/status") == {"needs_setup": True}
    out = api.post("/api/auth/setup", {"restaurant_name": "Madhurima", "username": "Admin", "password": ADMIN_PW})
    assert out["user"]["username"] == "admin"
    assert "password_hash" not in out["user"]
    assert api.get("/api/auth/status") == {"needs_setup": False}
    api.post("/api/auth/setup", {"restaurant_name": "Again", "username": "evil", "password": "whatever"}, expect=400)


def test_login_and_wrong_password(admin):
    admin.login("admin", ADMIN_PW)
    assert admin.get("/api/auth/me")["role"] == "admin"
    admin.login("admin", "wrong-password", expect=401)


def test_account_locks_after_five_failures(admin):
    for _ in range(5):
        admin.login("admin", "wrong-password", expect=401)
    admin.login("admin", ADMIN_PW, expect=423)


def test_requests_without_token_are_rejected(api):
    api.get("/api/products", expect=401)
    api.token = "not-a-jwt"
    api.get("/api/products", expect=401)


def test_cashier_cannot_use_admin_endpoints(admin):
    cashier = make_user(admin, "cashier1")
    cashier.get("/api/products")
    cashier.put("/api/settings", {"address": "x"}, expect=403)
    cashier.get("/api/users", expect=403)
    cashier.get("/api/backups", expect=403)


def test_password_change_invalidates_old_token(admin):
    old = admin.token
    new = admin.post("/api/auth/change-password", {"current_password": ADMIN_PW, "new_password": "new-pass-123"})
    admin.token = old
    admin.get("/api/auth/me", expect=401)
    admin.token = new["token"]
    admin.get("/api/auth/me")


def test_settings_gstin_sets_state_code(admin):
    s = admin.put("/api/settings", {"gstin": "29abcde1234f1z5"})
    assert s["gstin"] == "29ABCDE1234F1Z5"
    assert s["state_code"] == "29"
    admin.put("/api/settings", {"gstin": "123"}, expect=400)
    admin.put("/api/settings", {"no_such_setting": "1"}, expect=400)
