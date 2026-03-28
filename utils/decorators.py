"""Request decorators for rate limiting and authentication"""
from functools import wraps
from flask import request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)


def telegram_user_required(f):
    """
    Legacy decorator - redirects to new telegram_auth_required.
    Kept for backward compatibility.
    """
    from utils.telegram_auth import telegram_auth_required
    return telegram_auth_required(f)
