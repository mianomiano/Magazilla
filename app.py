import os
from flask import Flask, render_template
from flask_wtf.csrf import CSRFProtect
from config import Config
from models import db, AppSettings
from utils.decorators import limiter
from r2_storage import get_r2_url
from nav_icons import NAV_ICONS, ICON_LABELS

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
        
        return dict(r2_url=r2_url, settings=get_settings(),
                    nav_icons=NAV_ICONS, icon_labels=ICON_LABELS,
                    nav_menu=get_settings().get_nav_menu())
    
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


def _run_migration(conn, sql, label=""):
    """Run a single ALTER TABLE IF NOT EXISTS, log result."""
    import sqlalchemy as sa
    try:
        conn.execute(sa.text(sql))
        if label:
            print(f"  ✅ {label}")
    except Exception as e:
        # Column may already exist or other harmless race — log and continue
        print(f"  ⚠️  migration skipped ({label}): {e}")


def migrate_database():
    """Add missing columns to existing database — each step is independent."""
    import sqlalchemy as sa

    print("🔄 Checking database schema...")

    migrations = [
        # purchase table
        ("ALTER TABLE purchase ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT TRUE",
         "purchase.is_verified"),
        ("UPDATE purchase SET is_verified = TRUE WHERE is_verified IS NULL",
         "purchase.is_verified backfill"),
        ("ALTER TABLE purchase ADD COLUMN IF NOT EXISTS is_test BOOLEAN DEFAULT FALSE",
         "purchase.is_test"),

        # app_settings — appearance columns
        ("ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS font_family VARCHAR(50) DEFAULT 'inter'",
         "app_settings.font_family"),
        ("ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS button_style VARCHAR(20) DEFAULT 'soft'",
         "app_settings.button_style"),
        ("ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS button_roundness VARCHAR(20) DEFAULT 'rounded'",
         "app_settings.button_roundness"),
        ("ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS card_size VARCHAR(20) DEFAULT 'medium'",
         "app_settings.card_size"),
        ("ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS card_shape VARCHAR(20) DEFAULT 'square'",
         "app_settings.card_shape"),
        ("ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS card_info VARCHAR(20) DEFAULT 'full'",
         "app_settings.card_info"),
        ("ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS header_size VARCHAR(20) DEFAULT 'normal'",
         "app_settings.header_size"),
        ("ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS show_filters BOOLEAN DEFAULT TRUE",
         "app_settings.show_filters"),
        ("ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS background_svg TEXT DEFAULT ''",
         "app_settings.background_svg"),
        ("ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS text_color VARCHAR(20) DEFAULT ''",
         "app_settings.text_color"),
        ("ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS card_color VARCHAR(20) DEFAULT ''",
         "app_settings.card_color"),
        ("ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS svg_opacity INTEGER DEFAULT 15",
         "app_settings.svg_opacity"),
        ("ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS custom_head TEXT DEFAULT ''",
         "app_settings.custom_head"),
        ("ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS custom_css TEXT DEFAULT ''",
         "app_settings.custom_css"),
        ("ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS custom_js TEXT DEFAULT ''",
         "app_settings.custom_js"),
        ("ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS custom_html TEXT DEFAULT ''",
         "app_settings.custom_html"),
        ("ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS categories TEXT DEFAULT '[]'",
         "app_settings.categories"),
        ("ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS blog_categories TEXT DEFAULT '[]'",
         "app_settings.blog_categories"),
        ("ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS nav_menu TEXT DEFAULT ''",
         "app_settings.nav_menu"),
        ("ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS badge_color VARCHAR(20) DEFAULT 'accent'",
         "app_settings.badge_color"),

        # product table
        ("ALTER TABLE product ADD COLUMN IF NOT EXISTS images TEXT DEFAULT '[]'",
         "product.images"),
        ("ALTER TABLE product ADD COLUMN IF NOT EXISTS label_color VARCHAR(20) DEFAULT 'accent'",
         "product.label_color"),
        ("ALTER TABLE product ADD COLUMN IF NOT EXISTS is_pwyw BOOLEAN DEFAULT FALSE",
         "product.is_pwyw"),
        ("ALTER TABLE product ADD COLUMN IF NOT EXISTS bubble_text VARCHAR(15) DEFAULT ''",
         "product.bubble_text"),
        ("ALTER TABLE product ADD COLUMN IF NOT EXISTS bubble_shape VARCHAR(10) DEFAULT 'rounded'",
         "product.bubble_shape"),
        ("ALTER TABLE product ADD COLUMN IF NOT EXISTS bubble_pos VARCHAR(4) DEFAULT 'tr'",
         "product.bubble_pos"),
        ("ALTER TABLE product ADD COLUMN IF NOT EXISTS bubble_color VARCHAR(20) DEFAULT 'accent'",
         "product.bubble_color"),
        ("ALTER TABLE blog_post ADD COLUMN IF NOT EXISTS label_color VARCHAR(20) DEFAULT 'accent'",
         "blog_post.label_color"),

        # blog_post table
        ("ALTER TABLE blog_post ADD COLUMN IF NOT EXISTS slug VARCHAR(300)",
         "blog_post.slug"),
        ("ALTER TABLE blog_post ADD COLUMN IF NOT EXISTS excerpt TEXT DEFAULT ''",
         "blog_post.excerpt"),
        ("ALTER TABLE blog_post ADD COLUMN IF NOT EXISTS cover_image VARCHAR(500) DEFAULT ''",
         "blog_post.cover_image"),
        ("ALTER TABLE blog_post ADD COLUMN IF NOT EXISTS images TEXT DEFAULT '[]'",
         "blog_post.images"),
        ("ALTER TABLE blog_post ADD COLUMN IF NOT EXISTS tags VARCHAR(500) DEFAULT ''",
         "blog_post.tags"),
        ("ALTER TABLE blog_post ADD COLUMN IF NOT EXISTS post_type VARCHAR(20) DEFAULT 'large'",
         "blog_post.post_type"),
        ("ALTER TABLE blog_post ADD COLUMN IF NOT EXISTS is_published BOOLEAN DEFAULT FALSE",
         "blog_post.is_published"),
        ("ALTER TABLE blog_post ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP",
         "blog_post.updated_at"),
        ("ALTER TABLE blog_post ADD COLUMN IF NOT EXISTS subtitle VARCHAR(500) DEFAULT ''",
         "blog_post.subtitle"),
        ("ALTER TABLE blog_post ADD COLUMN IF NOT EXISTS category VARCHAR(100) DEFAULT ''",
         "blog_post.category"),
    ]

    try:
        with db.engine.begin() as conn:
            for sql, label in migrations:
                _run_migration(conn, sql, label)
        print("✅ Database schema up to date")
    except Exception as e:
        print(f"⚠️ Migration error: {e}")



# Create the app instance
app = create_app()


if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        debug=Config.DEBUG
    )
