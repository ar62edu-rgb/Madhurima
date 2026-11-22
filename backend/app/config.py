"""Runtime configuration. Everything comes from environment variables (see .env.example);
sensible defaults let the app also run directly on Windows with SQLite and no Docker."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/

DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", DATA_DIR / "backups"))
ATTACH_DIR = DATA_DIR / "attachments"
for _d in (DATA_DIR, BACKUP_DIR, ATTACH_DIR):
    _d.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{(DATA_DIR / 'restaurant.db').as_posix()}"
IS_SQLITE = DATABASE_URL.startswith("sqlite")

FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", BASE_DIR.parent / "frontend" / "dist"))

TOKEN_HOURS = int(os.getenv("TOKEN_HOURS", "14"))
AUTO_BACKUP_KEEP = int(os.getenv("AUTO_BACKUP_KEEP", "60"))
MAX_UPLOAD_MB = 10


def secret_key() -> str:
    """JWT signing key: env var, else a random key generated once and kept in the data folder."""
    env = os.getenv("SECRET_KEY")
    if env:
        return env
    f = DATA_DIR / "secret.key"
    if not f.exists():
        f.write_text(secrets.token_urlsafe(48))
    return f.read_text().strip()


SECRET_KEY = secret_key()
