import os

class Config:
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', 'magazilla-secret-key-change-in-prod')
    
    # Database (Railway provides DATABASE_URL)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///magazilla.db')
    # Railway uses postgres:// but SQLAlchemy needs postgresql://
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Telegram
    BOT_TOKEN = os.environ.get('BOT_TOKEN', '8291332731:AAGO4WCsshqXWiMymXm_bdbuXTAr2xHVE10')
    BOT_USERNAME = os.environ.get('BOT_USERNAME', 'mispicbot')
    ADMIN_TELEGRAM_IDS = [int(x) for x in os.environ.get('ADMIN_TELEGRAM_IDS', '7165489081').split(',')]
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '18273645')
    
    # App URL
    APP_URL = os.environ.get('APP_URL', 'https://magazilla-production.up.railway.app')
    WEBHOOK_URL = f"{APP_URL}/webhook/{BOT_TOKEN}"
    
    # Cloudflare R2
    R2_ACCOUNT_ID = os.environ.get('R2_ACCOUNT_ID', '99838ce7ba26e1ac7c9f89236e9966e0')
    R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY', '3f2c84439cde113381b200f5c887969d')
    R2_SECRET_KEY = os.environ.get('R2_SECRET_KEY', 'bf91cddf54bf59c07468e10e641f1f56b446c60c133ad12441c642b159d5e54d')
    R2_BUCKET = os.environ.get('R2_BUCKET', 'magazilla-files')
    R2_PUBLIC_URL = os.environ.get('R2_PUBLIC_URL', f'https://pub-{R2_ACCOUNT_ID}.r2.dev')
    
    # CSRF
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600
    
    # Upload
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max
    ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'webm'}
