import os
import time
import json
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, jsonify, redirect,
    url_for, session, abort, g
)
from flask_wtf.csrf import CSRFProtect
from config import Config
from models import (
    db, User, Category, Product, ProductImage, CartItem,
    Order, OrderItem, Post, PostImage, VisitorLog
)
from r2_storage import r2
from bot import bot, validate_webapp_data, get_or_create_user, setup_webhook, process_webhook_update, create_stars_invoice

import telebot

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
csrf = CSRFProtect(app)

with app.app_context():
    db.create_all()
    
    # Auto-seed default categories if empty
    if Category.query.count() == 0:
        defaults = [
            ('Digital Art', 'digital-art', '🎨', 1),
            ('Templates', 'templates', '📄', 2),
            ('Music', 'music', '🎵', 3),
            ('Software', 'software', '💻', 4),
            ('Gaming', 'gaming', '🎮', 5),
            ('Education', 'education', '📚', 6),
            ('Other', 'other', '📦', 7),
        ]
        for name, slug, icon, order in defaults:
            db.session.add(Category(name=name, slug=slug, icon=icon, sort_order=order, is_active=True))
        db.session.commit()
        print("✅ Default categories created")


# ─── Helpers & Middleware ──────────────────────────────────────────
def log_visit(page):
    try:
        log = VisitorLog(
            telegram_id=session.get('telegram_id'),
            page=page,
            ip_address=request.remote_addr,
            user_agent=str(request.user_agent)[:500]
        )
        db.session.add(log)
        db.session.commit()
    except:
        db.session.rollback()


def get_current_user():
    tid = session.get('telegram_id')
    if tid:
        return User.query.filter_by(telegram_id=tid).first()
    return None


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated


