"""Admin routes with authentication and CSRF protection"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime
from config import Config
from models import db, Product, Purchase, AppSettings
from r2_storage import upload_to_r2, delete_from_r2
from utils.auth import admin_required, verify_admin_password, log_admin_action
from utils.validation import allowed_file, validate_product_name, validate_price, validate_category, validate_color
from utils.decorators import limiter
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
        
        product = Product(
            name=name,
            description=description,
            price=price,
            is_free=is_free,
            category=category
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
        
        primary_color = request.form.get('primary_color', '#090c11')
        secondary_color = request.form.get('secondary_color', '#afe81f')
        accent_color = request.form.get('accent_color', '#1534fe')
        
        for color in [primary_color, secondary_color, accent_color]:
            valid, error = validate_color(color)
            if not valid:
                flash(error, 'error')
                return render_template('settings.html', settings=app_settings)
        
        app_settings.primary_color = primary_color
        app_settings.secondary_color = secondary_color
        app_settings.accent_color = accent_color
        
        if 'logo' in request.files:
            file = request.files['logo']
            if file and file.filename:
                if app_settings.logo_path:
                    delete_from_r2(app_settings.logo_path)
                key = upload_to_r2(file, 'logos')
                if key:
                    app_settings.logo_path = key
        
        db.session.commit()
        log_admin_action('update_settings', 'App settings updated')
        flash('Settings updated!', 'success')
        return redirect(url_for('admin_bp.dashboard'))
    
    return render_template('settings.html', settings=app_settings)


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
