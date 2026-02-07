"""Admin routes with authentication and CSRF protection"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime
from config import Config
from models import db, Product, Purchase, AppSettings, BlogPost, BlogLike
from r2_storage import upload_to_r2, delete_from_r2
from utils.auth import admin_required, verify_admin_password, log_admin_action
from utils.validation import allowed_file, validate_product_name, validate_price, validate_category, validate_color
from utils.decorators import limiter
from sqlalchemy import func
from sqlalchemy.exc import OperationalError, ProgrammingError
import json
import logging

admin_bp = Blueprint('admin_bp', __name__)
logger = logging.getLogger(__name__)


@admin_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    """Secure admin login"""
    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        
        if not password:
            return render_template('admin_login.html', error='Password required'), 400
        
        if verify_admin_password(password):
            session.permanent = True
            session['is_admin'] = True
            session['admin_user_id'] = 7165489081
            session['admin_username'] = 'Admin'
            
            log_admin_action('login', f"Login from {request.remote_addr}")
            return redirect(url_for('admin_bp.dashboard'))
        
        log_admin_action('failed_login', f"Failed login from {request.remote_addr}")
        return render_template('admin_login.html', error='Invalid password'), 401
    
    return render_template('admin_login.html', error=None)


@admin_bp.route('/logout')
def logout():
    """Logout admin user"""
    log_admin_action('logout', f"User {session.get('admin_user_id')} logged out")
    session.clear()
    return redirect(url_for('public_bp.index'))


@admin_bp.route('/')
@admin_required
def dashboard():
    """Admin dashboard"""
    products = Product.query.order_by(Product.created_at.desc()).all()
    total_stars = db.session.query(
        db.func.sum(Purchase.stars_paid)
    ).filter(Purchase.is_verified == True).scalar() or 0
    
    total_downloads = sum(p.download_count for p in products)
    total_purchases = Purchase.query.filter_by(is_verified=True).count()
    
    return render_template(
        'admin.html',
        products=products,
        total_downloads=total_downloads,
        total_products=len(products),
        total_purchases=total_purchases,
        total_stars=total_stars
    )


@admin_bp.route('/purchases')
@admin_required
def purchases():
    """Purchases analytics page"""
    # Get sort parameters
    sort_by = request.args.get('sort', 'sales')  # default sort by sales
    order = request.args.get('order', 'desc')  # default descending
    
    # Get all paid products with their stats
    paid_products = Product.query.filter(Product.is_free == False).all()
    
    product_stats = []
    now = datetime.utcnow()
    
    for product in paid_products:
        # Get purchase stats for this product
        purchases = Purchase.query.filter_by(
            product_id=product.id,
            is_verified=True
        ).all()
        
        sales_count = len(purchases)
        total_stars = sum(p.stars_paid for p in purchases)
        
        # Get last purchase date
        last_purchase = Purchase.query.filter_by(
            product_id=product.id,
            is_verified=True
        ).order_by(Purchase.purchased_at.desc()).first()
        
        last_purchase_date = last_purchase.purchased_at if last_purchase else None
        
        # Calculate days since product was added
        days_since_added = (now - product.created_at).days if product.created_at else 0
        days_since_added = max(days_since_added, 1)  # Minimum 1 day to avoid division by zero
        
        # Calculate ratio (sales per day)
        ratio = round(sales_count / days_since_added, 2)
        
        product_stats.append({
            'id': product.id,
            'name': product.name,
            'price': product.price,
            'sales_count': sales_count,
            'total_stars': total_stars,
            'date_added': product.created_at,
            'last_purchase': last_purchase_date,
            'days_active': days_since_added,
            'ratio': ratio,
            'is_active': product.is_active
        })
    
    # Sort the results
    reverse = (order == 'desc')
    
    if sort_by == 'name':
        product_stats.sort(key=lambda x: x['name'].lower(), reverse=reverse)
    elif sort_by == 'price':
        product_stats.sort(key=lambda x: x['price'], reverse=reverse)
    elif sort_by == 'sales':
        product_stats.sort(key=lambda x: x['sales_count'], reverse=reverse)
    elif sort_by == 'date_added':
        product_stats.sort(key=lambda x: x['date_added'] or datetime.min, reverse=reverse)
    elif sort_by == 'last_purchase':
        product_stats.sort(key=lambda x: x['last_purchase'] or datetime.min, reverse=reverse)
    elif sort_by == 'ratio':
        product_stats.sort(key=lambda x: x['ratio'], reverse=reverse)
    elif sort_by == 'stars':
        product_stats.sort(key=lambda x: x['total_stars'], reverse=reverse)
    
    # Calculate totals
    total_sales = sum(p['sales_count'] for p in product_stats)
    total_stars_earned = sum(p['total_stars'] for p in product_stats)
    
    return render_template(
        'purchases.html',
        products=product_stats,
        total_sales=total_sales,
        total_stars=total_stars_earned,
        sort_by=sort_by,
        order=order
    )


@admin_bp.route('/product/new', methods=['GET', 'POST'])
@admin_required
def new_product():
    """Create new product"""
    categories = list(set([
        c[0] for c in db.session.query(Product.category).distinct().all()
    ] + ['Icons', 'UI Kits', 'Templates', 'Stickers', 'General']))
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        valid, error = validate_product_name(name)
        if not valid:
            flash(error, 'error')
            return render_template('edit_product.html', product=None, categories=categories)
        
        description = request.form.get('description', '').strip()
        is_free = request.form.get('is_free') == 'on'
        
        price = 0
        if not is_free:
            try:
                price = int(request.form.get('price', 1))
                valid, error = validate_price(price, is_free)
                if not valid:
                    flash(error, 'error')
                    return render_template('edit_product.html', product=None, categories=categories)
            except ValueError:
                flash('Invalid price', 'error')
                return render_template('edit_product.html', product=None, categories=categories)
        
        category = request.form.get('category', 'General')
        if category == '_custom':
            category = request.form.get('custom_category', 'General').strip()
        
        valid, error = validate_category(category)
        if not valid:
            flash(error, 'error')
            return render_template('edit_product.html', product=None, categories=categories)
        
        # Validate badge color
        badge_color = request.form.get('badge_color', '#ff4444')
        badge_color_valid, _ = validate_color(badge_color)
        if not badge_color_valid:
            badge_color = '#ff4444'  # Fallback to default
        
        product = Product(
            name=name,
            description=description,
            price=price,
            is_free=is_free,
            category=category,
            tags=request.form.get('tags', '').strip()[:300],
            is_featured=request.form.get('is_featured') == 'on',
            badge_text=request.form.get('badge_text', '').strip()[:15],
            badge_color=badge_color,
            old_price=int(request.form.get('old_price', 0) or 0)
        )
        
        if 'thumbnail' in request.files:
            file = request.files['thumbnail']
            if file and file.filename and allowed_file(file.filename):
                key = upload_to_r2(file, 'thumbnails')
                if key:
                    product.thumbnail = key
        
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename:
                key = upload_to_r2(file, 'files')
                if key:
                    product.file_path = key
        
        db.session.add(product)
        db.session.commit()
        
        log_admin_action('create_product', json.dumps({'product_id': product.id, 'name': product.name}))
        flash(f'Product "{product.name}" created!', 'success')
        return redirect(url_for('admin_bp.dashboard'))
    
    return render_template('edit_product.html', product=None, categories=categories)


@admin_bp.route('/product/<int:pid>/edit', methods=['GET', 'POST'])
@admin_required
def edit_product(pid):
    """Edit existing product"""
    product = Product.query.get_or_404(pid)
    categories = list(set([
        c[0] for c in db.session.query(Product.category).distinct().all()
    ] + ['Icons', 'UI Kits', 'Templates', 'Stickers', 'General']))
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        valid, error = validate_product_name(name)
        if not valid:
            flash(error, 'error')
            return render_template('edit_product.html', product=product, categories=categories)
        
        product.name = name
        product.description = request.form.get('description', '').strip()
        product.is_free = request.form.get('is_free') == 'on'
        
        if not product.is_free:
            try:
                price = int(request.form.get('price', 1))
                valid, error = validate_price(price, product.is_free)
                if not valid:
                    flash(error, 'error')
                    return render_template('edit_product.html', product=product, categories=categories)
                product.price = price
            except ValueError:
                flash('Invalid price', 'error')
                return render_template('edit_product.html', product=product, categories=categories)
        else:
            product.price = 0
        
        category = request.form.get('category', 'General')
        if category == '_custom':
            category = request.form.get('custom_category', 'General').strip()
        
        valid, error = validate_category(category)
        if not valid:
            flash(error, 'error')
            return render_template('edit_product.html', product=product, categories=categories)
        
        product.category = category
        product.is_active = request.form.get('is_active') == 'on'
        
        # New fields
        product.tags = request.form.get('tags', '').strip()[:300]  # Max 300 chars
        product.is_featured = request.form.get('is_featured') == 'on'
        product.badge_text = request.form.get('badge_text', '').strip()[:15]  # Max 15 chars
        
        # Validate badge color
        badge_color = request.form.get('badge_color', '#ff4444')
        valid, error = validate_color(badge_color)
        if valid:
            product.badge_color = badge_color
        else:
            product.badge_color = '#ff4444'  # Fallback to default
        
        # Old price for strikethrough
        try:
            old_price = int(request.form.get('old_price', 0) or 0)
            product.old_price = max(0, old_price)
        except ValueError:
            product.old_price = 0
        
        if 'thumbnail' in request.files:
            file = request.files['thumbnail']
            if file and file.filename and allowed_file(file.filename):
                if product.thumbnail:
                    delete_from_r2(product.thumbnail)
                key = upload_to_r2(file, 'thumbnails')
                if key:
                    product.thumbnail = key
        
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename:
                if product.file_path:
                    delete_from_r2(product.file_path)
                key = upload_to_r2(file, 'files')
                if key:
                    product.file_path = key
        
        db.session.commit()
        log_admin_action('edit_product', json.dumps({'product_id': product.id, 'name': product.name}))
        flash(f'Product "{product.name}" updated!', 'success')
        return redirect(url_for('admin_bp.dashboard'))
    
    return render_template('edit_product.html', product=product, categories=categories)


@admin_bp.route('/product/<int:pid>/delete', methods=['POST'])
@admin_required
def delete_product(pid):
    """Delete product"""
    product = Product.query.get_or_404(pid)
    product_name = product.name
    
    if product.thumbnail:
        delete_from_r2(product.thumbnail)
    if product.file_path:
        delete_from_r2(product.file_path)
    
    db.session.delete(product)
    db.session.commit()
    
    log_admin_action('delete_product', json.dumps({'product_id': pid, 'name': product_name}))
    flash(f'Product "{product_name}" deleted!', 'success')
    return redirect(url_for('admin_bp.dashboard'))


@admin_bp.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    """App settings"""
    app_settings = AppSettings.query.first()
    if not app_settings:
        app_settings = AppSettings()
        db.session.add(app_settings)
        db.session.commit()
    
    if request.method == 'POST':
        app_settings.app_name = request.form.get('app_name', 'Magazilla').strip()
        
        # New header, contact, blog, footer settings
        app_settings.enable_blog = request.form.get('enable_blog') == 'on'
        app_settings.enable_product_messages = request.form.get('enable_product_messages') == 'on'
        app_settings.enable_contact_page = request.form.get('enable_contact_page') == 'on'
        app_settings.header_button_text = request.form.get('header_button_text', '').strip()[:100]
        app_settings.header_button_url = request.form.get('header_button_url', '').strip()[:500]
        app_settings.footer_text = request.form.get('footer_text', 'Powered by GramaZilla').strip()[:500]
        
        if 'logo' in request.files:
            file = request.files['logo']
            if file and file.filename:
                if app_settings.logo_path:
                    delete_from_r2(app_settings.logo_path)
                key = upload_to_r2(file, 'logos')
                if key:
                    app_settings.logo_path = key
        
        # Header image upload
        if 'header_image' in request.files:
            file = request.files['header_image']
            if file and file.filename and allowed_file(file.filename):
                if app_settings.header_image_path:
                    delete_from_r2(app_settings.header_image_path)
                key = upload_to_r2(file, 'headers')
                if key:
                    app_settings.header_image_path = key
        
        db.session.commit()
        log_admin_action('update_settings', 'App settings updated')
        flash('Settings updated!', 'success')
        return redirect(url_for('admin_bp.dashboard'))
    
    return render_template('settings.html', settings=app_settings)
    
@admin_bp.route('/appearance', methods=['GET', 'POST'])
@admin_required
def appearance():
    """Appearance customization"""
    app_settings = AppSettings.query.first()
    if not app_settings:
        app_settings = AppSettings()
        db.session.add(app_settings)
        db.session.commit()
    
    if request.method == 'POST':
        # Colors
        primary_color = request.form.get('primary_color', '#090c11')
        secondary_color = request.form.get('secondary_color', '#afe81f')
        accent_color = request.form.get('accent_color', '#1534fe')
        
        for color in [primary_color, secondary_color, accent_color]:
            valid, error = validate_color(color)
            if not valid:
                flash(error, 'error')
                return render_template('appearance.html', settings=app_settings)
        
        app_settings.primary_color = primary_color
        app_settings.secondary_color = secondary_color
        app_settings.accent_color = accent_color
        
        # Font
        font = request.form.get('font_family', 'inter')
        if font in ['inter', 'balsamiq', 'grandstander', 'montserrat', 'russo']:
            app_settings.font_family = font
        
        # Button style
        btn_style = request.form.get('button_style', 'soft')
        if btn_style in ['soft', 'flat', 'bubble', 'glow']:
            app_settings.button_style = btn_style
        
        # Button roundness
        btn_round = request.form.get('button_roundness', 'rounded')
        if btn_round in ['sharp', 'rounded', 'pill']:
            app_settings.button_roundness = btn_round
        
        # Card size
        card_size = request.form.get('card_size', 'medium')
        if card_size in ['small', 'medium', 'large']:
            app_settings.card_size = card_size
        
        # Card shape
        card_shape = request.form.get('card_shape', 'square')
        if card_shape in ['square', 'rectangle', 'wide']:
            app_settings.card_shape = card_shape
        
        # Card info
        card_info = request.form.get('card_info', 'full')
        if card_info in ['full', 'minimal', 'image']:
            app_settings.card_info = card_info
        
        # Header size
        header_size = request.form.get('header_size', 'normal')
        if header_size in ['compact', 'normal', 'tall']:
            app_settings.header_size = header_size
        
        # Show filters
        app_settings.show_filters = request.form.get('show_filters') == 'on'
        
        db.session.commit()
        log_admin_action('update_appearance', 'Appearance settings updated')
        flash('Appearance updated!', 'success')
        return redirect(url_for('admin_bp.appearance'))
    
    return render_template('appearance.html', settings=app_settings)


@admin_bp.route('/analytics')
@admin_required
def analytics():
    """Analytics and insights page"""
    from sqlalchemy import func, distinct
    from models import VisitorLog
    from datetime import timedelta
    
    # Total unique visitors
    total_visitors = db.session.query(
        func.count(distinct(VisitorLog.user_id))
    ).filter(VisitorLog.user_id.isnot(None)).scalar() or 0
    
    # Total page views
    total_views = VisitorLog.query.filter_by(action='view').count()
    
    # Total buy button clicks
    total_buy_clicks = VisitorLog.query.filter_by(action='buy_click').count()
    
    # Total purchases - handle is_test column gracefully
    try:
        total_purchases = Purchase.query.filter_by(is_verified=True, is_test=False).count()
    except (OperationalError, ProgrammingError) as e:
        # Fallback if is_test column doesn't exist
        logger.warning(f"is_test column not found in Purchase table: {e}")
        total_purchases = Purchase.query.filter_by(is_verified=True).count()
    
    # Conversion rate
    conversion_rate = round((total_purchases / total_buy_clicks * 100), 2) if total_buy_clicks > 0 else 0
    
    # Top viewed products
    top_products = db.session.query(
        Product.id, Product.name, Product.view_count
    ).order_by(Product.view_count.desc()).limit(10).all()
    
    # Recent visitors (last 20)
    recent_visitors = VisitorLog.query.filter(
        VisitorLog.user_id.isnot(None)
    ).order_by(VisitorLog.timestamp.desc()).limit(20).all()
    
    # Daily visitors for the last 7 days
    now = datetime.utcnow()
    daily_stats = []
    for i in range(6, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        
        day_visitors = db.session.query(
            func.count(distinct(VisitorLog.user_id))
        ).filter(
            VisitorLog.timestamp >= day_start,
            VisitorLog.timestamp < day_end,
            VisitorLog.user_id.isnot(None)
        ).scalar() or 0
        
        day_views = VisitorLog.query.filter(
            VisitorLog.timestamp >= day_start,
            VisitorLog.timestamp < day_end,
            VisitorLog.action == 'view'
        ).count()
        
        daily_stats.append({
            'date': day_start.strftime('%m/%d'),
            'visitors': day_visitors,
            'views': day_views
        })
    
    return render_template(
        'analytics.html',
        total_visitors=total_visitors,
        total_views=total_views,
        total_buy_clicks=total_buy_clicks,
        total_purchases=total_purchases,
        conversion_rate=conversion_rate,
        top_products=top_products,
        recent_visitors=recent_visitors,
        daily_stats=daily_stats
    )


# ===== BLOG MANAGEMENT ROUTES =====

@admin_bp.route('/blog')
@admin_required
def blog_list():
    """List all blog posts"""
    posts = BlogPost.query.order_by(BlogPost.created_at.desc()).all()
    return render_template('admin_blog_list.html', posts=posts)


@admin_bp.route('/blog/new', methods=['GET', 'POST'])
@admin_required
def blog_new():
    """Create new blog post"""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        author_name = request.form.get('author_name', 'Admin').strip()
        tags = request.form.get('tags', '').strip()
        show_likes = request.form.get('show_likes') == 'on'
        is_published = request.form.get('is_published') == 'on'
        
        if not title or not content:
            flash('Title and content are required', 'error')
            return render_template('admin_blog_edit.html', post=None)
        
        post = BlogPost(
            title=title,
            content=content,
            author_name=author_name,
            tags=tags,
            show_likes=show_likes,
            is_published=is_published
        )
        
        # Handle image upload
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename and allowed_file(file.filename):
                key = upload_to_r2(file, 'blog')
                if key:
                    post.image_path = key
        
        db.session.add(post)
        db.session.commit()
        
        log_admin_action('create_blog_post', json.dumps({'post_id': post.id, 'title': post.title}))
        flash(f'Blog post "{post.title}" created!', 'success')
        return redirect(url_for('admin_bp.blog_list'))
    
    return render_template('admin_blog_edit.html', post=None)


@admin_bp.route('/blog/<int:post_id>/edit', methods=['GET', 'POST'])
@admin_required
def blog_edit(post_id):
    """Edit existing blog post"""
    post = BlogPost.query.get_or_404(post_id)
    
    if request.method == 'POST':
        post.title = request.form.get('title', '').strip()
        post.content = request.form.get('content', '').strip()
        post.author_name = request.form.get('author_name', 'Admin').strip()
        post.tags = request.form.get('tags', '').strip()
        post.show_likes = request.form.get('show_likes') == 'on'
        post.is_published = request.form.get('is_published') == 'on'
        
        if not post.title or not post.content:
            flash('Title and content are required', 'error')
            return render_template('admin_blog_edit.html', post=post)
        
        # Handle image upload
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename and allowed_file(file.filename):
                if post.image_path:
                    delete_from_r2(post.image_path)
                key = upload_to_r2(file, 'blog')
                if key:
                    post.image_path = key
        
        db.session.commit()
        log_admin_action('edit_blog_post', json.dumps({'post_id': post.id, 'title': post.title}))
        flash(f'Blog post "{post.title}" updated!', 'success')
        return redirect(url_for('admin_bp.blog_list'))
    
    return render_template('admin_blog_edit.html', post=post)


@admin_bp.route('/blog/<int:post_id>/delete', methods=['POST'])
@admin_required
def blog_delete(post_id):
    """Delete blog post"""
    post = BlogPost.query.get_or_404(post_id)
    post_title = post.title
    
    if post.image_path:
        delete_from_r2(post.image_path)
    
    # Delete associated likes
    BlogLike.query.filter_by(post_id=post_id).delete()
    
    db.session.delete(post)
    db.session.commit()
    
    log_admin_action('delete_blog_post', json.dumps({'post_id': post_id, 'title': post_title}))
    flash(f'Blog post "{post_title}" deleted!', 'success')
    return redirect(url_for('admin_bp.blog_list'))


# NOTE: test-purchase endpoint removed for production security
