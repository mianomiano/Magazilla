"""Public routes for the shop frontend"""
from flask import Blueprint, render_template, request, jsonify, redirect, session, url_for
from models import db, Product, Purchase, VisitorLog, BlogPost, BlogLike, AppSettings
from utils.decorators import limiter
from utils.telegram_auth import validate_telegram_init_data
from r2_storage import get_r2_url
from config import Config
from datetime import datetime
import uuid
import logging

public_bp = Blueprint('public_bp', __name__)
logger = logging.getLogger(__name__)


def log_visitor_action(page, action='view', user_id=None):
    """Log visitor action for analytics"""
    try:
        # Get or create session ID
        if 'session_id' not in session:
            session['session_id'] = str(uuid.uuid4())
        
        log = VisitorLog(
            user_id=user_id,
            page=page,
            action=action,
            session_id=session['session_id']
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        logger.error(f"Visitor logging error: {e}")
        # Don't crash if logging fails


@public_bp.route('/')
def index():
    """Main shop page"""
    # Get sorting parameter
    sort_by = request.args.get('sort', 'default')
    
    # Base query
    query = Product.query.filter_by(is_active=True)
    
    # Apply sorting
    if sort_by == 'price_asc':
        products = query.order_by(Product.price.asc()).all()
    elif sort_by == 'price_desc':
        products = query.order_by(Product.price.desc()).all()
    elif sort_by == 'newest':
        products = query.order_by(Product.created_at.desc()).all()
    elif sort_by == 'popular':
        products = query.order_by(Product.view_count.desc()).all()
    else:  # default - featured first, then newest
        products = query.order_by(Product.is_featured.desc(), Product.created_at.desc()).all()
    
    # Get unique categories from products
    categories = set()
    for p in products:
        if p.category:
            categories.add(p.category)
    categories = sorted(list(categories))
    
    # Get user_id from initData if available (for showing purchase status)
    user_id = None
    init_data = request.args.get('initData')
    if init_data:
        user_data = validate_telegram_init_data(init_data, Config.BOT_TOKEN)
        if user_data:
            user_id = user_data.get('id')
    
    # Log visitor
    log_visitor_action('/', 'view', user_id)
    
    # Get purchased product IDs for this user
    purchased_ids = set()
    if user_id:
        purchases = Purchase.query.filter_by(user_id=user_id, is_verified=True).all()
        purchased_ids = {p.product_id for p in purchases}
    
    return render_template(
        'index.html',
        products=products,
        categories=categories,
        purchased_ids=purchased_ids,
        user_id=user_id,
        r2_url=get_r2_url,
        current_sort=sort_by
    )


@public_bp.route('/product/<int:pid>')
def product_detail(pid):
    """Product detail page"""
    product = Product.query.get_or_404(pid)
    
    # Increment view count
    product.view_count = (product.view_count or 0) + 1
    db.session.commit()
    
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
    
    # Log visitor
    log_visitor_action(f'/product/{pid}', 'view', user_id)
    
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
        logger.error(f"Download error: {e}")
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


# ===== BLOG PUBLIC ROUTES =====

@public_bp.route('/blog')
def blog_index():
    """Blog listing page"""
    try:
        app_settings = AppSettings.query.first()
        if not app_settings or not app_settings.enable_blog:
            return redirect('/')
        
        posts = BlogPost.query.filter_by(is_published=True).order_by(BlogPost.created_at.desc()).all()
        
        # Get user_id from initData if available
        user_id = None
        init_data = request.args.get('initData')
        if init_data:
            user_data = validate_telegram_init_data(init_data, Config.BOT_TOKEN)
            if user_data:
                user_id = user_data.get('id')
        
        # Get liked post IDs for this user
        liked_post_ids = set()
        if user_id:
            likes = BlogLike.query.filter_by(user_id=user_id).all()
            liked_post_ids = {like.post_id for like in likes}
        
        return render_template(
            'blog_index.html',
            posts=posts,
            liked_post_ids=liked_post_ids,
            user_id=user_id,
            r2_url=get_r2_url
        )
    except Exception as e:
        logger.error(f"Blog index error: {e}")
        # Redirect to home if blog tables don't exist yet
        return redirect('/')


@public_bp.route('/blog/<int:post_id>')
def blog_detail(post_id):
    """Blog post detail page"""
    try:
        app_settings = AppSettings.query.first()
        if not app_settings or not app_settings.enable_blog:
            return redirect('/')
        
        post = BlogPost.query.get_or_404(post_id)
        
        if not post.is_published:
            return redirect(url_for('public_bp.blog_index'))
        
        # Increment view count
        post.view_count = (post.view_count or 0) + 1
        db.session.commit()
        
        # Get user_id from initData if available
        user_id = None
        init_data = request.args.get('initData') or request.headers.get('X-Telegram-Init-Data')
        if init_data:
            user_data = validate_telegram_init_data(init_data, Config.BOT_TOKEN)
            if user_data:
                user_id = user_data.get('id')
        
        # Check if user liked this post
        user_liked = False
        if user_id:
            like = BlogLike.query.filter_by(post_id=post_id, user_id=user_id).first()
            user_liked = like is not None
        
        return render_template(
            'blog_detail.html',
            post=post,
            user_liked=user_liked,
            user_id=user_id,
            r2_url=get_r2_url
        )
    except Exception as e:
        logger.error(f"Blog detail error: {e}")
        # Redirect to home if blog tables don't exist yet
        return redirect('/')
