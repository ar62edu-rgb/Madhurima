"""Madhurima Family Restaurant — Billing, GST, Inventory & Finance. One local server serves API + web UI."""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .config import BACKUP_DIR, FRONTEND_DIST
from .db import Base, SessionLocal, engine
from .routers import auth, backup, billing, dashboard, finance, masters, purchases, reports_api, stock

log = logging.getLogger("madhurima")


async def auto_backup_loop():
    """Takes one automatic backup per day while the server is running."""
    while True:
        try:
            today = f"madhurima_auto_{date.today():%Y%m%d}_"
            if not any(p.name.startswith(today) for p in BACKUP_DIR.glob("madhurima_auto_*.zip")):
                with SessionLocal() as db:
                    if db.scalar(text("SELECT COUNT(*) FROM users")):
                        name = backup.create_backup(db, "auto")
                        log.info("Automatic backup created: %s", name)
        except Exception as e:  # never crash the server because of backup
            log.warning("Automatic backup failed: %s", e)
        await asyncio.sleep(1800)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    task = asyncio.create_task(auto_backup_loop())
    yield
    task.cancel()


app = FastAPI(title="Madhurima Family Restaurant API", version="1.0.0", lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    msgs = []
    for e in exc.errors():
        loc = ".".join(str(x) for x in e.get("loc", []) if x not in ("body", "query"))
        msgs.append(f"{loc}: {e.get('msg')}" if loc else e.get("msg"))
    return JSONResponse(status_code=422, content={"detail": "; ".join(msgs)})


for r in (auth.router, auth.users_router, masters.router, billing.router, purchases.router, stock.router,
          finance.router, reports_api.router, dashboard.router, backup.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---------- web UI (React build) ----------
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        candidate = (FRONTEND_DIST / full_path).resolve()
        if full_path and candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
