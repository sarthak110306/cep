import os
from pathlib import Path
from urllib.parse import urlparse, unquote

from dotenv import load_dotenv

# Always load .env from the project folder (works regardless of cwd)
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production")

    # Support connection via a full database URL (common on Render / cloud DBs)
    # Format: mysql://user:password@host:port/database
    _raw_db_url = os.getenv("DATABASE_URL") or os.getenv("MYSQL_URL")

    if _raw_db_url:
        _parsed = urlparse(_raw_db_url)
        _default_host = _parsed.hostname or "localhost"
        _default_port = _parsed.port or 3306
        _default_user = unquote(_parsed.username) if _parsed.username else "root"
        _default_password = unquote(_parsed.password) if _parsed.password else ""
        _default_db = _parsed.path.lstrip("/") if _parsed.path else "community_hackathon"
    else:
        _default_host = "localhost"
        _default_port = 3306
        _default_user = "root"
        _default_password = ""
        _default_db = "community_hackathon"

    DB_HOST = os.getenv("DB_HOST", _default_host)
    DB_PORT = int(os.getenv("DB_PORT", str(_default_port)))
    DB_USER = os.getenv("DB_USER", _default_user)
    DB_PASSWORD = os.getenv("DB_PASSWORD", _default_password)
    DB_NAME = os.getenv("DB_NAME", _default_db)

    # SSL configuration for cloud MySQL providers (TiDB, Aiven, PlanetScale, Railway, etc.)
    # Set DB_SSL_DISABLED=true if connecting to a local MySQL that has SSL disabled.
    # Set DB_SSL_VERIFY_CERT=false if cloud provider uses self-signed or internal CA.
    DB_SSL_DISABLED = os.getenv("DB_SSL_DISABLED", "false").strip().lower() in ("1", "true", "yes")
    DB_SSL_VERIFY_CERT = os.getenv("DB_SSL_VERIFY_CERT", "false").strip().lower() in ("1", "true", "yes")
    DB_SSL_CA = os.getenv("DB_SSL_CA", None)

    # Mail configuration
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")

    # Session cookie security: set to true in production over HTTPS (e.g. Render)
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").strip().lower() in ("1", "true", "yes")
