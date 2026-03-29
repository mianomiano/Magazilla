from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Integer, default=0)
    is_free = db.Column(db.Boolean, default=True)
    category = db.Column(db.String(100), default='General')
    thumbnail = db.Column(db.String(500))
    file_path = db.Column(db.String(500))
    download_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'price': self.price,
            'is_free': self.is_free,
            'category': self.category,
            'thumbnail': self.thumbnail,
            'file_path': self.file_path,
            'download_count': self.download_count,
            'is_active': self.is_active
        }


class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.BigInteger, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    telegram_payment_id = db.Column(db.String(200), unique=True)
    stars_paid = db.Column(db.Integer, default=0)
    purchased_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_verified = db.Column(db.Boolean, default=False)
    is_test = db.Column(db.Boolean, default=False)
    
    __table_args__ = (
        db.Index('idx_user_product', 'user_id', 'product_id'),
        db.Index('idx_payment_id', 'telegram_payment_id'),
    )


class AppSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    app_name = db.Column(db.String(200), default='Magazilla')
    logo_path = db.Column(db.String(500), default='')
    
    # Colors
    primary_color = db.Column(db.String(20), default='#090c11')
    secondary_color = db.Column(db.String(20), default='#afe81f')
    accent_color = db.Column(db.String(20), default='#1534fe')
    
    # Appearance settings
    font_family = db.Column(db.String(50), default='inter')  # inter, balsamiq, grandstander, montserrat, russo
    button_style = db.Column(db.String(20), default='soft')  # soft, flat, bubble, glow
    button_roundness = db.Column(db.String(20), default='rounded')  # sharp, rounded, pill
    card_size = db.Column(db.String(20), default='medium')  # small, medium, large
    card_shape = db.Column(db.String(20), default='square')  # square, rectangle
    card_info = db.Column(db.String(20), default='full')  # full, minimal, image
    header_size = db.Column(db.String(20), default='normal')  # compact, normal, tall
    show_filters = db.Column(db.Boolean, default=True)


class AdminAuditLog(db.Model):
    """Track all admin actions for security"""
    id = db.Column(db.Integer, primary_key=True)
    admin_user_id = db.Column(db.BigInteger)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.Index('idx_admin_user', 'admin_user_id'),
        db.Index('idx_action_date', 'action', 'created_at'),
    )
