"""Public routes for the shop frontend"""
import json
from flask import Blueprint, render_template, request, jsonify, redirect, abort
from models import db, Product, Purchase, Block, BlogPost, AppSettings
from utils.decorators import limiter
from utils.telegram_auth import validate_telegram_init_data
from r2_storage import get_r2_url
from config import Config

public_bp = Blueprint('public_bp', __name__)


def _get_app_categories():
    """Return the admin-defined list of categories."""
    app_s = AppSettings.query.first()
    if app_s:
        try:
            cats = json.loads(app_s.categories or '[]')
            if cats:
                return cats
        except Exception:
            pass
    return []


@public_bp.route('/pay-test')
def pay_test():
    """Minimal Stars payment test page — no dependencies on any app settings"""
    return render_template('pay_test.html')


@public_bp.route('/')
def index():
    """Main shop page"""
    all_active = Product.query.filter_by(is_active=True).order_by(Product.created_at.desc()).all()
    all_products_map = {p.id: p for p in all_active}

    # Categories from AppSettings (admin-defined)
    categories = _get_app_categories()

    # Get user_id from initData if available (for showing purchase status)
    user_id = None
    init_data = request.args.get('initData')
    if init_data:
        user_data = validate_telegram_init_data(init_data, Config.BOT_TOKEN)
        if user_data:
            user_id = user_data.get('id')

    # Get purchased product IDs for this user
    purchased_ids = set()
    if user_id:
        purchases = Purchase.query.filter_by(user_id=user_id, is_verified=True).all()
        purchased_ids = {p.product_id for p in purchases}

    # Fetch page builder blocks (visible, ordered)
    blocks = Block.query.filter_by(is_visible=True).order_by(Block.position).all()
    all_published_posts = BlogPost.query.filter_by(is_published=True).order_by(BlogPost.created_at.desc()).all()
    recent_posts = all_published_posts[:10]
    all_posts_map = {p.id: p for p in all_published_posts}

    return render_template(
        'index.html',
        products=all_active,
        categories=categories,
        purchased_ids=purchased_ids,
        user_id=user_id,
        r2_url=get_r2_url,
        blocks=blocks,
        all_products=all_products_map,
        recent_posts=recent_posts,
        all_posts_map=all_posts_map,
    )


@public_bp.route('/products')
def products_page():
    """Dedicated products page with search + category filter."""
    q = request.args.get('q', '').strip().lower()
    cat = request.args.get('cat', '').strip()

    all_active = Product.query.filter_by(is_active=True).order_by(Product.created_at.desc()).all()
    categories = _get_app_categories()

    # User auth
    user_id = None
    init_data = request.args.get('initData')
    if init_data:
        user_data = validate_telegram_init_data(init_data, Config.BOT_TOKEN)
        if user_data:
            user_id = user_data.get('id')
    purchased_ids = set()
    if user_id:
        purchases = Purchase.query.filter_by(user_id=user_id, is_verified=True).all()
        purchased_ids = {p.product_id for p in purchases}

    return render_template(
        'products.html',
        products=all_active,
        categories=categories,
        q=q,
        active_cat=cat,
        purchased_ids=purchased_ids,
        user_id=user_id,
        r2_url=get_r2_url,
    )


@public_bp.route('/product/<int:pid>')
def product_detail(pid):
    """Product detail page"""
    product = Product.query.get_or_404(pid)
    
    # Check if user has purchased (from initData or header)
    purchased = False
    user_id = None
    
    # Try getting initData from query param or header
    init_data = (
        request.args.get('initData') or
        request.headers.get('X-Telegram-Init-Data')
    )
    
    if init_data:
        user_data = validate_telegram_init_data(init_data, Config.BOT_TOKEN)
        if user_data:
            user_id = user_data.get('id')
            if user_id:
                purchase = Purchase.query.filter_by(
                    user_id=user_id,
                    product_id=pid,
                    is_verified=True
                ).first()
                purchased = purchase is not None
    
    return render_template(
        'product.html',
        product=product,
        purchased=purchased,
        user_id=user_id,
        r2_url=get_r2_url,
        bot_username=Config.BOT_USERNAME
    )


@public_bp.route('/download/<int:pid>')
@limiter.limit("20 per minute")
def download(pid):
    """Download product file - requires Telegram auth for paid products"""
    product = Product.query.get_or_404(pid)
    
    if not product.file_path:
        return jsonify({'error': 'No file available'}), 404
    
    # Free products - allow download without auth
    if product.is_free:
        return _process_download(product)
    
    # Paid products - require valid Telegram auth
    init_data = (
        request.headers.get('X-Telegram-Init-Data') or
        request.args.get('initData')
    )
    
    if not init_data:
        return jsonify({'error': 'Authentication required. Please open from Telegram.'}), 401
    
    user_data = validate_telegram_init_data(init_data, Config.BOT_TOKEN)
    if not user_data:
        return jsonify({'error': 'Invalid authentication'}), 401
    
    user_id = user_data.get('id')
    
    # Check purchase
    purchase = Purchase.query.filter_by(
        user_id=user_id,
        product_id=pid,
        is_verified=True
    ).first()
    
    if not purchase:
        return jsonify({'error': 'Purchase required'}), 403
    
    return _process_download(product)


def _process_download(product):
    """Process the actual download - generates signed URL"""
    try:
        # Generate signed URL that expires in 5 minutes
        download_url = get_r2_url(product.file_path, expires=300)
        
        if not download_url:
            return jsonify({'error': 'File temporarily unavailable'}), 500
        
        # Increment download count
        product.download_count = (product.download_count or 0) + 1
        db.session.commit()
        
        return redirect(download_url)
    
    except Exception as e:
        print(f"Download error: {e}")
        return jsonify({'error': 'Download failed'}), 500


@public_bp.route('/category/<string:cat_name>')
def category_products(cat_name):
    """Products filtered by category"""
    products = Product.query.filter_by(
        category=cat_name,
        is_active=True
    ).order_by(Product.created_at.desc()).all()
    
    # Get all categories
    all_products = Product.query.filter_by(is_active=True).all()
    categories = set()
    for p in all_products:
        if p.category:
            categories.add(p.category)
    categories = sorted(list(categories))
    
    return render_template(
        'index.html',
        products=products,
        categories=categories,
        current_category=cat_name,
        purchased_ids=set(),
        r2_url=get_r2_url
    )


@public_bp.route('/health')
def health_check():
    """Health check endpoint for Railway"""
    return jsonify({'status': 'ok'}), 200

# ─── Public Blog ─────────────────────────────────────────────────────────────

@public_bp.route('/blog')
def blog():
    import json as _j
    posts = BlogPost.query.filter_by(is_published=True).order_by(BlogPost.created_at.desc()).all()
    app_settings = AppSettings.query.first()
    blog_cats = []
    if app_settings:
        try:
            blog_cats = _j.loads(app_settings.blog_categories or '[]') or []
        except Exception:
            blog_cats = []
    settings = app_settings
    return render_template('blog.html', posts=posts, r2_url=get_r2_url,
                           blog_categories=blog_cats, settings=settings)


@public_bp.route('/blog/<slug>')
def blog_post(slug):
    post = BlogPost.query.filter_by(slug=slug, is_published=True).first_or_404()
    return render_template('blog_post.html', post=post, r2_url=get_r2_url)
