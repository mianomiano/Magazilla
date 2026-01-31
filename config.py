import os
from dotenv import load_dotenv

# Load .env ONLY for local development
if not os.getenv("RAILWAY_ENVIRONMENT"):
    load_dotenv()
    print("✅ Loaded .env file for local development")


class Config:
    # ---------- Environment (define this FIRST) ----------
    ENV = os.getenv("FLASK_ENV", "development")
    DEBUG = ENV == "development"
    TESTING = os.getenv("TESTING", "false").lower() == "true"
    
    # ---------- Core ----------
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set in .env file")

    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # ---------- Security ----------
    SESSION_COOKIE_SECURE = ENV == "production"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
    
    # ---------- Admin Authentication ----------
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
    ADMIN_TELEGRAM_IDS = [7165489081]  # Your Telegram ID
    
    # ---------- App URL ----------
    APP_URL = os.getenv("APP_URL", "http://localhost:5000")

    # ---------- Database ----------
    DATABASE_URL = os.getenv("DATABASE_URL")
    
    # Allow SQLite for local development
    if not DATABASE_URL:
        if ENV == "development":
            DATABASE_URL = "sqlite:///app.db"
            print("⚠️ Using SQLite for local development")
        else:
            raise RuntimeError("DATABASE_URL is not set")
    
    # Handle postgres:// vs postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    # Use psycopg driver for PostgreSQL only
    if DATABASE_URL.startswith("postgresql://"):
        SQLALCHEMY_DATABASE_URI = DATABASE_URL.replace(
            "postgresql://", "postgresql+psycopg://", 1
        )
    else:
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

    if not all([R2_ACCOUNT_ID, R2_ACCESS_KEY, R2_SECRET_KEY, R2_BUCKET]):
        print("⚠️ Warning: R2 credentials not set - uploads disabled")
    
    # ---------- Rate Limiting ----------
    RATELIMIT_STORAGE_URL = "memory://"
