"""Custom decorators for Flask routes"""
from functools import wraps
from flask import request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)


def telegram_user_required(f):
    """Ensure request has valid Telegram user ID"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = request.args.get('user_id') or request.json.get('user_id')
        if not user_id:
            return jsonify({'error': 'user_id required'}), 400
        try:
            user_id = int(user_id)
        except ValueError:
            return jsonify({'error': 'Invalid user_id'}), 400
        return f(*args, **kwargs)
    return decorated_function
