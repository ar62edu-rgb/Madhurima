"""Test setup. Every test gets a brand-new empty database and empty data folders.

Database: TEST_DATABASE_URL if set (must point at a throwaway database whose name contains "test"),
otherwise a temporary SQLite file. The live install is never touched: DATA_DIR / BACKUP_DIR point at a
temp folder and DATABASE_URL is overwritten before the app is imported."""
import os
import shutil
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="madhurima_test_"))
_url = os.getenv("TEST_DATABASE_URL", "").strip()
if _url:
    db_name = _url.rsplit("/", 1)[-1].split("?")[0]
    if "test" not in db_name.lower():
        raise RuntimeError(f"TEST_DATABASE_URL must point at a throwaway database with 'test' in its name, got {db_name!r}")
else:
    _url = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["DATABASE_URL"] = _url
os.environ["DATA_DIR"] = str(_TMP / "data")
os.environ["BACKUP_DIR"] = str(_TMP / "data" / "backups")
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["FRONTEND_DIST"] = str(_TMP / "no-frontend")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

ADMIN_PW = "admin-test-pw"


def pytest_report_header():
    return f"database: {engine.url.render_as_string(hide_password=True)}"


def _reset():
    engine.dispose()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    for d in (config.BACKUP_DIR, config.ATTACH_DIR):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)


class Api:
    """Thin wrapper around TestClient that adds the bearer token and checks status codes."""

    def __init__(self, client: TestClient):
        self.client = client
        self.token = None

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def req(self, method, path, expect=200, **kw):
        r = self.client.request(method, path, headers=self._headers(), **kw)
        assert r.status_code == expect, f"{method} {path} -> {r.status_code}: {r.text}"
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else r

    def get(self, path, expect=200, **kw):
        return self.req("GET", path, expect, **kw)

    def post(self, path, body=None, expect=200, **kw):
        return self.req("POST", path, expect, json=body, **kw)

    def put(self, path, body=None, expect=200, **kw):
        return self.req("PUT", path, expect, json=body, **kw)

    def login(self, username, password, expect=200):
        self.token = None
        out = self.post("/api/auth/login", {"username": username, "password": password}, expect=expect)
        if expect == 200:
            self.token = out["token"]
        return out


@pytest.fixture
def api():
    _reset()
    with TestClient(app) as c:
        yield Api(c)
    engine.dispose()


@pytest.fixture
def admin(api):
    """Logged-in admin on a fresh install with the sample menu loaded."""
    out = api.post("/api/auth/setup", {"restaurant_name": "Madhurima Test", "username": "admin",
                                       "password": ADMIN_PW, "load_sample_data": True})
    api.token = out["token"]
    api.put("/api/settings", {"gstin": "32ABCDE1234F1Z5", "address": "MG Road, Kochi"})
    return api


@pytest.fixture
def products(admin):
    return {p["name"]: p for p in admin.get("/api/products")}


def make_user(api, username, role="cashier", password="user-test-pw", **perms):
    body = {"username": username, "password": password, "role": role, **perms}
    api.post("/api/users", body)
    other = Api(api.client)
    other.login(username, password)
    return other


def pay_exact(api, body):
    """Preview a bill and fill in an all-cash payment for the exact amount."""
    total = api.post("/api/bills/preview", body)["totals"]["grand_total"]
    return {**body, "cash_amount": total}


def pytest_sessionfinish(session, exitstatus):
    engine.dispose()
    shutil.rmtree(_TMP, ignore_errors=True)
