import os  # Add this if not already there
from flask import Flask, render_template
from flask_wtf.csrf import CSRFProtect
from config import Config
from models import db, AppSettings
from utils.decorators import limiter
from r2_storage import get_r2_url
import sqlalchemy as sa

# Import blueprints
from blueprints.admin import admin_bp
from blueprints.api import api_bp
from blueprints.public import public_bp


def migrate_database():
    """Add missing columns to existing database"""
    print("🔄 Checking database schema...")
    
    temp_app = Flask(__name__)
    temp_app.config.from_object(Config)
    db.init_app(temp_app)
    
    with temp_app.app_context():
        try:
            # Get database inspector
            inspector = sa.inspect(db.engine)
            
            # Check Purchase table columns
            if inspector.has_table('purchase'):
                columns = {col['name'] for col in inspector.get_columns('purchase')}
                
                # Add is_verified if missing
                if 'is_verified' not in columns:
                    print("  ➕ Adding is_verified column...")
                    with db.engine.begin() as conn:
                        conn.execute(sa.text(
                            'ALTER TABLE purchase ADD COLUMN is_verified BOOLEAN DEFAULT TRUE'
                        ))
                        # Set existing purchases as verified
                        conn.execute(sa.text(
                            'UPDATE purchase SET is_verified = TRUE WHERE is_verified IS NULL'
                        ))
                
                # Add is_test if missing
                if 'is_test' not in columns:
                    print("  ➕ Adding is_test column...")
                    with db.engine.begin() as conn:
                        conn.execute(sa.text(
                            'ALTER TABLE purchase ADD COLUMN is_test BOOLEAN DEFAULT FALSE'
                        ))
            
            # Check AdminAuditLog table exists
            if not inspector.has_table('admin_audit_log'):
                print("  ➕ Creating admin_audit_log table...")
                db.create_all()
            
            print("✅ Database schema up to date")
        
        except Exception as e:
            print(f"⚠️ Migration warning: {e}")
def migrate_database():
    """Migrate database to add missing columns"""
    from flask import Flask
    from models import db
    import sqlalchemy as sa
    
    temp_app = Flask(__name__)
    temp_app.config.from_object(Config)
    db.init_app(temp_app)
    
    with temp_app.app_context():
        inspector = sa.inspect(db.engine)
        
        # Check if Purchase table has new columns
        columns = [col['name'] for col in inspector.get_columns('purchase')]
        
        if 'is_verified' not in columns:
            print("🔄 Adding is_verified column...")
            db.engine.execute(sa.text(
                'ALTER TABLE purchase ADD COLUMN is_verified BOOLEAN DEFAULT FALSE'
            ))
        
        if 'is_test' not in columns:
            print("🔄 Adding is_test column...")
            db.engine.execute(sa.text(
                'ALTER TABLE purchase ADD COLUMN is_test BOOLEAN DEFAULT FALSE'
            ))
        
        print("✅ Database migration complete")

# Run migration
migrate_database()

app = create_app()


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
    
    # Create/migrate tables
    with app.app_context():
        db.create_all()
    
    # Health check
    @app.route('/health')
    def health():
        return 'ok'
    
    return app


# Run migration first
migrate_database()

# Then create app
app = create_app()


if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        debug=Config.DEBUG
    )
