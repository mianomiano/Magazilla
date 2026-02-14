from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.BigInteger, unique=True, nullable=False, index=True)
    username = db.Column(db.String(255), nullable=True)
    first_name = db.Column(db.String(255), nullable=True)
    last_name = db.Column(db.String(255), nullable=True)
    photo_url = db.Column(db.String(500), nullable=True)
    is_admin = db.Column(db.Boolean, default=False)
    is_banned = db.Column(db.Boolean, default=False)
    total_spent = db.Column(db.Integer, default=0)  # Total stars spent
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_visit = db.Column(db.DateTime, default=datetime.utcnow)
    
    orders = db.relationship('Order', backref='user', lazy='dynamic')
    cart_items = db.relationship('CartItem', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<User {self.telegram_id} {self.username}>'


class Category(db.Model):
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    icon = db.Column(db.String(50), nullable=True)  # Emoji or icon class
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    
    products = db.relationship('Product', backref='category', lazy='dynamic')
    
    def __repr__(self):
        return f'<Category {self.name}>'


class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price_stars = db.Column(db.Integer, nullable=False)  # Price in Telegram Stars
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    
    # Media
    thumbnail_url = db.Column(db.String(500), nullable=True)  # Main image/webm
    
    # Product details
    is_digital = db.Column(db.Boolean, default=True)
    digital_content = db.Column(db.Text, nullable=True)  # Download link or content sent after purchase
    stock = db.Column(db.Integer, default=-1)  # -1 = unlimited
    
    # Stats
    views = db.Column(db.Integer, default=0)
    purchases = db.Column(db.Integer, default=0)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    is_featured = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    gallery_images = db.relationship('ProductImage', backref='product', lazy='dynamic', cascade='all, delete-orphan')
    order_items = db.relationship('OrderItem', backref='product', lazy='dynamic')
    
    @property
    def in_stock(self):
        return self.stock == -1 or self.stock > 0
    
    def __repr__(self):
        return f'<Product {self.title} ⭐{self.price_stars}>'


class ProductImage(db.Model):
    __tablename__ = 'product_images'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    image_url = db.Column(db.String(500), nullable=False)
    is_video = db.Column(db.Boolean, default=False)  # True for webm
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CartItem(db.Model):
    __tablename__ = 'cart_items'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    product = db.relationship('Product', lazy='joined')
    
    __table_args__ = (db.UniqueConstraint('user_id', 'product_id'),)


class Order(db.Model):
    __tablename__ = 'orders'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Telegram payment
    telegram_payment_id = db.Column(db.String(255), nullable=True, unique=True)
    
    # Totals
    total_stars = db.Column(db.Integer, nullable=False)
    
    # Status: pending, paid, refunded, cancelled
    status = db.Column(db.String(20), default='pending', index=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)
    
    items = db.relationship('OrderItem', backref='order', lazy='joined', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Order #{self.id} ⭐{self.total_stars} {self.status}>'


class OrderItem(db.Model):
    __tablename__ = 'order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    price_stars = db.Column(db.Integer, nullable=False)  # Price at time of purchase


class Post(db.Model):
    """Simple blog/announcement posts with carousel galleries"""
    __tablename__ = 'posts'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=True)
    is_published = db.Column(db.Boolean, default=False)
    views = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    images = db.relationship('PostImage', backref='post', lazy='dynamic', cascade='all, delete-orphan')


class PostImage(db.Model):
    __tablename__ = 'post_images'
    
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)
    image_url = db.Column(db.String(500), nullable=False)
    is_video = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)


class VisitorLog(db.Model):
    """Track page views for stats"""
    __tablename__ = 'visitor_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.BigInteger, nullable=True)
    page = db.Column(db.String(255), nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
