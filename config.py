"""Application configuration"""
import os
from dotenv import load_dotenv

# Load .env file only in local development
if not os.getenv("RAILWAY_ENVIRONMENT"):
    load_dotenv()


class Config:
    """Main configuration class"""



    # ----- ENVIRONMENT -----
    ENV = os.getenv("FLASK_ENV", "production")
    DEBUG = ENV == "development"
    TESTING = os.getenv("TESTING", "false").lower() == "true"
    
    # ----- CORE SECURITY -----
    SECRET_KEY = os.getenv("SECRET_KEY", "")
    if not SECRET_KEY:
        # Generate a random key if not set (not recommended for production)
        import secrets
        SECRET_KEY = secrets.token_hex(32)
        print("⚠️ WARNING: SECRET_KEY not set, using random key (sessions won't persist)")
    
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    if not BOT_TOKEN:
        print("❌ ERROR: BOT_TOKEN is required")
       
BOT_USERNAME = os.getenv("BOT_USERNAME", "")
if not BOT_USERNAME:
    print("⚠️ WARNING: BOT_USERNAME not set (needed for 'Start Bot' button)") 
    
    # ----- ADMIN CONFIGURATION -----
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
    if not ADMIN_PASSWORD:
        print("⚠️ WARNING: ADMIN_PASSWORD not set")
    
    # Admin Telegram IDs (comma-separated in .env)
    _admin_ids_str = os.getenv("ADMIN_TELEGRAM_IDS", "")
    ADMIN_TELEGRAM_IDS = []
    if _admin_ids_str:
        try:
            ADMIN_TELEGRAM_IDS = [int(id.strip()) for id in _admin_ids_str.split(",") if id.strip()]
        except ValueError:
            print("⚠️ WARNING: Invalid ADMIN_TELEGRAM_IDS format")
    
    # ----- SESSION SECURITY -----
    SESSION_COOKIE_SECURE = ENV == "production"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour
    
    # ----- CSRF PROTECTION -----
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600
    
    # ----- FILE UPLOADS -----
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS = {
        "png", "jpg", "jpeg", "gif", "svg", "webp",
        "webm", "zip", "rar", "psd", "ai", "fig", 
        "mp4", "pdf", "mp3", "wav"
    }
    
    # ----- DATABASE -----
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///shop.db")
    
    # Fix Heroku/Railway postgres:// URLs
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    # Use psycopg3 for PostgreSQL
    if DATABASE_URL.startswith("postgresql://"):
        SQLALCHEMY_DATABASE_URI = DATABASE_URL.replace(
            "postgresql://", "postgresql+psycopg://", 1
        )
    else:
        SQLALCHEMY_DATABASE_URI = DATABASE_URL
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
    
    # ----- CLOUDFLARE R2 STORAGE -----
    R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "")
    R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY", "")
    R2_SECRET_KEY = os.getenv("R2_SECRET_KEY", "")
    R2_BUCKET = os.getenv("R2_BUCKET", "")
    R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "")
    
    # ----- APP URL -----
    APP_URL = os.getenv("APP_URL", "https://web-production-36eec.up.railway.app")
    
    # ----- RATE LIMITING -----
    RATELIMIT_STORAGE_URL = "memory://"
    RATELIMIT_DEFAULT = "200 per day"
    RATELIMIT_HEADERS_ENABLED = True
