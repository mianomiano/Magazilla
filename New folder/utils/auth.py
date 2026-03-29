"""Admin authentication utilities"""
import hmac
from functools import wraps
from flask import session, redirect, url_for, request, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from config import Config


def verify_admin_password(password: str) -> bool:
    """Securely verify admin password"""
    if not Config.ADMIN_PASSWORD:
        return False
    
    # Support hashed passwords (if password starts with hash prefix)
    if Config.ADMIN_PASSWORD.startswith('pbkdf2:sha256:'):
        return check_password_hash(Config.ADMIN_PASSWORD, password)
    
    # Plain text comparison (constant time to prevent timing attacks)
    return hmac.compare_digest(password, Config.ADMIN_PASSWORD)


def is_admin_telegram_user(user_id: int) -> bool:
    """Check if Telegram user ID is in admin list"""
    return user_id in Config.ADMIN_TELEGRAM_IDS


def admin_required(f):
    """Decorator to protect admin routes - session based"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('admin_bp.login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_api_required(f):
    """Decorator for admin API routes - validates Telegram initData + admin status"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from utils.telegram_auth import validate_telegram_init_data
        
        # First check session (for browser-based admin panel)
        if session.get('is_admin'):
            return f(*args, **kwargs)
        
        # Then check Telegram initData for API calls
        init_data = (
            request.headers.get('X-Telegram-Init-Data') or
            (request.json or {}).get('initData')
        )
        
        if init_data:
            user_data = validate_telegram_init_data(init_data, Config.BOT_TOKEN)
            if user_data and is_admin_telegram_user(user_data.get('id')):
                return f(*args, **kwargs)
        
        return jsonify({'error': 'Admin access required'}), 403
    
    return decorated_function


def log_admin_action(action: str, details: str = None):
    """
    Log admin action for audit trail.
    
    Args:
        action: The action performed (e.g., 'create_product', 'delete_product')
        details: Additional details about the action
    """
    try:
        from models import db, AdminAuditLog
        
        log_entry = AdminAuditLog(
            admin_user_id=session.get('admin_user_id'),
            action=action,
            details=details,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')[:500]
        )
        db.session.add(log_entry)
        db.session.commit()
        
    except Exception as e:
        # If logging fails, don't crash the app - just print error
        print(f"⚠️ Failed to log admin action: {e}")
        print(f"📝 Admin Action: {action} | Details: {details}")
