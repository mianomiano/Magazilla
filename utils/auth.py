"""Admin authentication utilities"""
import hmac
from functools import wraps
from flask import session, redirect, url_for, request
from werkzeug.security import check_password_hash
from config import Config


def verify_admin_password(password: str) -> bool:
    """Securely verify admin password"""
    if not Config.ADMIN_PASSWORD:
        return False
    
    if Config.ADMIN_PASSWORD.startswith('pbkdf2:sha256:'):
        return check_password_hash(Config.ADMIN_PASSWORD, password)
    
    return hmac.compare_digest(password, Config.ADMIN_PASSWORD)


def admin_required(f):
    """Decorator to protect admin routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('admin_bp.login'))
        return f(*args, **kwargs)
    return decorated_function


def log_admin_action(action: str, details: str = None):
    """Log admin action to audit trail"""
    from models import db, AdminAuditLog
    
    log = AdminAuditLog(
        admin_user_id=session.get('admin_user_id'),
        action=action,
        details=details,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent', '')[:500]
    )
    db.session.add(log)
    try:
        db.session.commit()
    except Exception as e:
        print(f"Failed to log admin action: {e}")
        db.session.rollback()
