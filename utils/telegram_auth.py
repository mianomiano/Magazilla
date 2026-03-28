"""Telegram WebApp initData validation"""
import hmac
import hashlib
import json
import time
from urllib.parse import parse_qsl, unquote
from functools import wraps
from flask import request, jsonify
from config import Config


def validate_telegram_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400) -> dict:
    """
    Validate Telegram WebApp initData using HMAC-SHA256.
    Returns user data if valid, None if invalid.
    
    Args:
        init_data: The initData string from Telegram WebApp
        bot_token: Your bot token
        max_age_seconds: Maximum age of auth_date (default 24 hours)
    
    Returns:
        dict with user info if valid, None if invalid
    """
    try:
        # Parse the init data
        parsed_data = dict(parse_qsl(init_data, keep_blank_values=True))
        
        # Extract and remove hash
        received_hash = parsed_data.pop('hash', None)
        if not received_hash:
            return None
        
        # Check auth_date freshness (prevent replay attacks)
        auth_date = parsed_data.get('auth_date')
        if auth_date:
            try:
                auth_timestamp = int(auth_date)
                current_timestamp = int(time.time())
                if current_timestamp - auth_timestamp > max_age_seconds:
                    print(f"⚠️ initData expired: {current_timestamp - auth_timestamp}s old")
                    return None
            except ValueError:
                return None
        
        # Create the secret key: HMAC-SHA256 of bot token with "WebAppData"
        secret_key = hmac.new(
            key=b"WebAppData",
            msg=bot_token.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        
        # Create data-check-string: sort keys alphabetically, join with \n
        data_check_string = "\n".join(
            f"{key}={value}" 
            for key, value in sorted(parsed_data.items())
        )
        
        # Calculate expected hash
        calculated_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode('utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()
        
        # Constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(calculated_hash, received_hash):
            print("⚠️ initData hash mismatch")
            return None
        
        # Parse user data
        user_data = parsed_data.get('user')
        if user_data:
            try:
                return json.loads(unquote(user_data))
            except json.JSONDecodeError:
                return None
        
        return parsed_data
        
    except Exception as e:
        print(f"❌ initData validation error: {e}")
        return None


def telegram_auth_required(f):
    """
    Decorator that validates Telegram initData.
    Adds validated user info to request context.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get initData from header or body
        init_data = (
            request.headers.get('X-Telegram-Init-Data') or
            request.headers.get('Authorization', '').replace('tma ', '') or
            (request.json or {}).get('initData') or
            request.args.get('initData')
        )
        
        if not init_data:
            return jsonify({'error': 'Telegram authentication required'}), 401
        
        # Validate the initData
        user_data = validate_telegram_init_data(init_data, Config.BOT_TOKEN)
        
        if not user_data:
            return jsonify({'error': 'Invalid Telegram authentication'}), 401
        
        # Store validated user in request context
        request.telegram_user = user_data
        request.telegram_user_id = user_data.get('id')
        
        return f(*args, **kwargs)
    
    return decorated_function


def get_telegram_user_id() -> int:
    """Get the validated Telegram user ID from current request"""
    return getattr(request, 'telegram_user_id', None)


def get_telegram_user() -> dict:
    """Get the validated Telegram user data from current request"""
    return getattr(request, 'telegram_user', None)
