"""Admin routes with authentication and CSRF protection"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime
from config import Config
from models import db, Product, Purchase, AppSettings, Block, BlogPost, BLOCK_TYPES
import re
from r2_storage import upload_to_r2, delete_from_r2
from utils.auth import admin_required, verify_admin_password, log_admin_action
from utils.validation import allowed_file, validate_product_name, validate_price, validate_category, validate_color
from utils.decorators import limiter
from sqlalchemy import func
import json

admin_bp = Blueprint('admin_bp', __name__)


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
    from datetime import datetime, timedelta
    products = Product.query.order_by(Product.created_at.desc()).all()
    total_stars = db.session.query(
        db.func.sum(Purchase.stars_paid)
    ).filter(Purchase.is_verified == True).scalar() or 0
    
    total_downloads = sum(p.download_count for p in products)
    total_purchases = Purchase.query.filter_by(is_verified=True).count()

    # Per-product sales analytics
    product_stats = []
    for p in products:
        sales = Purchase.query.filter_by(product_id=p.id, is_verified=True).count()
        earned = db.session.query(db.func.sum(Purchase.stars_paid)).filter_by(
            product_id=p.id, is_verified=True).scalar() or 0
        product_stats.append({'name': p.name, 'sales': sales, 'earned': earned})
    product_stats = sorted(product_stats, key=lambda x: x['sales'], reverse=True)[:8]

    # Last 7 days daily purchases
    daily = []
    for i in range(6, -1, -1):
        day = datetime.utcnow() - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)
        count = Purchase.query.filter(
            Purchase.is_verified == True,
            Purchase.purchased_at >= day_start,
            Purchase.purchased_at <= day_end
        ).count()
        stars = db.session.query(db.func.sum(Purchase.stars_paid)).filter(
            Purchase.is_verified == True,
            Purchase.purchased_at >= day_start,
            Purchase.purchased_at <= day_end
        ).scalar() or 0
        daily.append({'day': day.strftime('%a'), 'count': count, 'stars': stars})

    max_daily = max((d['stars'] for d in daily), default=1) or 1

    return render_template(
        'admin.html',
        products=products,
        total_downloads=total_downloads,
        total_products=len(products),
        total_purchases=total_purchases,
        total_stars=total_stars,
        product_stats=product_stats,
        daily=daily,
        max_daily=max_daily
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
    import json as _json
    _app_s = AppSettings.query.first()
    try:
        categories = _json.loads(_app_s.categories or '[]') if _app_s else []
    except Exception:
        categories = []
    if not categories:
        categories = ['Icons', 'UI Kits', 'Templates', 'Stickers', 'General']
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        valid, error = validate_product_name(name)
        if not valid:
            flash(error, 'error')
            return render_template('edit_product.html', product=None, categories=categories)
        
        description = request.form.get('description', '').strip()
        product_type = request.form.get('product_type', 'free')
        is_free = product_type in ('free', 'pwyw')
        is_pwyw = product_type == 'pwyw'
        
        price = 0
        if product_type == 'paid':
            try:
                price = int(request.form.get('price', 1))
                valid, error = validate_price(price, False)
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
        
        label_color = request.form.get('label_color', 'accent')
        if label_color not in ('accent','red','green','purple','yellow','orange','black','white'):
            label_color = 'accent'
        _valid_bcolors = ('accent','red','green','purple','yellow','orange','black','white')
        _btext = request.form.get('bubble_text', '').strip()[:15]
        _bshape = request.form.get('bubble_shape', 'rounded')
        if _bshape not in ('rect', 'rounded'): _bshape = 'rounded'
        _bpos = request.form.get('bubble_pos', 'tr')
        if _bpos not in ('tl','tr','bl','br'): _bpos = 'tr'
        _bcolor = request.form.get('bubble_color', 'accent')
        if _bcolor not in _valid_bcolors: _bcolor = 'accent'
        product = Product(
            name=name,
            description=description,
            price=price,
            is_free=is_free,
            is_pwyw=is_pwyw,
            category=category,
            label_color=label_color,
            bubble_text=_btext,
            bubble_shape=_bshape,
            bubble_pos=_bpos,
            bubble_color=_bcolor,
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

        gallery_files = request.files.getlist('gallery_images')
        gallery_keys = []
        for gf in gallery_files[:10]:
            if gf and gf.filename:
                gkey = upload_to_r2(gf, 'gallery')
                if gkey:
                    gallery_keys.append(gkey)
        if gallery_keys:
            product.images = json.dumps(gallery_keys)

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
    import json as _json
    product = Product.query.get_or_404(pid)
    _app_s = AppSettings.query.first()
    try:
        categories = _json.loads(_app_s.categories or '[]') if _app_s else []
    except Exception:
        categories = []
    if not categories:
        categories = ['Icons', 'UI Kits', 'Templates', 'Stickers', 'General']
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        valid, error = validate_product_name(name)
        if not valid:
            flash(error, 'error')
            return render_template('edit_product.html', product=product, categories=categories)
        
        product.name = name
        product.description = request.form.get('description', '').strip()
        _ptype = request.form.get('product_type', 'free')
        product.is_free = _ptype in ('free', 'pwyw')
        product.is_pwyw = _ptype == 'pwyw'
        
        if _ptype == 'paid':
            try:
                price = int(request.form.get('price', 1))
                valid, error = validate_price(price, False)
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
        lc = request.form.get('label_color', 'accent')
        product.label_color = lc if lc in ('accent','red','green','purple','yellow','orange','black','white') else 'accent'
        _valid_bcolors = ('accent','red','green','purple','yellow','orange','black','white')
        product.bubble_text = request.form.get('bubble_text', '').strip()[:15]
        _bs = request.form.get('bubble_shape', 'rounded')
        product.bubble_shape = _bs if _bs in ('rect', 'rounded') else 'rounded'
        _bp = request.form.get('bubble_pos', 'tr')
        product.bubble_pos = _bp if _bp in ('tl','tr','bl','br') else 'tr'
        _bc = request.form.get('bubble_color', 'accent')
        product.bubble_color = _bc if _bc in _valid_bcolors else 'accent'
        product.is_active = request.form.get('is_active') == 'on'
        
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

        if request.form.get('clear_images') == '1':
            for old_key in product.get_images():
                delete_from_r2(old_key)
            product.images = '[]'
        gallery_files = request.files.getlist('gallery_images')
        gallery_keys = list(product.get_images())
        for gf in gallery_files[:10]:
            if gf and gf.filename:
                gkey = upload_to_r2(gf, 'gallery')
                if gkey:
                    gallery_keys.append(gkey)
        product.images = json.dumps(gallery_keys[:10])

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
    
    import json as _json
    # Parse product categories from AppSettings
    try:
        cats_list = _json.loads(app_settings.categories or '[]')
    except Exception:
        cats_list = []
    categories_text = '\n'.join(cats_list)
    # Parse blog categories from AppSettings
    try:
        blog_cats_list = _json.loads(app_settings.blog_categories or '[]')
    except Exception:
        blog_cats_list = []
    blog_categories_text = '\n'.join(blog_cats_list)

    if request.method == 'POST':
        app_settings.app_name = request.form.get('app_name', 'Magazilla').strip()

        if 'logo' in request.files:
            file = request.files['logo']
            if file and file.filename:
                if app_settings.logo_path:
                    delete_from_r2(app_settings.logo_path)
                key = upload_to_r2(file, 'logos')
                if key:
                    app_settings.logo_path = key

        app_settings.custom_head = request.form.get('custom_head', '').strip()
        app_settings.custom_html = request.form.get('custom_html', '').strip()

        raw_cats = request.form.get('categories', '')
        cats = [c.strip() for c in raw_cats.splitlines() if c.strip()]
        app_settings.categories = _json.dumps(cats)

        raw_blog_cats = request.form.get('blog_categories', '')
        blog_cats = [c.strip() for c in raw_blog_cats.splitlines() if c.strip()]
        app_settings.blog_categories = _json.dumps(blog_cats)

        # Navigation menu
        nav_enabled = request.form.get('nav_enabled') == 'on'
        nav_mode = request.form.get('nav_mode', 'icons+text')
        nav_active_color = request.form.get('nav_active_color', '').strip()
        FIXED_HREFS = ['/', '/products', '/blog', '#']
        DEFAULTS = ['Home', 'Shop', 'Blog', 'Contact']
        DEFAULT_ICONS = ['home', 'store', 'blog', 'chat']
        nav_items = []
        for i, href in enumerate(FIXED_HREFS):
            nav_items.append({
                "name": request.form.get(f'nav_item_{i}_name', DEFAULTS[i]).strip(),
                "href": href,
                "icon": request.form.get(f'nav_item_{i}_icon', DEFAULT_ICONS[i]).strip(),
            })
        app_settings.nav_menu = _json.dumps({
            "enabled": nav_enabled,
            "mode": nav_mode,
            "active_color": nav_active_color,
            "menu_items": nav_items,
        })

        db.session.commit()
        log_admin_action('update_settings', 'App settings updated')
        flash('Settings updated!', 'success')
        return redirect(url_for('admin_bp.dashboard'))

    return render_template('settings.html', settings=app_settings,
                           categories_text=categories_text,
                           blog_categories_text=blog_categories_text)
    
@admin_bp.route('/remove-logo', methods=['POST'])
@admin_required
def remove_logo():
    """Remove header logo (just clears the database path)"""
    app_settings = AppSettings.query.first()
    if app_settings:
        # Optionally try to delete from R2 if it still exists
        if app_settings.logo_path:
            try:
                delete_from_r2(app_settings.logo_path)
            except Exception:
                pass  # File may already be gone from R2
        app_settings.logo_path = ''
        db.session.commit()
        log_admin_action('remove_logo', 'Header logo removed')
        flash('Logo removed!', 'success')
    return redirect(url_for('admin_bp.settings'))
    
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
        text_color = request.form.get('text_color', '').strip()
        card_color = request.form.get('card_color', '').strip()

        for color in [primary_color, secondary_color, accent_color]:
            valid, error = validate_color(color)
            if not valid:
                flash(error, 'error')
                return render_template('appearance.html', settings=app_settings)

        for color in [text_color, card_color]:
            if color:
                valid, error = validate_color(color)
                if not valid:
                    flash(error, 'error')
                    return render_template('appearance.html', settings=app_settings)

        app_settings.primary_color = primary_color
        app_settings.secondary_color = secondary_color
        app_settings.accent_color = accent_color
        app_settings.text_color = text_color
        app_settings.card_color = card_color
        
        # Badge / label color
        badge_color = request.form.get('badge_color', 'accent')
        if badge_color in ['accent', 'red', 'green', 'purple', 'yellow', 'orange', 'black', 'white']:
            app_settings.badge_color = badge_color

        # Font
        font = request.form.get('font_family', 'inter')
        allowed_fonts = [
            'inter', 'balsamiq', 'grandstander', 'montserrat', 'russo',
            'atlas', 'desolator', 'desolator_bold', 'desolator_light',
            'effortless', 'ragata', 'sfpro', 'sfpro_bold', 'crackajack', 'bradleyhand'
        ]
        if font in allowed_fonts:
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
        if card_shape in ['square', 'rectangle']:
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

        # Background SVG (inline code)
        bg_svg = request.form.get('background_svg', '').strip()
        app_settings.background_svg = bg_svg

        # SVG opacity
        try:
            svg_opacity = int(request.form.get('svg_opacity', 15))
            svg_opacity = max(1, min(100, svg_opacity))
        except (ValueError, TypeError):
            svg_opacity = 15
        app_settings.svg_opacity = svg_opacity

        db.session.commit()
        log_admin_action('update_appearance', 'Appearance settings updated')
        flash('Appearance updated!', 'success')
        return redirect(url_for('admin_bp.appearance'))
    
    return render_template('appearance.html', settings=app_settings)


@admin_bp.route('/test-purchase', methods=['POST'])
@admin_required
@limiter.limit("10 per minute")
def test_purchase():
    """Create TEST purchase (only for testing)"""
    data = request.json
    user_id = data.get('user_id')
    product_id = data.get('product_id')
    
    if not user_id or not product_id:
        return jsonify({'error': 'Missing user_id or product_id'}), 400
    
    try:
        user_id = int(user_id) if user_id != 'admin' else 7165489081
        product_id = int(product_id)
    except ValueError:
        return jsonify({'error': 'Invalid IDs'}), 400
    
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    
    if product.is_free:
        return jsonify({'error': 'Product is free'}), 400
    
    existing = Purchase.query.filter_by(user_id=user_id, product_id=product_id).first()
    if existing:
        return jsonify({'error': 'Already purchased', 'is_test': existing.is_test}), 400
    
    purchase = Purchase(
        user_id=user_id,
        product_id=product_id,
        telegram_payment_id=f"test_{user_id}_{product_id}_{int(datetime.utcnow().timestamp())}",
        stars_paid=product.price,
        is_verified=True,
        is_test=True
    )
    
    db.session.add(purchase)
    db.session.commit()
    
    log_admin_action('test_purchase', f"Test: user={user_id}, product={product_id}")
    
    return jsonify({'success': True, 'purchase_id': purchase.id})

# ═══════════════════════════════════════════════════════
#  PAGE BUILDER
# ═══════════════════════════════════════════════════════

BLOCK_TYPE_LABELS = {
    'product_grid':     '🛒 Product Grid',
    'featured_product': '⭐ Featured Product',
    'blog_posts':       '📝 Blog Posts',
    'donation':         '💜 Donation',
    'ad_banner':        '📢 Ad Banner',
    'divider':          '─ Divider',
    'text_section':     '📄 Text Section',
    'button_block':     '🔘 Button',
}


@admin_bp.route('/builder')
@admin_required
def builder():
    blocks = Block.query.order_by(Block.position).all()
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    return render_template(
        'builder.html',
        blocks=blocks,
        products=products,
        block_types=BLOCK_TYPES,
        block_type_labels=BLOCK_TYPE_LABELS,
    )


@admin_bp.route('/builder/add', methods=['POST'])
@admin_required
def builder_add():
    block_type = request.form.get('block_type', 'text_section')
    if block_type not in BLOCK_TYPES:
        flash('Invalid block type', 'error')
        return redirect(url_for('admin_bp.builder'))

    max_pos = db.session.query(db.func.max(Block.position)).scalar() or 0
    block = Block(
        block_type=block_type,
        title=BLOCK_TYPE_LABELS.get(block_type, block_type),
        position=max_pos + 1,
        is_visible=True,
        config='{}',
    )
    db.session.add(block)
    db.session.commit()
    log_admin_action('builder_add', f"Added block {block_type} id={block.id}")
    flash(f'Block added: {BLOCK_TYPE_LABELS.get(block_type)}', 'success')
    return redirect(url_for('admin_bp.builder_edit', bid=block.id))


@admin_bp.route('/builder/<int:bid>/edit', methods=['GET', 'POST'])
@admin_required
def builder_edit(bid):
    block = Block.query.get_or_404(bid)
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    blog_posts = BlogPost.query.order_by(BlogPost.created_at.desc()).all()

    if request.method == 'POST':
        block.title = request.form.get('title', block.title).strip()
        block.is_visible = request.form.get('is_visible') == 'on'

        cfg = block.get_config()

        if block.block_type == 'product_grid':
            product_ids = request.form.getlist('product_ids')
            cfg['product_ids'] = [int(i) for i in product_ids if i]

        elif block.block_type == 'featured_product':
            pid = request.form.get('product_id')
            if pid:
                cfg['product_id'] = int(pid)

        elif block.block_type == 'blog_posts':
            post_ids = request.form.getlist('post_ids')
            cfg['post_ids'] = [int(i) for i in post_ids if i]
            cfg['limit'] = int(request.form.get('limit', 3))

        elif block.block_type == 'donation':
            cfg['title'] = request.form.get('donation_title', '').strip()
            cfg['description'] = request.form.get('donation_description', '').strip()
            cfg['button_text'] = request.form.get('donation_button', '').strip()
            cfg['amount'] = request.form.get('donation_amount', '').strip()

        elif block.block_type == 'ad_banner':
            cfg['link'] = request.form.get('ad_link', '').strip()
            cfg['alt'] = request.form.get('ad_alt', '').strip()
            cfg['ad_code'] = request.form.get('ad_code', '').strip()
            if 'ad_image' in request.files:
                f = request.files['ad_image']
                if f and f.filename:
                    key = upload_to_r2(f, 'ads')
                    if key:
                        if cfg.get('image'):
                            delete_from_r2(cfg['image'])
                        cfg['image'] = key

        elif block.block_type == 'text_section':
            cfg['heading'] = request.form.get('text_heading', '').strip()
            cfg['body'] = request.form.get('text_body', '').strip()

        elif block.block_type == 'divider':
            cfg['style'] = request.form.get('divider_style', 'line')

        elif block.block_type == 'button_block':
            cfg['text'] = request.form.get('btn_text', 'Click Here').strip()[:60]
            cfg['bg_color'] = request.form.get('btn_bg_color', '#000000').strip()
            cfg['text_color'] = request.form.get('btn_text_color', '#ffffff').strip()
            link_preset = request.form.get('btn_link_preset', '')
            if link_preset and link_preset != '_custom':
                cfg['link'] = link_preset
            else:
                cfg['link'] = request.form.get('btn_custom_link', '#').strip() or '#'
            cfg['link_type'] = request.form.get('btn_link_type', 'internal')

        block.set_config(cfg)
        db.session.commit()
        log_admin_action('builder_edit', f"Edited block id={block.id}")
        flash('Block saved!', 'success')
        return redirect(url_for('admin_bp.builder'))

    return render_template(
        'builder_edit.html',
        block=block,
        products=products,
        blog_posts=blog_posts,
        block_type_labels=BLOCK_TYPE_LABELS,
        cfg=block.get_config(),
    )


@admin_bp.route('/builder/<int:bid>/delete', methods=['POST'])
@admin_required
def builder_delete(bid):
    block = Block.query.get_or_404(bid)
    db.session.delete(block)
    db.session.commit()
    log_admin_action('builder_delete', f"Deleted block id={bid}")
    flash('Block deleted', 'success')
    return redirect(url_for('admin_bp.builder'))


@admin_bp.route('/builder/<int:bid>/toggle', methods=['POST'])
@admin_required
def builder_toggle(bid):
    block = Block.query.get_or_404(bid)
    block.is_visible = not block.is_visible
    db.session.commit()
    return redirect(url_for('admin_bp.builder'))


@admin_bp.route('/builder/reorder', methods=['POST'])
@admin_required
def builder_reorder():
    order = request.form.getlist('order[]')
    for i, bid in enumerate(order):
        b = Block.query.get(int(bid))
        if b:
            b.position = i
    db.session.commit()
    return jsonify({'ok': True})


# ═══════════════════════════════════════════════════════
#  BLOG
# ═══════════════════════════════════════════════════════

def _slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text[:200]


def _unique_slug(title, exclude_id=None):
    base = _slugify(title)
    slug = base
    i = 1
    while True:
        q = BlogPost.query.filter_by(slug=slug)
        if exclude_id:
            q = q.filter(BlogPost.id != exclude_id)
        if not q.first():
            break
        slug = f"{base}-{i}"
        i += 1
    return slug


@admin_bp.route('/blog')
@admin_required
def blog_admin():
    posts = BlogPost.query.order_by(BlogPost.created_at.desc()).all()
    return render_template('blog_admin.html', posts=posts)


def _get_blog_categories():
    import json as _j
    app_s = AppSettings.query.first()
    if app_s:
        try:
            cats = _j.loads(app_s.blog_categories or '[]')
            return cats if cats else []
        except Exception:
            pass
    return []


@admin_bp.route('/blog/new', methods=['GET', 'POST'])
@admin_required
def blog_new():
    blog_cats = _get_blog_categories()
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Title is required', 'error')
            return render_template('blog_edit.html', post=None, blog_categories=blog_cats)

        slug = _unique_slug(title)
        _blc = request.form.get('label_color', 'accent')
        post = BlogPost(
            title=title,
            slug=slug,
            subtitle=request.form.get('subtitle', '').strip(),
            excerpt=request.form.get('excerpt', '').strip(),
            content=request.form.get('content', '').strip(),
            tags=request.form.get('tags', '').strip(),
            category=request.form.get('category', '').strip(),
            label_color=_blc if _blc in ('accent','red','green','purple','yellow','orange','black','white') else 'accent',
            post_type=request.form.get('post_type', 'banner_169'),
            is_published=request.form.get('is_published') == 'on',
        )

        if 'cover_image' in request.files:
            f = request.files['cover_image']
            if f and f.filename:
                key = upload_to_r2(f, 'blog')
                if key:
                    post.cover_image = key

        gallery_files = request.files.getlist('gallery_images')
        gallery_keys = []
        for gf in gallery_files[:10]:
            if gf and gf.filename:
                gkey = upload_to_r2(gf, 'gallery')
                if gkey:
                    gallery_keys.append(gkey)
        if gallery_keys:
            post.images = json.dumps(gallery_keys)

        db.session.add(post)
        db.session.commit()
        log_admin_action('blog_create', f"Created post: {title}")
        flash('Post created!', 'success')
        return redirect(url_for('admin_bp.blog_admin'))

    return render_template('blog_edit.html', post=None, blog_categories=blog_cats)


@admin_bp.route('/blog/<int:pid>/edit', methods=['GET', 'POST'])
@admin_required
def blog_edit(pid):
    post = BlogPost.query.get_or_404(pid)
    blog_cats = _get_blog_categories()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Title is required', 'error')
            return render_template('blog_edit.html', post=post, blog_categories=blog_cats)

        post.title = title
        post.slug = _unique_slug(title, exclude_id=post.id)
        post.subtitle = request.form.get('subtitle', '').strip()
        post.excerpt = request.form.get('excerpt', '').strip()
        post.content = request.form.get('content', '').strip()
        post.tags = request.form.get('tags', '').strip()
        post.category = request.form.get('category', '').strip()
        _blc2 = request.form.get('label_color', 'accent')
        post.label_color = _blc2 if _blc2 in ('accent','red','green','purple','yellow','orange','black','white') else 'accent'
        post.post_type = request.form.get('post_type', 'banner_169')
        post.is_published = request.form.get('is_published') == 'on'
        post.updated_at = datetime.utcnow()

        if 'cover_image' in request.files:
            f = request.files['cover_image']
            if f and f.filename:
                if post.cover_image:
                    delete_from_r2(post.cover_image)
                key = upload_to_r2(f, 'blog')
                if key:
                    post.cover_image = key

        if request.form.get('clear_images') == '1':
            for old_key in post.get_images():
                delete_from_r2(old_key)
            post.images = '[]'
        gallery_files = request.files.getlist('gallery_images')
        gallery_keys = list(post.get_images())
        for gf in gallery_files[:10]:
            if gf and gf.filename:
                gkey = upload_to_r2(gf, 'gallery')
                if gkey:
                    gallery_keys.append(gkey)
        post.images = json.dumps(gallery_keys[:10])

        db.session.commit()
        log_admin_action('blog_edit', f"Edited post id={post.id}")
        flash('Post saved!', 'success')
        return redirect(url_for('admin_bp.blog_admin'))

    return render_template('blog_edit.html', post=post, blog_categories=blog_cats)


@admin_bp.route('/blog/<int:pid>/delete', methods=['POST'])
@admin_required
def blog_delete(pid):
    post = BlogPost.query.get_or_404(pid)
    if post.cover_image:
        delete_from_r2(post.cover_image)
    db.session.delete(post)
    db.session.commit()
    log_admin_action('blog_delete', f"Deleted post id={pid}")
    flash('Post deleted', 'success')
    return redirect(url_for('admin_bp.blog_admin'))


@admin_bp.route('/blog/<int:pid>/toggle', methods=['POST'])
@admin_required
def blog_toggle(pid):
    post = BlogPost.query.get_or_404(pid)
    post.is_published = not post.is_published
    db.session.commit()
    return redirect(url_for('admin_bp.blog_admin'))
