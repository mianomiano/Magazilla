import os
from flask import Flask, render_template
from flask_wtf.csrf import CSRFProtect
from config import Config
from models import db, AppSettings, BlogPost, BlogLike, VisitorLog
from utils.decorators import limiter
from r2_storage import get_r2_url

# Import blueprints
from blueprints.admin import admin_bp
from blueprints.api import api_bp
from blueprints.public import public_bp


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
    
    # Custom template filters
    @app.template_filter('nl2br')
    def nl2br_filter(text):
        """Convert newlines to <br> tags"""
        if not text:
            return ''
        return text.replace('\n', '<br>')
    
    # Create/migrate tables
    with app.app_context():
        # Run database migration
        migrate_database()
        # Create any missing tables
        db.create_all()
    
    # Health check
    @app.route('/health')
    def health():
        return 'ok'
    
    return app


def migrate_database():
    """Add missing columns to existing database"""
    import sqlalchemy as sa
    
    try:
        print("🔄 Checking database schema...")
        
        # Get database inspector
        inspector = sa.inspect(db.engine)
        
        # ===== PURCHASE TABLE =====
        if inspector.has_table('purchase'):
            columns = {col['name'] for col in inspector.get_columns('purchase')}
            
            # Add is_verified if missing
            if 'is_verified' not in columns:
                print("  ➕ Adding is_verified column...")
                with db.engine.begin() as conn:
                    conn.execute(sa.text(
                        'ALTER TABLE purchase ADD COLUMN is_verified BOOLEAN DEFAULT TRUE'
                    ))
                    conn.execute(sa.text(
                        'UPDATE purchase SET is_verified = TRUE WHERE is_verified IS NULL'
                    ))
                print("  ✅ is_verified column added")
            
            # Add is_test if missing
            if 'is_test' not in columns:
                print("  ➕ Adding is_test column...")
                with db.engine.begin() as conn:
                    conn.execute(sa.text(
                        'ALTER TABLE purchase ADD COLUMN is_test BOOLEAN DEFAULT FALSE'
                    ))
                print("  ✅ is_test column added")
        
        # ===== PRODUCT TABLE =====
        if inspector.has_table('product'):
            columns = {col['name'] for col in inspector.get_columns('product')}
            
            product_columns = {
                'tags': "VARCHAR(300) DEFAULT ''",
                'old_price': "INTEGER DEFAULT 0",
                'badge_text': "VARCHAR(15) DEFAULT ''",
                'badge_color': "VARCHAR(20) DEFAULT '#ff4444'",
                'is_featured': "BOOLEAN DEFAULT FALSE",
                'view_count': "INTEGER DEFAULT 0"
            }
            
            for col_name, col_type in product_columns.items():
                if col_name not in columns:
                    print(f"  ➕ Adding product.{col_name} column...")
                    with db.engine.begin() as conn:
                        conn.execute(sa.text(
                            f'ALTER TABLE product ADD COLUMN {col_name} {col_type}'
                        ))
                    print(f"  ✅ product.{col_name} column added")
        
        # ===== APP_SETTINGS TABLE =====
        if inspector.has_table('app_settings'):
            columns = {col['name'] for col in inspector.get_columns('app_settings')}
            
            # Appearance settings columns to add
            appearance_columns = {
                'font_family': "VARCHAR(50) DEFAULT 'inter'",
                'button_style': "VARCHAR(20) DEFAULT 'soft'",
                'button_roundness': "VARCHAR(20) DEFAULT 'rounded'",
                'card_size': "VARCHAR(20) DEFAULT 'medium'",
                'card_shape': "VARCHAR(20) DEFAULT 'square'",
                'card_info': "VARCHAR(20) DEFAULT 'full'",
                'header_size': "VARCHAR(20) DEFAULT 'normal'",
                'show_filters': "BOOLEAN DEFAULT TRUE",
                'layout_mode': "VARCHAR(20) DEFAULT 'grid'",
                'enable_blog': "BOOLEAN DEFAULT FALSE",
                'enable_product_messages': "BOOLEAN DEFAULT FALSE",
                'enable_contact_page': "BOOLEAN DEFAULT FALSE",
                'header_image_path': "VARCHAR(500) DEFAULT ''",
                'header_button_text': "VARCHAR(100) DEFAULT ''",
                'header_button_url': "VARCHAR(500) DEFAULT ''",
                'footer_text': "VARCHAR(500) DEFAULT 'Powered by GramaZilla'"
            }
            
            for col_name, col_type in appearance_columns.items():
                if col_name not in columns:
                    print(f"  ➕ Adding app_settings.{col_name} column...")
                    with db.engine.begin() as conn:
                        conn.execute(sa.text(
                            f'ALTER TABLE app_settings ADD COLUMN {col_name} {col_type}'
                        ))
                    print(f"  ✅ app_settings.{col_name} column added")
        
        # ===== ADMIN_AUDIT_LOG TABLE =====
        if not inspector.has_table('admin_audit_log'):
            print("  ➕ Creating admin_audit_log table...")
        
        # ===== BLOG_POST TABLE =====
        if not inspector.has_table('blog_post'):
            print("  ➕ Creating blog_post table...")
        
        # ===== BLOG_LIKE TABLE =====
        if not inspector.has_table('blog_like'):
            print("  ➕ Creating blog_like table...")
        
        # ===== VISITOR_LOG TABLE =====
        if not inspector.has_table('visitor_log'):
            print("  ➕ Creating visitor_log table...")
        
        print("✅ Database schema up to date")
    
    except Exception as e:
        print(f"⚠️ Migration warning: {e}")
        # Don't crash if migration fails


# Create the app instance
app = create_app()


if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        debug=Config.DEBUG
    )
