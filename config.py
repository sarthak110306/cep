import os
from pathlib import Path
from urllib.parse import urlparse, unquote

from dotenv import load_dotenv

# Always load .env from the project folder
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production")

    # Supabase API credentials
    SUPABASE_URL = os.getenv("SUPABASE_URL", "https://pfphsnbguxoybnmnogcx.supabase.co")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_jY1aBwwwf6SkDKq-Jxet7A_YHm4-PV9")

    # Database connection URL (defaults to Supabase PostgreSQL)
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:sarthak%402026V@db.pfphsnbguxoybnmnogcx.supabase.co:5432/postgres"
    )

    if DATABASE_URL:
        _parsed = urlparse(DATABASE_URL)
        _engine = "postgres" if "postgres" in (_parsed.scheme or "") else "mysql"
        _host = _parsed.hostname or "db.pfphsnbguxoybnmnogcx.supabase.co"
        _port = _parsed.port or (5432 if _engine == "postgres" else 3306)
        _user = unquote(_parsed.username) if _parsed.username else "postgres"
        _password = unquote(_parsed.password) if _parsed.password else "sarthak@2026V"
        _db = _parsed.path.lstrip("/") if _parsed.path else "postgres"
    else:
        _engine = os.getenv("DB_ENGINE", "postgres")
        _host = os.getenv("DB_HOST", "db.pfphsnbguxoybnmnogcx.supabase.co")
        _port = int(os.getenv("DB_PORT", "5432"))
        _user = os.getenv("DB_USER", "postgres")
        _password = os.getenv("DB_PASSWORD", "sarthak@2026V")
        _db = os.getenv("DB_NAME", "postgres")

    DB_ENGINE = os.getenv("DB_ENGINE", _engine).lower()
    IS_POSTGRES = DB_ENGINE in ("postgres", "postgresql") or ("postgres" in DATABASE_URL)
    # Individual env vars take priority over DATABASE_URL parsed values
    DB_HOST = os.getenv("DB_HOST") or _host
    DB_PORT = int(os.getenv("DB_PORT") or _port)
    DB_USER = os.getenv("DB_USER") or _user
    DB_PASSWORD = os.getenv("DB_PASSWORD") or _password
    DB_NAME = os.getenv("DB_NAME") or _db
    DB_SSL_MODE = os.getenv("DB_SSL_MODE", "require" if IS_POSTGRES else "prefer")

    # Mail configuration
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")

    # Render & keep-alive configuration
    RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("APP_URL")
    KEEP_ALIVE_INTERVAL_MINUTES = int(os.getenv("KEEP_ALIVE_INTERVAL_MINUTES", "10"))

    # Session cookie security (true in production over HTTPS)
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").strip().lower() in ("1", "true", "yes")
