"""Backup & restore. A backup is a .zip holding data.json (every table) plus purchase attachments.
It is database-independent, so a backup taken on SQLite restores into PostgreSQL and vice versa."""
import io
import json
import re
import zipfile
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import Date, DateTime, select, text
from sqlalchemy.orm import Session

from ..config import ATTACH_DIR, AUTO_BACKUP_KEEP, BACKUP_DIR, IS_SQLITE
from ..db import Base, get_db
from ..models import User
from ..security import admin_only
from ..services import audit

router = APIRouter(prefix="/api/backups", tags=["backup"])
FORMAT_VERSION = 1
NAME_RE = re.compile(r"^madhurima_(auto|manual|pre-restore)_\d{8}_\d{6}\.zip$")


def create_backup(db: Session, kind: str = "manual") -> str:
    data = {"format": FORMAT_VERSION, "created_at": datetime.now().isoformat(), "tables": {}}
    for table in Base.metadata.sorted_tables:
        rows = db.execute(select(table)).mappings().all()
        data["tables"][table.name] = [{k: (v.isoformat() if isinstance(v, (date, datetime)) else v)
                                       for k, v in r.items()} for r in rows]
    name = f"madhurima_{kind}_{datetime.now():%Y%m%d_%H%M%S}.zip"
    path = BACKUP_DIR / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("data.json", json.dumps(data))
        for f in ATTACH_DIR.iterdir():
            if f.is_file():
                z.write(f, f"attachments/{f.name}")
    if kind == "auto":
        autos = sorted(BACKUP_DIR.glob("madhurima_auto_*.zip"))
        for old in autos[:-AUTO_BACKUP_KEEP]:
            old.unlink(missing_ok=True)
    return name


def restore_zip(db: Session, raw: bytes):
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        data = json.loads(z.read("data.json"))
    except Exception:
        raise HTTPException(400, "This is not a valid Madhurima backup file")
    if data.get("format") != FORMAT_VERSION or "tables" not in data:
        raise HTTPException(400, "Unsupported backup format")
    if not data["tables"].get("users"):
        raise HTTPException(400, "Backup has no users; refusing to restore")
    tables = Base.metadata.sorted_tables
    try:
        for table in reversed(tables):
            db.execute(table.delete())
        for table in tables:
            rows = data["tables"].get(table.name, [])
            conv = []
            for r in rows:
                row = {}
                for col in table.columns:
                    if col.name not in r:
                        continue
                    v = r[col.name]
                    if v is not None and isinstance(col.type, DateTime):
                        v = datetime.fromisoformat(v)
                    elif v is not None and isinstance(col.type, Date):
                        v = date.fromisoformat(v[:10])
                    row[col.name] = v
                conv.append(row)
            if "id" in table.columns:
                conv.sort(key=lambda x: x.get("id") or 0)  # parents (lower ids) first for self-references
            if conv:
                db.execute(table.insert(), conv)
        if not IS_SQLITE:
            for table in tables:
                if "id" in table.columns:
                    db.execute(text(f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), "
                                    f"COALESCE((SELECT MAX(id) FROM {table.name}), 0) + 1, false)"))
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(400, f"Restore failed, nothing was changed: {e}")
    for name in z.namelist():
        if name.startswith("attachments/") and not name.endswith("/"):
            fname = name.split("/", 1)[1]
            if "/" not in fname and ".." not in fname:
                (ATTACH_DIR / fname).write_bytes(z.read(name))


def _info(p):
    st = p.stat()
    return {"name": p.name, "size": st.st_size, "created_at": datetime.fromtimestamp(st.st_mtime).isoformat(),
            "kind": p.name.split("_")[1]}


@router.get("")
def list_backups(_: User = Depends(admin_only)):
    files = sorted(BACKUP_DIR.glob("madhurima_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    return {"folder": str(BACKUP_DIR), "backups": [_info(p) for p in files]}


@router.post("")
def backup_now(user: User = Depends(admin_only), db: Session = Depends(get_db)):
    name = create_backup(db, "manual")
    audit(db, user, "BACKUP", "backup", name)
    db.commit()
    return _info(BACKUP_DIR / name)


def _safe(name: str):
    if not NAME_RE.match(name):
        raise HTTPException(400, "Invalid backup name")
    p = BACKUP_DIR / name
    if not p.exists():
        raise HTTPException(404, "Backup not found")
    return p


@router.get("/{name}/download")
def download(name: str, _: User = Depends(admin_only)):
    return FileResponse(_safe(name), filename=name, media_type="application/zip")


@router.post("/{name}/restore")
def restore_existing(name: str, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    raw = _safe(name).read_bytes()
    create_backup(db, "pre-restore")
    restore_zip(db, raw)
    audit(db, user.username, "RESTORE", "backup", name)
    db.commit()
    return {"ok": True, "message": "Restored. Please log in again."}


@router.post("/upload-restore")
async def upload_restore(file: UploadFile = File(...), user: User = Depends(admin_only),
                         db: Session = Depends(get_db)):
    raw = await file.read(500 * 1024 * 1024)
    create_backup(db, "pre-restore")
    username = user.username
    restore_zip(db, raw)
    audit(db, username, "RESTORE_UPLOAD", "backup", file.filename or "")
    db.commit()
    return {"ok": True, "message": "Restored. Please log in again."}


@router.delete("/{name}")
def delete_backup(name: str, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    _safe(name).unlink()
    audit(db, user, "DELETE_BACKUP", "backup", name)
    db.commit()
    return {"ok": True}
