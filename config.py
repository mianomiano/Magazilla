import os
from dotenv import load_dotenv

# Load .env ONLY for local development
if not os.getenv("RAILWAY_ENVIRONMENT"):
    load_dotenv()


class Config:
    # ---------- Core ----------
    SECRET_KEY = os.getenv("SECRET_KEY")
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY is not set")

    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ---------- Database (PostgreSQL ONLY) ----------
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set. PostgreSQL is required. "
            "SQLite is not allowed on Railway."
        )

    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace(
            "postgres://", "postgresql://", 1
        )

    SQLALCHEMY_DATABASE_URI = DATABASE_URL

    # ---------- Upload rules ----------
    ALLOWED_EXTENSIONS = {
        "png", "jpg", "jpeg", "gif", "svg",
        "webm", "webp", "zip", "psd",
        "ai", "fig", "mp4", "pdf"
    }

    # ---------- Cloudflare R2 ----------
    R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
    R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY")
    R2_SECRET_KEY = os.getenv("R2_SECRET_KEY")
    R2_BUCKET = os.getenv("R2_BUCKET")
    R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "")

    if not all([
        R2_ACCOUNT_ID,
        R2_ACCESS_KEY,
        R2_SECRET_KEY,
        R2_BUCKET
    ]):
        raise RuntimeError("One or more R2 environment variables are missing")

