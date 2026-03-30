import os
from flask import Flask, render_template
from flask_wtf.csrf import CSRFProtect
from config import Config
from models import db, AppSettings
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
                'show_filters': "BOOLEAN DEFAULT TRUE"
            }
            
            for col_name, col_type in appearance_columns.items():
                if col_name not in columns:
                    print(f"  ➕ Adding {col_name} column...")
                    with db.engine.begin() as conn:
                        conn.execute(sa.text(
                            f'ALTER TABLE app_settings ADD COLUMN {col_name} {col_type}'
                        ))
                    print(f"  ✅ {col_name} column added")
        
        # ===== ADMIN_AUDIT_LOG TABLE =====
        if not inspector.has_table('admin_audit_log'):
            print("  ➕ Creating admin_audit_log table...")

        # ===== BLOG_POST TABLE =====
        if inspector.has_table('blog_post'):
            columns = {col['name'] for col in inspector.get_columns('blog_post')}
            for col_name, col_type in {
                'slug': 'VARCHAR(300)',
                'excerpt': 'TEXT DEFAULT \'\'',
                'cover_image': 'VARCHAR(500) DEFAULT \'\'',
                'images': "TEXT DEFAULT '[]'",
                'tags': 'VARCHAR(500) DEFAULT \'\'',
                'post_type': "VARCHAR(20) DEFAULT 'large'",
                'is_published': 'BOOLEAN DEFAULT FALSE',
                'updated_at': 'TIMESTAMP',
            }.items():
                if col_name not in columns:
                    print(f"  ➕ Adding blog_post.{col_name}...")
                    with db.engine.begin() as conn:
                        conn.execute(sa.text(
                            f'ALTER TABLE blog_post ADD COLUMN {col_name} {col_type}'
                        ))

        # ===== PRODUCT TABLE =====
        if inspector.has_table('product'):
            columns = {col['name'] for col in inspector.get_columns('product')}
            if 'images' not in columns:
                print("  ➕ Adding product.images...")
                with db.engine.begin() as conn:
                    conn.execute(sa.text("ALTER TABLE product ADD COLUMN images TEXT DEFAULT '[]'"))

        # ===== APP_SETTINGS — background_svg, text_color, card_color =====
        if inspector.has_table('app_settings'):
            columns = {col['name'] for col in inspector.get_columns('app_settings')}
            if 'background_svg' not in columns:
                print("  ➕ Adding app_settings.background_svg...")
                with db.engine.begin() as conn:
                    conn.execute(sa.text("ALTER TABLE app_settings ADD COLUMN background_svg TEXT DEFAULT ''"))
            if 'text_color' not in columns:
                print("  ➕ Adding app_settings.text_color...")
                with db.engine.begin() as conn:
                    conn.execute(sa.text("ALTER TABLE app_settings ADD COLUMN text_color VARCHAR(20) DEFAULT ''"))
            if 'card_color' not in columns:
                print("  ➕ Adding app_settings.card_color...")
                with db.engine.begin() as conn:
                    conn.execute(sa.text("ALTER TABLE app_settings ADD COLUMN card_color VARCHAR(20) DEFAULT ''"))
            if 'svg_opacity' not in columns:
                print("  ➕ Adding app_settings.svg_opacity...")
                with db.engine.begin() as conn:
                    conn.execute(sa.text("ALTER TABLE app_settings ADD COLUMN svg_opacity INTEGER DEFAULT 15"))

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
