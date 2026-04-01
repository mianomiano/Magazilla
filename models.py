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
    images = db.Column(db.Text, default='[]')          # JSON array of R2 keys
    file_path = db.Column(db.String(500))
    download_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    def get_images(self):
        import json
        try:
            return json.loads(self.images or '[]')
        except Exception:
            return []
    
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
    text_color = db.Column(db.String(20), default='')
    card_color = db.Column(db.String(20), default='')
    
    # Appearance settings
    font_family = db.Column(db.String(50), default='inter')  # inter, balsamiq, grandstander, montserrat, russo
    button_style = db.Column(db.String(20), default='soft')  # soft, flat, bubble, glow
    button_roundness = db.Column(db.String(20), default='rounded')  # sharp, rounded, pill
    card_size = db.Column(db.String(20), default='medium')  # small, medium, large
    card_shape = db.Column(db.String(20), default='square')  # square, rectangle
    card_info = db.Column(db.String(20), default='full')  # full, minimal, image
    header_size = db.Column(db.String(20), default='normal')  # compact, normal, tall
    show_filters = db.Column(db.Boolean, default=True)
    background_svg = db.Column(db.Text, default='')    # SVG code or R2 key
    svg_opacity = db.Column(db.Integer, default=15)   # 1-100 percent

    # Custom code injection
    custom_head = db.Column(db.Text, default='')  # injected inside <head>
    custom_html = db.Column(db.Text, default='')  # HTML banner (with inline style/script) injected at top of page

    # Product categories (JSON list of strings)
    categories = db.Column(db.Text, default='[]')

    # Blog post categories (JSON list of strings — separate from product categories)
    blog_categories = db.Column(db.Text, default='[]')

    # Bottom navigation menu (JSON config)
    nav_menu = db.Column(db.Text, default='')

    def get_nav_menu(self):
        import json
        default = {
            "enabled": True,
            "mode": "icons+text",
            "active_color": "",
            "menu_items": [
                {"name": "Home", "href": "/", "icon": "home"},
                {"name": "Shop", "href": "/products", "icon": "store"},
                {"name": "Blog", "href": "/blog", "icon": "blog"},
                {"name": "Contact", "href": "#", "icon": "chat"},
            ]
        }
        FIXED_HREFS = ['/', '/products', '/blog', '#']
        if not self.nav_menu:
            return default
        try:
            data = json.loads(self.nav_menu)
            if "menu_items" not in data:
                data["menu_items"] = data.pop("items", default["menu_items"])
            # Ensure exactly 4 items with correct fixed hrefs
            saved = data.get("menu_items", [])
            normalized = []
            for i, href in enumerate(FIXED_HREFS):
                def_item = default["menu_items"][i]
                saved_item = saved[i] if i < len(saved) else {}
                normalized.append({
                    "name": saved_item.get("name", def_item["name"]),
                    "href": href,
                    "icon": saved_item.get("icon", def_item["icon"]),
                })
            data["menu_items"] = normalized
            return data
        except Exception:
            return default


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


# ─── Page Builder ───────────────────────────────────────────────────────────

BLOCK_TYPES = [
    'product_grid',      # All active products grid
    'featured_product',  # Single highlighted product
    'blog_posts',        # Latest N blog posts
    'donation',          # Donation / support block
    'ad_banner',         # Image + link ad banner
    'divider',           # Visual separator
    'text_section',      # Rich text / HTML section
]

class Block(db.Model):
    """Page layout block — defines what appears on the public home page"""
    id = db.Column(db.Integer, primary_key=True)
    block_type = db.Column(db.String(50), nullable=False)          # one of BLOCK_TYPES
    title = db.Column(db.String(200), default='')                  # optional admin label
    position = db.Column(db.Integer, default=0)                    # sort order
    is_visible = db.Column(db.Boolean, default=True)
    config = db.Column(db.Text, default='{}')                      # JSON config blob
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_config(self):
        import json
        try:
            return json.loads(self.config or '{}')
        except Exception:
            return {}

    def set_config(self, data: dict):
        import json
        self.config = json.dumps(data)


# ─── Blog ────────────────────────────────────────────────────────────────────

class BlogPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    subtitle = db.Column(db.String(500), default='')               # second title shown on banner
    slug = db.Column(db.String(300), unique=True)
    excerpt = db.Column(db.Text, default='')
    content = db.Column(db.Text, default='')
    cover_image = db.Column(db.String(500), default='')            # R2 key
    images = db.Column(db.Text, default='[]')                      # JSON array of R2 keys
    tags = db.Column(db.String(500), default='')                   # comma-separated
    category = db.Column(db.String(100), default='')               # blog post category
    post_type = db.Column(db.String(20), default='banner_169')     # 'banner_169' or 'banner_245'
    is_published = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def tag_list(self):
        return [t.strip() for t in (self.tags or '').split(',') if t.strip()]

    def get_images(self):
        import json
        try:
            return json.loads(self.images or '[]')
        except Exception:
            return []
