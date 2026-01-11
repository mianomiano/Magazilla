import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'change-me-123')
    DATABASE_URL = os.getenv('DATABASE_URL', '')
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_DATABASE_URI = DATABASE_URL or 'sqlite:///magazilla.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    BOT_TOKEN = os.getenv('BOT_TOKEN', '')
    ALLOWED_EXTENSIONS = {'png','jpg','jpeg','gif','svg','webm','webp','zip','psd','ai','fig','mp4','pdf'}
    
    # R2 Storage
    R2_ACCOUNT_ID = os.getenv('R2_ACCOUNT_ID', '99838ce7ba26e1ac7c9f89236e9966e0')
    R2_ACCESS_KEY = os.getenv('R2_ACCESS_KEY', '3f2c84439cde113381b200f5c887969d')
    R2_SECRET_KEY = os.getenv('R2_SECRET_KEY', 'bf91cddf54bf59c07468e10e641f1f56b446c60c133ad12449c642b159d5e54d')
    R2_BUCKET = os.getenv('R2_BUCKET', 'magazilla-files')
    R2_PUBLIC_URL = os.getenv('R2_PUBLIC_URL', '')  # Optional: custom domain
