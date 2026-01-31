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
    
    # Exempt API webhook from CSRF (Telegram doesn't send CSRF tokens)
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


app = create_app()


if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=int(Config.APP_URL.split(':')[-1]) if ':' in Config.APP_URL else 5000,
        debug=Config.DEBUG
    )
