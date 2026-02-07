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
    
    # New fields for Phase 1
    tags = db.Column(db.String(300), default='')  # Comma-separated, max 3 keywords
    old_price = db.Column(db.Integer, default=0)  # If > 0, shown as strikethrough
    badge_text = db.Column(db.String(15), default='')  # e.g., "SALE", "NEW", "-50%"
    badge_color = db.Column(db.String(20), default='#ff4444')
    is_featured = db.Column(db.Boolean, default=False)  # Pin to top
    view_count = db.Column(db.Integer, default=0)  # For analytics
    
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
    card_shape = db.Column(db.String(20), default='square')  # square, rectangle, wide, list
    card_info = db.Column(db.String(20), default='full')  # full, minimal, image
    header_size = db.Column(db.String(20), default='normal')  # compact, normal, tall
    show_filters = db.Column(db.Boolean, default=True)
    
    # New fields for Phase 1
    layout_mode = db.Column(db.String(20), default='grid')  # grid, carousel, list
    enable_blog = db.Column(db.Boolean, default=False)
    enable_product_messages = db.Column(db.Boolean, default=False)
    enable_contact_page = db.Column(db.Boolean, default=False)
    header_image_path = db.Column(db.String(500), default='')
    header_button_text = db.Column(db.String(100), default='')
    header_button_url = db.Column(db.String(500), default='')
    footer_text = db.Column(db.String(500), default='Powered by GramaZilla')


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


class BlogPost(db.Model):
    """Blog posts for blogging mode"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(500))  # Optional image
    author_name = db.Column(db.String(100), default='Admin')
    likes_count = db.Column(db.Integer, default=0)
    show_likes = db.Column(db.Boolean, default=True)  # Owner can choose to show/hide like count
    is_published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tags = db.Column(db.String(300), default='')  # Comma-separated tags/keywords
    view_count = db.Column(db.Integer, default=0)  # Track views


class BlogLike(db.Model):
    """Track blog post likes by users"""
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('blog_post.id', ondelete='CASCADE'))
    user_id = db.Column(db.BigInteger, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('post_id', 'user_id', name='unique_post_user_like'),
    )


class VisitorLog(db.Model):
    """Track visitors and page views for analytics"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.BigInteger, nullable=True)  # Telegram user ID if available
    page = db.Column(db.String(200))  # e.g., '/', '/product/5'
    action = db.Column(db.String(50))  # 'view', 'buy_click', 'purchase'
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    session_id = db.Column(db.String(100))  # for anonymous tracking
    
    __table_args__ = (
        db.Index('idx_user_action', 'user_id', 'action'),
        db.Index('idx_timestamp', 'timestamp'),
    )
