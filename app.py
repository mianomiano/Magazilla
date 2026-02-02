from flask import Flask, render_template
from flask_wtf.csrf import CSRFProtect
from config import Config
from models import db, AppSettings
from utils.decorators import limiter
from r2_storage import get_r2_url
import os

# Import blueprints
from blueprints.admin import admin_bp
from blueprints.api import api_bp
from blueprints.public import public_bp


def migrate_database():
    """Add missing columns to existing database - with error handling"""
    print("🔄 Checking database schema...")
    
    temp_app = Flask(__name__)
    temp_app.config.from_object(Config)
    db.init_app(temp_app)
    
    with temp_app.app_context():
        try:
            # Just create all tables - SQLAlchemy will skip existing ones
            db.create_all()
            
            # Try to add missing columns using raw SQL
            try:
                with db.engine.begin() as conn:
                    # Add is_verified column if missing
                    try:
                        conn.execute(db.text(
                            "ALTER TABLE purchase ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT TRUE"
                        ))
                        print("  ✅ Added is_verified column")
                    except Exception as e:
                        print(f"  ℹ️ is_verified: {e}")
                    
                    # Add is_test column if missing
                    try:
                        conn.execute(db.text(
                            "ALTER TABLE purchase ADD COLUMN IF NOT EXISTS is_test BOOLEAN DEFAULT FALSE"
                        ))
                        print("  ✅ Added is_test column")
                    except Exception as e:
                        print(f"  ℹ️ is_test: {e}")
                    
                    # Set existing purchases as verified
                    try:
                        conn.execute(db.text(
                            "UPDATE purchase SET is_verified = TRUE WHERE is_verified IS NULL"
                        ))
                        print("  ✅ Updated existing purchases")
                    except Exception as e:
                        print(f"  ℹ️ update: {e}")
                
                print("✅ Database migration complete")
            
            except Exception as e:
                print(f"⚠️ Migration error (non-fatal): {e}")
                print("  Continuing with app startup...")
        
        except Exception as e:
            print(f"❌ Critical migration error: {e}")
            # Don't crash - let app continue
            print("  App will start anyway...")


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Initialize extensions
    db.init_app(app)
    csrf = CSRFProtect(app)
    limiter.init_app(app)
    
    # Exempt API webhook from CSRF
    csrf.exempt(api_bp)
    
    # Register blueprints
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(public_bp)
    
    # Template helper functions
    @app.context_processor
    def utility_processor():
        def r2_url(key, expires=3600):
            return get_r2_url(key, expires) if key else None
        
        def get_settings():
            s = AppSettings.query.first()
            if not s:
                s = AppSettings()
                db.session.add(s)
                db.session.commit()
            return s
        
        return dict(r2_url=r2_url, settings=get_settings())
    
    # Create tables
    with app.app_context():
        db.create_all()
    
    # Health check
    @app.route('/health')
    def health():
        return 'ok'
    
    return app


# Run
