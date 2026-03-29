#!/usr/bin/env python3
"""
Setup validation script for Telegram Shop template.
Run this to check if your configuration is correct.

Usage: python setup_check.py
"""
import os
import sys

def main():
    print("\n" + "=" * 55)
    print("🔍 TELEGRAM SHOP - SETUP CHECKER")
    print("=" * 55 + "\n")
    
    errors = []
    warnings = []
    
    # Check .env file exists
    if not os.path.exists('.env'):
        errors.append("❌ .env file not found")
        errors.append("   → Copy .env.example to .env and fill in your values")
        print_results(errors, warnings)
        return
    
    # Load environment
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        errors.append("❌ python-dotenv not installed")
        errors.append("   → Run: pip install python-dotenv")
    
    # Check required variables
    checks = [
        ('BOT_TOKEN', 'Telegram Bot Token', True, None),
        ('SECRET_KEY', 'Session Secret Key', True, 32),
        ('ADMIN_PASSWORD', 'Admin Password', True, 8),
        ('ADMIN_TELEGRAM_IDS', 'Admin Telegram IDs', False, None),
        ('APP_URL', 'Application URL', True, None),
    ]
    
    for var, name, required, min_length in checks:
        value = os.getenv(var, '')
        
        if not value:
            if required:
                errors.append(f"❌ {var} is not set")
                errors.append(f"   → {name} is required")
            else:
                warnings.append(f"⚠️ {var} is not set (optional)")
        elif min_length and len(value) < min_length:
            errors.append(f"❌ {var} is too short (min {min_length} chars)")
        elif var == 'BOT_TOKEN' and not value.count(':') == 1:
            errors.append(f"❌ {var} format looks invalid")
            errors.append("   → Should be like: 123456789:ABCdefGHIjklMNOpqrSTUvwxYZ")
        elif var == 'APP_URL' and not value.startswith('http'):
            errors.append(f"❌ {var} should start with http:// or https://")
    
    # Check R2 configuration
    r2_vars = ['R2_ACCOUNT_ID', 'R2_ACCESS_KEY', 'R2_SECRET_KEY', 'R2_BUCKET']
    missing_r2 = [v for v in r2_vars if not os.getenv(v)]
    if missing_r2:
        warnings.append("⚠️ Cloudflare R2 not fully configured")
        warnings.append(f"   → Missing: {', '.join(missing_r2)}")
        warnings.append("   → File uploads will not work without R2")
    
    # Check for common mistakes
    bot_token = os.getenv('BOT_TOKEN', '')
    if 'your_bot_token' in bot_token.lower() or bot_token == '':
        errors.append("❌ BOT_TOKEN contains placeholder value")
        errors.append("   → Replace with your actual bot token from @BotFather")
    
    secret_key = os.getenv('SECRET_KEY', '')
    if 'change_this' in secret_key.lower() or 'your_' in secret_key.lower():
        errors.append("❌ SECRET_KEY contains placeholder value")
        errors.append("   → Generate with: python -c \"import secrets; print(secrets.token_hex(32))\"")
    
    # Check Flask environment
    flask_env = os.getenv('FLASK_ENV', 'production')
    if flask_env == 'development':
        warnings.append("⚠️ FLASK_ENV is set to 'development'")
        warnings.append("   → Use 'production' for deployed apps")
    
    testing = os.getenv('TESTING', 'false').lower()
    if testing == 'true':
        warnings.append("⚠️ TESTING mode is enabled")
        warnings.append("   → Set TESTING=false for production")
    
    print_results(errors, warnings)


def print_results(errors, warnings):
    """Print the results summary"""
    print("-" * 55)
    
    if errors:
        print("\n🚫 ERRORS (must fix before deploying):\n")
        for e in errors:
            print(f"  {e}")
    
    if warnings:
        print("\n⚠️ WARNINGS (optional but recommended):\n")
        for w in warnings:
            print(f"  {w}")
    
    print("\n" + "-" * 55)
    
    if not errors and not warnings:
        print("\n✅ All checks passed! Your setup looks good.\n")
    elif not errors:
        print(f"\n✅ Required setup complete! ({len(warnings)} warnings)\n")
    else:
        print(f"\n❌ Please fix {len(errors)} error(s) before deploying.\n")
        sys.exit(1)
    
    print("=" * 55 + "\n")


if __name__ == '__main__':
    main()