def api_auth_required(f):
    """For AJAX API calls from the mini app."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Check session first
        if session.get('telegram_id'):
            g.user = get_current_user()
            if g.user:
                return f(*args, **kwargs)

        # Check initData header
        init_data = request.headers.get('X-Telegram-Init-Data', '')
        if init_data:
            user_data = validate_webapp_data(init_data)
            if user_data:
                g.user = get_or_create_user(
                    telegram_id=user_data['id'],
                    username=user_data.get('username'),
                    first_name=user_data.get('first_name'),
                    last_name=user_data.get('last_name'),
                    photo_url=user_data.get('photo_url')
                )
                session['telegram_id'] = user_data['id']
                session['is_admin'] = g.user.is_admin
                return f(*args, **kwargs)

        return jsonify({'error': 'Unauthorized'}), 401
    return decorated


# ─── Telegram Webhook ─────────────────────────────────────────────
@app.route(f'/webhook/{Config.BOT_TOKEN}', methods=['POST'])
@csrf.exempt
def telegram_webhook():
    try:
        json_data = request.get_json(force=True)
        process_webhook_update(json_data)
    except Exception as e:
        print(f"Webhook error: {e}")
    return 'OK', 200


# ─── Auth Route (Mini App lands here) ─────────────────────────────
@app.route('/auth', methods=['POST'])
@csrf.exempt
def auth():
    """Authenticate user from Telegram Mini App initData."""
    init_data = request.form.get('initData') or request.json.get('initData', '')
    user_data = validate_webapp_data(init_data)

    if not user_data:
        return jsonify({'error': 'Invalid auth'}), 401

    user = get_or_create_user(
        telegram_id=user_data['id'],
        username=user_data.get('username'),
        first_name=user_data.get('first_name'),
        last_name=user_data.get('last_name'),
        photo_url=user_data.get('photo_url')
    )

    session['telegram_id'] = user_data['id']
    session['is_admin'] = user.is_admin
    session.permanent = True

    return jsonify({
        'ok': True,
        'user': {
            'id': user.telegram_id,
            'username': user.username,
            'first_name': user.first_name,
            'is_admin': user.is_admin
        }
    })


# ─── Shop Pages ───────────────────────────────────────────────────
@app.route('/')
def index():
    return redirect(url_for('shop'))


@app.route('/shop')
def shop():
    log_visit('/shop')
    categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()
    featured = Product.query.filter_by(is_active=True, is_featured=True).order_by(Product.sort_order).limit(10).all()
    latest = Product.query.filter_by(is_active=True).order_by(Product.created_at.desc()).limit(20).all()
    posts = Post.query.filter_by(is_published=True).order_by(Post.created_at.desc()).limit(5).all()
    return render_template('shop.html', categories=categories, featured=featured, latest=latest, posts=posts)


@app.route('/shop/category/<slug>')
def shop_category(slug):
    cat = Category.query.filter_by(slug=slug, is_active=True).first_or_404()
    products = Product.query.filter_by(category_id=cat.id, is_active=True).order_by(Product.sort_order).all()
    return render_template('shop.html', categories=Category.query.filter_by(is_active=True).all(),
                           featured=[], latest=products, current_category=cat, posts=[])


@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    product.views = (product.views or 0) + 1
    db.session.commit()
    log_visit(f'/product/{product_id}')
    gallery = ProductImage.query.filter_by(product_id=product.id).order_by(ProductImage.sort_order).all()
    related = Product.query.filter(
        Product.category_id == product.category_id,
        Product.id != product.id,
        Product.is_active == True
    ).limit(6).all()
    return render_template('product.html', product=product, gallery=gallery, related=related)


@app.route('/cart')
def cart_page():
    log_visit('/cart')
    return render_template('cart.html')


@app.route('/profile')
def profile_page():
    log_visit('/profile')
    return render_template('profile.html')


@app.route('/post/<int:post_id>')
def post_detail(post_id):
    post = Post.query.get_or_404(post_id)
    post.views = (post.views or 0) + 1
    db.session.commit()
    images = PostImage.query.filter_by(post_id=post.id).order_by(PostImage.sort_order).all()
    return render_template('post.html', post=post, images=images)


# ─── Cart API ─────────────────────────────────────────────────────
@app.route('/api/cart', methods=['GET'])
@api_auth_required
def api_cart_get():
    items = CartItem.query.filter_by(user_id=g.user.id).all()
    total = sum(item.product.price_stars * item.quantity for item in items if item.product)
    return jsonify({
        'items': [{
            'id': item.id,
            'product_id': item.product_id,
            'title': item.product.title,
            'price_stars': item.product.price_stars,
            'thumbnail_url': item.product.thumbnail_url,
            'quantity': item.quantity,
            'subtotal': item.product.price_stars * item.quantity
        } for item in items if item.product],
        'total': total,
        'count': len(items)
    })


@app.route('/api/cart/add', methods=['POST'])
@api_auth_required
def api_cart_add():
    data = request.get_json()
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)

    product = Product.query.get(product_id)
    if not product or not product.is_active:
        return jsonify({'error': 'Product not found'}), 404
    if not product.in_stock:
        return jsonify({'error': 'Out of stock'}), 400

    existing = CartItem.query.filter_by(user_id=g.user.id, product_id=product_id).first()
    if existing:
        existing.quantity += quantity
    else:
        item = CartItem(user_id=g.user.id, product_id=product_id, quantity=quantity)
        db.session.add(item)

    db.session.commit()
    count = CartItem.query.filter_by(user_id=g.user.id).count()
    return jsonify({'ok': True, 'cart_count': count})


@app.route('/api/cart/update', methods=['POST'])
@api_auth_required
def api_cart_update():
    data = request.get_json()
    item_id = data.get('item_id')
    quantity = data.get('quantity', 1)

    item = CartItem.query.filter_by(id=item_id, user_id=g.user.id).first()
    if not item:
        return jsonify({'error': 'Item not found'}), 404

    if quantity <= 0:
        db.session.delete(item)
    else:
        item.quantity = quantity

    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/cart/remove', methods=['POST'])
@api_auth_required
def api_cart_remove():
    data = request.get_json()
    item_id = data.get('item_id')

    item = CartItem.query.filter_by(id=item_id, user_id=g.user.id).first()
    if item:
        db.session.delete(item)
        db.session.commit()

    return jsonify({'ok': True})


# ─── Checkout / Payment API ───────────────────────────────────────
@app.route('/api/checkout', methods=['POST'])
@api_auth_required
def api_checkout():
    """Create order and send Stars invoice via bot."""
    cart_items = CartItem.query.filter_by(user_id=g.user.id).all()
    if not cart_items:
        return jsonify({'error': 'Cart is empty'}), 400

    total = 0
    order_items = []
    for ci in cart_items:
        if not ci.product or not ci.product.is_active:
            continue
        if not ci.product.in_stock:
            return jsonify({'error': f'{ci.product.title} is out of stock'}), 400
        subtotal = ci.product.price_stars * ci.quantity
        total += subtotal
        order_items.append({
            'product_id': ci.product_id,
            'quantity': ci.quantity,
            'price_stars': ci.product.price_stars
        })

    if total <= 0:
        return jsonify({'error': 'Invalid cart'}), 400

    # Create order
    order = Order(user_id=g.user.id, total_stars=total, status='pending')
    db.session.add(order)
    db.session.flush()

    for oi in order_items:
        db.session.add(OrderItem(
            order_id=order.id,
            product_id=oi['product_id'],
            quantity=oi['quantity'],
            price_stars=oi['price_stars']
        ))

    db.session.commit()

    # Build description
    desc_lines = [f"{oi['quantity']}x item" for oi in order_items]
    description = f"Order #{order.id}: {', '.join(desc_lines[:5])}"
    if len(description) > 255:
        description = description[:252] + '...'

    # Send invoice via bot
    try:
        create_stars_invoice(
            chat_id=g.user.telegram_id,
            order_id=order.id,
            title=f"Magazilla Order #{order.id}",
            description=description,
            total_stars=total
        )
        return jsonify({'ok': True, 'order_id': order.id, 'total': total, 'method': 'invoice_sent'})
    except Exception as e:
        print(f"Invoice error: {e}")
        return jsonify({'ok': True, 'order_id': order.id, 'total': total, 'method': 'manual'})


# ─── Profile API ──────────────────────────────────────────────────
@app.route('/api/profile', methods=['GET'])
@api_auth_required
def api_profile():
    user = g.user
    orders = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).limit(20).all()
    return jsonify({
        'user': {
            'telegram_id': user.telegram_id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'photo_url': user.photo_url,
            'total_spent': user.total_spent,
            'is_admin': user.is_admin,
            'member_since': user.created_at.isoformat()
        },
        'orders': [{
            'id': o.id,
            'total_stars': o.total_stars,
            'status': o.status,
            'created_at': o.created_at.isoformat(),
            'items_count': len(o.items)
        } for o in orders]
    })


# ─── Admin Auth ───────────────────────────────────────────────────
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == Config.ADMIN_PASSWORD:
            session['is_admin'] = True
            session['admin_logged_in'] = True
            session.permanent = True
            return redirect(url_for('admin_dashboard'))
        return render_template('admin/login.html', error='Wrong password')
    return render_template('admin/login.html')


@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    session.pop('admin_logged_in', None)
    return redirect(url_for('shop'))


# ─── Admin Dashboard ──────────────────────────────────────────────
@app.route('/admin')
@admin_required
def admin_dashboard():
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    stats = {
        'total_products': Product.query.count(),
        'active_products': Product.query.filter_by(is_active=True).count(),
        'total_users': User.query.count(),
        'total_orders': Order.query.filter_by(status='paid').count(),
        'total_revenue': db.session.query(db.func.coalesce(db.func.sum(Order.total_stars), 0)).filter(Order.status == 'paid').scalar(),
        'today_visitors': VisitorLog.query.filter(VisitorLog.created_at >= today_start).distinct(VisitorLog.ip_address).count(),
        'week_orders': Order.query.filter(Order.status == 'paid', Order.created_at >= week_ago).count(),
        'week_revenue': db.session.query(db.func.coalesce(db.func.sum(Order.total_stars), 0)).filter(Order.status == 'paid', Order.created_at >= week_ago).scalar(),
        'month_visitors': VisitorLog.query.filter(VisitorLog.created_at >= month_ago).count(),
    }

    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()
    return render_template('admin/dashboard.html', stats=stats, recent_orders=recent_orders)


# ─── Admin Products ───────────────────────────────────────────────
@app.route('/admin/products')
@admin_required
def admin_products():
    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template('admin/products.html', products=products)


@app.route('/admin/products/new', methods=['GET', 'POST'])
@admin_required
def admin_product_new():
    categories = Category.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        product = Product(
            title=request.form['title'],
            description=request.form.get('description', ''),
            price_stars=int(request.form['price_stars']),
            category_id=int(request.form['category_id']) if request.form.get('category_id') else None,
            is_digital=bool(request.form.get('is_digital')),
            digital_content=request.form.get('digital_content', ''),
            stock=int(request.form.get('stock', -1)),
            is_active=bool(request.form.get('is_active')),
            is_featured=bool(request.form.get('is_featured')),
        )

        # Handle thumbnail upload
        thumb = request.files.get('thumbnail')
        if thumb and thumb.filename:
            product.thumbnail_url = r2.upload_file(thumb, folder='products/thumbnails')

        db.session.add(product)
        db.session.flush()

        # Handle gallery uploads
        gallery_files = request.files.getlist('gallery')
        for i, f in enumerate(gallery_files):
            if f and f.filename:
                url = r2.upload_file(f, folder='products/gallery')
                is_video = f.filename.lower().endswith('.webm')
                img = ProductImage(product_id=product.id, image_url=url, is_video=is_video, sort_order=i)
                db.session.add(img)

        db.session.commit()
        return redirect(url_for('admin_products'))

    return render_template('admin/product_form.html', product=None, categories=categories)


@app.route('/admin/products/<int:product_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_product_edit(product_id):
    product = Product.query.get_or_404(product_id)
    categories = Category.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        product.title = request.form['title']
        product.description = request.form.get('description', '')
        product.price_stars = int(request.form['price_stars'])
        product.category_id = int(request.form['category_id']) if request.form.get('category_id') else None
        product.is_digital = bool(request.form.get('is_digital'))
        product.digital_content = request.form.get('digital_content', '')
        product.stock = int(request.form.get('stock', -1))
        product.is_active = bool(request.form.get('is_active'))
        product.is_featured = bool(request.form.get('is_featured'))

        thumb = request.files.get('thumbnail')
        if thumb and thumb.filename:
            if product.thumbnail_url:
                r2.delete_file(product.thumbnail_url)
            product.thumbnail_url = r2.upload_file(thumb, folder='products/thumbnails')

        gallery_files = request.files.getlist('gallery')
        for i, f in enumerate(gallery_files):
            if f and f.filename:
                url = r2.upload_file(f, folder='products/gallery')
                is_video = f.filename.lower().endswith('.webm')
                max_sort = db.session.query(db.func.coalesce(db.func.max(ProductImage.sort_order), 0)).filter_by(product_id=product.id).scalar()
                img = ProductImage(product_id=product.id, image_url=url, is_video=is_video, sort_order=max_sort + 1 + i)
                db.session.add(img)

        db.session.commit()
        return redirect(url_for('admin_products'))

    gallery = ProductImage.query.filter_by(product_id=product.id).order_by(ProductImage.sort_order).all()
    return render_template('admin/product_form.html', product=product, categories=categories, gallery=gallery)


@app.route('/admin/products/<int:product_id>/delete', methods=['POST'])
@admin_required
def admin_product_delete(product_id):
    product = Product.query.get_or_404(product_id)
    if product.thumbnail_url:
        r2.delete_file(product.thumbnail_url)
    for img in product.gallery_images.all():
        r2.delete_file(img.image_url)
    db.session.delete(product)
    db.session.commit()
    return redirect(url_for('admin_products'))


@app.route('/admin/gallery/<int:image_id>/delete', methods=['POST'])
@admin_required
def admin_gallery_delete(image_id):
    img = ProductImage.query.get_or_404(image_id)
    r2.delete_file(img.image_url)
    product_id = img.product_id
    db.session.delete(img)
    db.session.commit()
    return redirect(url_for('admin_product_edit', product_id=product_id))


# ─── Admin Categories ─────────────────────────────────────────────
@app.route('/admin/categories')
@admin_required
def admin_categories():
    cats = Category.query.order_by(Category.sort_order).all()
    return render_template('admin/categories.html', categories=cats)


@app.route('/admin/categories/save', methods=['POST'])
@admin_required
def admin_category_save():
    cat_id = request.form.get('id')
    if cat_id:
        cat = Category.query.get_or_404(int(cat_id))
    else:
        cat = Category()
        db.session.add(cat)

    cat.name = request.form['name']
    cat.slug = request.form['slug'].lower().strip().replace(' ', '-')
    cat.icon = request.form.get('icon', '📦')
    cat.sort_order = int(request.form.get('sort_order', 0))
    cat.is_active = bool(request.form.get('is_active'))

    db.session.commit()
    return redirect(url_for('admin_categories'))


@app.route('/admin/categories/<int:cat_id>/delete', methods=['POST'])
@admin_required
def admin_category_delete(cat_id):
    cat = Category.query.get_or_404(cat_id)
    db.session.delete(cat)
    db.session.commit()
    return redirect(url_for('admin_categories'))


# ─── Admin Posts ───────────────────────────────────────────────────
@app.route('/admin/posts')
@admin_required
def admin_posts():
    posts = Post.query.order_by(Post.created_at.desc()).all()
    return render_template('admin/posts.html', posts=posts)


@app.route('/admin/posts/new', methods=['GET', 'POST'])
@admin_required
def admin_post_new():
    if request.method == 'POST':
        post = Post(
            title=request.form['title'],
            content=request.form.get('content', ''),
            is_published=bool(request.form.get('is_published')),
        )
        db.session.add(post)
        db.session.flush()

        gallery_files = request.files.getlist('gallery')
        for i, f in enumerate(gallery_files):
            if f and f.filename:
                url = r2.upload_file(f, folder='posts')
                is_video = f.filename.lower().endswith('.webm')
                img = PostImage(post_id=post.id, image_url=url, is_video=is_video, sort_order=i)
                db.session.add(img)

        db.session.commit()
        return redirect(url_for('admin_posts'))

    return render_template('admin/post_form.html', post=None)


@app.route('/admin/posts/<int:post_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_post_edit(post_id):
    post = Post.query.get_or_404(post_id)

    if request.method == 'POST':
        post.title = request.form['title']
        post.content = request.form.get('content', '')
        post.is_published = bool(request.form.get('is_published'))

        gallery_files = request.files.getlist('gallery')
        for i, f in enumerate(gallery_files):
            if f and f.filename:
                url = r2.upload_file(f, folder='posts')
                is_video = f.filename.lower().endswith('.webm')
                max_sort = db.session.query(db.func.coalesce(db.func.max(PostImage.sort_order), 0)).filter_by(post_id=post.id).scalar()
                img = PostImage(post_id=post.id, image_url=url, is_video=is_video, sort_order=max_sort + 1 + i)
                db.session.add(img)

        db.session.commit()
        return redirect(url_for('admin_posts'))

    images = PostImage.query.filter_by(post_id=post.id).order_by(PostImage.sort_order).all()
    return render_template('admin/post_form.html', post=post, images=images)


@app.route('/admin/posts/<int:post_id>/delete', methods=['POST'])
@admin_required
def admin_post_delete(post_id):
    post = Post.query.get_or_404(post_id)
    for img in post.images.all():
        r2.delete_file(img.image_url)
    db.session.delete(post)
    db.session.commit()
    return redirect(url_for('admin_posts'))


# ─── Admin Orders ─────────────────────────────────────────────────
@app.route('/admin/orders')
@admin_required
def admin_orders():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template('admin/orders.html', orders=orders)


@app.route('/admin/orders/<int:order_id>/refund', methods=['POST'])
@admin_required
def admin_order_refund(order_id):
    order = Order.query.get_or_404(order_id)
    if order.status == 'paid' and order.telegram_payment_id:
        try:
            bot.refund_payment(order.user.telegram_id, order.telegram_payment_id)
            order.status = 'refunded'
            user = User.query.get(order.user_id)
            if user:
                user.total_spent = max(0, (user.total_spent or 0) - order.total_stars)
            db.session.commit()
        except Exception as e:
            print(f"Refund error: {e}")
    return redirect(url_for('admin_orders'))


# ─── Admin Users ───────────────────────────────────────────────────
@app.route('/admin/users')
@admin_required
def admin_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)


# ─── Admin Stats API ──────────────────────────────────────────────
@app.route('/admin/api/stats/visitors')
@admin_required
def admin_api_visitor_stats():
    days = int(request.args.get('days', 7))
    now = datetime.utcnow()
    data = []
    for i in range(days - 1, -1, -1):
        day = (now - timedelta(days=i)).date()
        start = datetime.combine(day, datetime.min.time())
        end = datetime.combine(day, datetime.max.time())
        count = VisitorLog.query.filter(VisitorLog.created_at.between(start, end)).count()
        unique = db.session.query(db.func.count(db.distinct(VisitorLog.ip_address))).filter(
            VisitorLog.created_at.between(start, end)).scalar()
        data.append({'date': day.isoformat(), 'views': count, 'unique': unique})
    return jsonify(data)


# ─── Setup Webhook on Start ───────────────────────────────────────
@app.before_request
def setup_on_first_request():
    if not getattr(app, '_webhook_set', False):
        try:
            setup_webhook()
            app._webhook_set = True
        except Exception as e:
            print(f"Webhook setup error: {e}")
            app._webhook_set = True


# ─── Error Handlers ───────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Not found'}), 404
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Server error'}), 500
    return render_template('500.html'), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
