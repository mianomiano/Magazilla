import os
import json
import hmac
import hashlib
import time
from urllib.parse import parse_qs, unquote
from datetime import datetime
from functools import wraps

from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

from config import Config
from models import db, User, Category, Product, ProductImage, CartItem, Order, OrderItem, Post, PostImage

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

with app.app_context():
    db.create_all()
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


# ─── Telegram initData Validation ────────────────────────

def validate_init_data(init_data_raw, bot_token):
    """Validate Telegram Mini App initData using HMAC-SHA256."""
    try:
        parsed = parse_qs(init_data_raw, keep_blank_values=True)

        if 'hash' not in parsed:
            return None

        received_hash = parsed.pop('hash')[0]

        data_check_parts = []
        for key in sorted(parsed.keys()):
            val = parsed[key][0]
            data_check_parts.append(f"{key}={val}")
        data_check_string = "\n".join(data_check_parts)

        secret_key = hmac.new(
            b"WebAppData",
            bot_token.encode('utf-8'),
            hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(calculated_hash, received_hash):
            return None

        auth_date = parsed.get('auth_date', [None])[0]
        if auth_date:
            if time.time() - int(auth_date) > 86400:
                return None

        user_data_raw = parsed.get('user', [None])[0]
        if not user_data_raw:
            return None

        user_data = json.loads(unquote(user_data_raw) if '%' in user_data_raw else user_data_raw)
        return user_data
    except Exception as e:
        app.logger.error(f"initData validation error: {e}")
        return None


def extract_user_from_init_data(init_data_raw):
    """Extract user WITHOUT validation (fallback for development)."""
    try:
        parsed = parse_qs(init_data_raw, keep_blank_values=True)
        user_data_raw = parsed.get('user', [None])[0]
        if not user_data_raw:
            return None
        user_data = json.loads(unquote(user_data_raw) if '%' in user_data_raw else user_data_raw)
        if user_data.get('id'):
            return user_data
        return None
    except:
        return None


def get_or_create_user(user_data):
    """Get existing user or create new one from Telegram user data."""
    telegram_id = user_data.get('id')
    if not telegram_id:
        return None

    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        user = User(
            telegram_id=telegram_id,
            first_name=user_data.get('first_name', ''),
            last_name=user_data.get('last_name', ''),
            username=user_data.get('username', ''),
            photo_url=user_data.get('photo_url', ''),
        )
        db.session.add(user)
        db.session.commit()
    else:
        user.first_name = user_data.get('first_name', user.first_name)
        user.last_name = user_data.get('last_name', user.last_name)
        user.username = user_data.get('username', user.username)
        user.photo_url = user_data.get('photo_url', user.photo_url)
        user.last_visit = datetime.utcnow()
        db.session.commit()

    return user


def require_telegram_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        from flask import g
        init_data = request.headers.get('X-Telegram-Init-Data', '')

        if not init_data:
            return jsonify({'error': 'No auth data'}), 401

        user_data = validate_init_data(init_data, Config.BOT_TOKEN)

        if not user_data:
            user_data = extract_user_from_init_data(init_data)

        if not user_data:
            return jsonify({'error': 'Invalid auth data'}), 401

        user = get_or_create_user(user_data)
        if not user:
            return jsonify({'error': 'Could not create user'}), 401

        g.user = user
        return f(*args, **kwargs)
    return decorated


def is_admin_user(user):
    admin_ids = Config.ADMIN_TELEGRAM_IDS
    if not admin_ids:
        return False
    id_list = [int(x.strip()) for x in str(admin_ids).split(',') if x.strip()]
    return user.telegram_id in id_list


def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('is_admin'):
            return f(*args, **kwargs)
        if session.get('admin_telegram_id'):
            return f(*args, **kwargs)
        return redirect(url_for('admin_login'))
    return decorated


# ─── Auth Endpoint ───────────────────────────────────────

@app.route('/auth', methods=['POST'])
def auth():
    data = request.get_json()
    if not data or not data.get('initData'):
        return jsonify({'ok': False, 'error': 'No initData'}), 400

    init_data = data['initData']

    user_data = validate_init_data(init_data, Config.BOT_TOKEN)
    if not user_data:
        user_data = extract_user_from_init_data(init_data)

    if not user_data:
        return jsonify({'ok': False, 'error': 'Invalid initData'}), 401

    user = get_or_create_user(user_data)
    if not user:
        return jsonify({'ok': False, 'error': 'Could not create user'}), 500

    session['telegram_id'] = user.telegram_id

    if is_admin_user(user):
        session['admin_telegram_id'] = user.telegram_id

    return jsonify({
        'ok': True,
        'user': {
            'id': user.telegram_id,
            'first_name': user.first_name,
            'is_admin': is_admin_user(user)
        }
    })


# ─── Shop Pages ─────────────────────────────────────────

@app.route('/')
@app.route('/shop')
def shop():
    categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()

    cat_slug = request.args.get('category', '')

    query = Product.query.filter_by(is_active=True)
    if cat_slug:
        cat = Category.query.filter_by(slug=cat_slug).first()
        if cat:
            query = query.filter_by(category_id=cat.id)

    products = query.order_by(Product.created_at.desc()).all()
    featured = Product.query.filter_by(is_active=True, is_featured=True).limit(6).all()

    return render_template('shop.html',
                           categories=categories,
                           products=products,
                           featured=featured,
                           current_category=cat_slug)


@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    if not product.is_active:
        abort(404)
    gallery = ProductImage.query.filter_by(product_id=product.id).order_by(ProductImage.sort_order).all()
    related = Product.query.filter(
        Product.category_id == product.category_id,
        Product.id != product.id,
        Product.is_active == True
    ).limit(4).all()
    return render_template('product_detail.html', product=product, gallery=gallery, related=related)


@app.route('/cart')
def cart_page():
    return render_template('cart.html')


@app.route('/profile')
def profile_page():
    return render_template('profile.html')


# ─── Posts Pages ─────────────────────────────────────────

@app.route('/posts')
def posts_list():
    posts = Post.query.filter_by(is_published=True).order_by(Post.created_at.desc()).all()
    return render_template('posts.html', posts=posts)


@app.route('/post/<int:post_id>')
def post_detail(post_id):
    post = Post.query.get_or_404(post_id)
    if not post.is_published:
        abort(404)
    post.views += 1
    db.session.commit()
    gallery = PostImage.query.filter_by(post_id=post.id).order_by(PostImage.sort_order).all()
    return render_template('post_detail.html', post=post, gallery=gallery)


# ─── Cart API ────────────────────────────────────────────

@app.route('/api/cart', methods=['GET'])
@require_telegram_auth
def api_cart():
    from flask import g
    items = CartItem.query.filter_by(user_id=g.user.id).all()
    result = []
    total = 0
    for item in items:
        product = Product.query.get(item.product_id)
        if not product:
            continue
        subtotal = product.price_stars * item.quantity
        total += subtotal
        result.append({
            'id': item.id,
            'product_id': product.id,
            'title': product.title,
            'price_stars': product.price_stars,
            'quantity': item.quantity,
            'subtotal': subtotal,
            'thumbnail_url': product.thumbnail_url or ''
        })
    return jsonify({'items': result, 'total': total, 'count': len(result)})


@app.route('/api/cart/add', methods=['POST'])
@require_telegram_auth
def api_cart_add():
    from flask import g
    data = request.get_json()
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)

    product = Product.query.get(product_id)
    if not product or not product.is_active:
        return jsonify({'ok': False, 'error': 'Product not found'}), 404

    if not product.in_stock:
        return jsonify({'ok': False, 'error': 'Out of stock'}), 400

    existing = CartItem.query.filter_by(user_id=g.user.id, product_id=product_id).first()
    if existing:
        existing.quantity += quantity
    else:
        item = CartItem(user_id=g.user.id, product_id=product_id, quantity=quantity)
        db.session.add(item)

    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/cart/update', methods=['POST'])
@require_telegram_auth
def api_cart_update():
    from flask import g
    data = request.get_json()
    item_id = data.get('item_id')
    quantity = data.get('quantity', 1)

    item = CartItem.query.filter_by(id=item_id, user_id=g.user.id).first()
    if not item:
        return jsonify({'ok': False, 'error': 'Item not found'}), 404

    if quantity <= 0:
        db.session.delete(item)
    else:
        item.quantity = quantity

    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/cart/remove', methods=['POST'])
@require_telegram_auth
def api_cart_remove():
    from flask import g
    data = request.get_json()
    item_id = data.get('item_id')

    item = CartItem.query.filter_by(id=item_id, user_id=g.user.id).first()
    if item:
        db.session.delete(item)
        db.session.commit()

    return jsonify({'ok': True})


# ─── Profile API ─────────────────────────────────────────

@app.route('/api/profile', methods=['GET'])
@require_telegram_auth
def api_profile():
    from flask import g
    user = g.user

    orders = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).all()
    orders_data = []
    for o in orders:
        items_count = OrderItem.query.filter_by(order_id=o.id).count()
        orders_data.append({
            'id': o.id,
            'status': o.status,
            'total_stars': o.total_stars,
            'items_count': items_count,
            'created_at': o.created_at.isoformat() if o.created_at else ''
        })

    total_spent = user.total_spent or 0

    return jsonify({
        'user': {
            'first_name': user.first_name,
            'last_name': user.last_name,
            'username': user.username,
            'photo_url': user.photo_url,
            'total_spent': total_spent,
            'member_since': user.created_at.isoformat() if user.created_at else ''
        },
        'orders': orders_data
    })


# ─── Checkout API ────────────────────────────────────────

@app.route('/api/checkout', methods=['POST'])
@require_telegram_auth
def api_checkout():
    from flask import g
    user = g.user

    items = CartItem.query.filter_by(user_id=user.id).all()
    if not items:
        return jsonify({'ok': False, 'error': 'Cart is empty'}), 400

    total = 0
    order_items_data = []
    for item in items:
        product = Product.query.get(item.product_id)
        if not product or not product.is_active:
            continue
        subtotal = product.price_stars * item.quantity
        total += subtotal
        order_items_data.append({
            'product': product,
            'quantity': item.quantity,
            'price_stars': product.price_stars
        })

    if not order_items_data:
        return jsonify({'ok': False, 'error': 'No valid items'}), 400

    order = Order(
        user_id=user.id,
        total_stars=total,
        status='pending'
    )
    db.session.add(order)
    db.session.flush()

    for oi in order_items_data:
        db.session.add(OrderItem(
            order_id=order.id,
            product_id=oi['product'].id,
            quantity=oi['quantity'],
            price_stars=oi['price_stars']
        ))

    CartItem.query.filter_by(user_id=user.id).delete()
    db.session.commit()

    # Send Telegram Stars invoice
    try:
        import requests as http_requests
        title_parts = [oi['product'].title for oi in order_items_data[:3]]
        title = "Order #" + str(order.id)
        description = ", ".join(title_parts)
        if len(order_items_data) > 3:
            description += f" +{len(order_items_data) - 3} more"

        payload = json.dumps({'order_id': order.id})

        resp = http_requests.post(
            f"https://api.telegram.org/bot{Config.BOT_TOKEN}/sendInvoice",
            json={
                'chat_id': user.telegram_id,
                'title': title,
                'description': description,
                'payload': payload,
                'currency': 'XTR',
                'prices': [{'label': 'Total', 'amount': total}]
            },
            timeout=10
        )

        if resp.ok:
            return jsonify({'ok': True, 'method': 'invoice_sent', 'order_id': order.id})
        else:
            app.logger.error(f"Invoice send failed: {resp.text}")
    except Exception as e:
        app.logger.error(f"Invoice error: {e}")

    return jsonify({'ok': True, 'method': 'order_created', 'order_id': order.id})


# ─── Telegram Bot Webhook ────────────────────────────────

@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    data = request.get_json()
    if not data:
        return 'ok'

    # Handle pre_checkout_query
    pcq = data.get('pre_checkout_query')
    if pcq:
        try:
            import requests as http_requests
            http_requests.post(
                f"https://api.telegram.org/bot{Config.BOT_TOKEN}/answerPreCheckoutQuery",
                json={'pre_checkout_query_id': pcq['id'], 'ok': True},
                timeout=10
            )
        except:
            pass
        return 'ok'

    # Handle successful_payment
    msg = data.get('message', {})
    sp = msg.get('successful_payment')
    if sp:
        try:
            payload = json.loads(sp.get('invoice_payload', '{}'))
            order_id = payload.get('order_id')
            if order_id:
                order = Order.query.get(order_id)
                if order:
                    order.status = 'paid'
                    order.paid_at = datetime.utcnow()
                    order.telegram_payment_id = sp.get('telegram_payment_charge_id', '')

                    # Update user total_spent
                    user = User.query.get(order.user_id)
                    if user:
                        user.total_spent = (user.total_spent or 0) + order.total_stars

                    # Decrease stock
                    for oi in order.items:
                        product = Product.query.get(oi.product_id)
                        if product and product.stock > 0:
                            product.stock -= oi.quantity
                            product.purchases += oi.quantity

                    db.session.commit()

                    import requests as http_requests
                    http_requests.post(
                        f"https://api.telegram.org/bot{Config.BOT_TOKEN}/sendMessage",
                        json={
                            'chat_id': msg['from']['id'],
                            'text': f"✅ Payment received! Order #{order_id} confirmed.\n\nThank you! ⭐"
                        },
                        timeout=10
                    )
        except Exception as e:
            app.logger.error(f"Payment processing error: {e}")
        return 'ok'

    # Handle /start command
    text = msg.get('text', '')
    if text.startswith('/start'):
        try:
            import requests as http_requests
            chat_id = msg['from']['id']

            from_user = msg.get('from', {})
            get_or_create_user({
                'id': from_user.get('id'),
                'first_name': from_user.get('first_name', ''),
                'last_name': from_user.get('last_name', ''),
                'username': from_user.get('username', ''),
            })

            webapp_url = Config.APP_URL + '/shop'
            http_requests.post(
                f"https://api.telegram.org/bot{Config.BOT_TOKEN}/sendMessage",
                json={
                    'chat_id': chat_id,
                    'text': "👋 Welcome to **Magazilla**!\n\nTap the button below to open our shop:",
                    'parse_mode': 'Markdown',
                    'reply_markup': {
                        'inline_keyboard': [[{
                            'text': '🏪 Open Shop',
                            'web_app': {'url': webapp_url}
                        }]]
                    }
                },
                timeout=10
            )
        except:
            pass
        return 'ok'

    return 'ok'


# ─── Admin Login ─────────────────────────────────────────

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('is_admin') or session.get('admin_telegram_id'):
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == Config.ADMIN_PASSWORD:
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))
        flash('Invalid password', 'error')

    return render_template('admin/login.html')


@app.route('/admin/tg-login')
def admin_tg_login():
    if session.get('admin_telegram_id'):
        return redirect(url_for('admin_dashboard'))

    tid = session.get('telegram_id')
    if tid:
        admin_ids = Config.ADMIN_TELEGRAM_IDS
        if isinstance(admin_ids, list):
            id_list = admin_ids
        else:
            id_list = [int(x.strip()) for x in str(admin_ids).split(',') if x.strip()]
        if tid in id_list:
            session['admin_telegram_id'] = tid
            return redirect(url_for('admin_dashboard'))

    flash('You are not an admin or not authenticated via Telegram', 'error')
    return redirect(url_for('admin_login'))



# ─── Admin Dashboard ─────────────────────────────────────

@app.route('/admin')
@require_admin
def admin_dashboard():
    products_count = Product.query.filter_by(is_active=True).count()
    users_count = User.query.count()
    orders_count = Order.query.count()
    revenue = db.session.query(db.func.sum(Order.total_stars)).filter_by(status='paid').scalar() or 0
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()
    
    return render_template('admin/dashboard.html',
                           products_count=products_count,
                           users_count=users_count,
                           orders_count=orders_count,
                           revenue=revenue,
                           recent_orders=recent_orders)


# ─── Admin Products ──────────────────────────────────────

@app.route('/admin/products')
@require_admin
def admin_products():
    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template('admin/products.html', products=products)


@app.route('/admin/products/new', methods=['GET', 'POST'])
@require_admin
def admin_product_new():
    categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()

    if request.method == 'POST':
        stock_val = request.form.get('stock', '-1').strip()
        stock = int(stock_val) if stock_val else -1

        product = Product(
            title=request.form.get('title', '').strip(),
            description=request.form.get('description', '').strip(),
            price_stars=int(request.form.get('price_stars', 0)),
            category_id=int(request.form.get('category_id', 0)) or None,
            thumbnail_url=request.form.get('thumbnail_url', '').strip(),
            digital_content=request.form.get('digital_content', '').strip(),
            stock=stock,
            is_active=bool(request.form.get('is_active')),
            is_featured=bool(request.form.get('is_featured'))
        )

        db.session.add(product)
        db.session.flush()

        # Gallery images (one URL per line)
        gallery_urls = request.form.get('gallery_urls', '').strip().split('\n')
        for i, url in enumerate(gallery_urls):
            url = url.strip()
            if url:
                is_video = any(url.lower().endswith(ext) for ext in ['.mp4', '.webm', '.mov'])
                db.session.add(ProductImage(
                    product_id=product.id,
                    image_url=url,
                    is_video=is_video,
                    sort_order=i
                ))

        db.session.commit()
        flash('Product created!', 'success')
        return redirect(url_for('admin_products'))

    return render_template('admin/product_form.html', product=None, categories=categories, gallery_urls='')


@app.route('/admin/products/<int:product_id>/edit', methods=['GET', 'POST'])
@require_admin
def admin_product_edit(product_id):
    product = Product.query.get_or_404(product_id)
    categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()

    if request.method == 'POST':
        product.title = request.form.get('title', '').strip()
        product.description = request.form.get('description', '').strip()
        product.price_stars = int(request.form.get('price_stars', 0))
        product.category_id = int(request.form.get('category_id', 0)) or None
        product.thumbnail_url = request.form.get('thumbnail_url', '').strip()
        product.digital_content = request.form.get('digital_content', '').strip()
        stock_val = request.form.get('stock', '-1').strip()
        product.stock = int(stock_val) if stock_val else -1
        product.is_active = bool(request.form.get('is_active'))
        product.is_featured = bool(request.form.get('is_featured'))

        # Update gallery
        ProductImage.query.filter_by(product_id=product.id).delete()
        gallery_urls = request.form.get('gallery_urls', '').strip().split('\n')
        for i, url in enumerate(gallery_urls):
            url = url.strip()
            if url:
                is_video = any(url.lower().endswith(ext) for ext in ['.mp4', '.webm', '.mov'])
                db.session.add(ProductImage(
                    product_id=product.id,
                    image_url=url,
                    is_video=is_video,
                    sort_order=i
                ))

        db.session.commit()
        flash('Product updated!', 'success')
        return redirect(url_for('admin_products'))

    gallery = ProductImage.query.filter_by(product_id=product.id).order_by(ProductImage.sort_order).all()
    gallery_urls = '\n'.join([img.image_url for img in gallery])

    return render_template('admin/product_form.html', product=product, categories=categories, gallery_urls=gallery_urls)


@app.route('/admin/products/<int:product_id>/delete', methods=['POST'])
@require_admin
def admin_product_delete(product_id):
    product = Product.query.get_or_404(product_id)
    ProductImage.query.filter_by(product_id=product.id).delete()
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted', 'success')
    return redirect(url_for('admin_products'))


# ─── Admin Categories ────────────────────────────────────

@app.route('/admin/categories')
@require_admin
def admin_categories():
    categories = Category.query.order_by(Category.sort_order).all()
    return render_template('admin/categories.html', categories=categories)


@app.route('/admin/categories/save', methods=['POST'])
@require_admin
def admin_category_save():
    cat_id = request.form.get('cat_id', '')
    name = request.form.get('name', '').strip()
    slug = request.form.get('slug', '').strip()
    icon = request.form.get('icon', '📦').strip()
    sort_order = int(request.form.get('sort_order', 0))
    is_active = bool(request.form.get('is_active'))

    if cat_id:
        cat = Category.query.get(int(cat_id))
        if cat:
            cat.name = name
            cat.slug = slug
            cat.icon = icon
            cat.sort_order = sort_order
            cat.is_active = is_active
    else:
        cat = Category(name=name, slug=slug, icon=icon, sort_order=sort_order, is_active=is_active)
        db.session.add(cat)

    db.session.commit()
    flash('Category saved!', 'success')
    return redirect(url_for('admin_categories'))


@app.route('/admin/categories/<int:cat_id>/delete', methods=['POST'])
@require_admin
def admin_category_delete(cat_id):
    cat = Category.query.get_or_404(cat_id)
    db.session.delete(cat)
    db.session.commit()
    flash('Category deleted', 'success')
    return redirect(url_for('admin_categories'))


# ─── Admin Orders ─────────────────────────────────────────

@app.route('/admin/orders')
@require_admin
def admin_orders():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template('admin/orders.html', orders=orders)


@app.route('/admin/orders/<int:order_id>')
@require_admin
def admin_order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    items = OrderItem.query.filter_by(order_id=order.id).all()
    user = User.query.get(order.user_id)
    return render_template('admin/order_detail.html', order=order, items=items, user=user)


# ─── Admin Posts ──────────────────────────────────────────

@app.route('/admin/posts')
@require_admin
def admin_posts():
    posts = Post.query.order_by(Post.created_at.desc()).all()
    return render_template('admin/posts.html', posts=posts)


@app.route('/admin/posts/new', methods=['GET', 'POST'])
@require_admin
def admin_post_new():
    if request.method == 'POST':
        post = Post(
            title=request.form.get('title', '').strip(),
            content=request.form.get('content', '').strip(),
            is_published=bool(request.form.get('is_published'))
        )
        db.session.add(post)
        db.session.flush()

        image_urls = request.form.get('image_urls', '').strip().split('\n')
        for i, url in enumerate(image_urls):
            url = url.strip()
            if url:
                is_video = any(url.lower().endswith(ext) for ext in ['.mp4', '.webm', '.mov'])
                db.session.add(PostImage(
                    post_id=post.id,
                    image_url=url,
                    is_video=is_video,
                    sort_order=i
                ))

        db.session.commit()
        flash('Post created!', 'success')
        return redirect(url_for('admin_posts'))

    return render_template('admin/post_form.html', post=None, image_urls='')


@app.route('/admin/posts/<int:post_id>/edit', methods=['GET', 'POST'])
@require_admin
def admin_post_edit(post_id):
    post = Post.query.get_or_404(post_id)

    if request.method == 'POST':
        post.title = request.form.get('title', '').strip()
        post.content = request.form.get('content', '').strip()
        post.is_published = bool(request.form.get('is_published'))

        PostImage.query.filter_by(post_id=post.id).delete()
        image_urls = request.form.get('image_urls', '').strip().split('\n')
        for i, url in enumerate(image_urls):
            url = url.strip()
            if url:
                is_video = any(url.lower().endswith(ext) for ext in ['.mp4', '.webm', '.mov'])
                db.session.add(PostImage(
                    post_id=post.id,
                    image_url=url,
                    is_video=is_video,
                    sort_order=i
                ))

        db.session.commit()
        flash('Post updated!', 'success')
        return redirect(url_for('admin_posts'))

    images = PostImage.query.filter_by(post_id=post.id).order_by(PostImage.sort_order).all()
    image_urls = '\n'.join([img.image_url for img in images])

    return render_template('admin/post_form.html', post=post, image_urls=image_urls)


@app.route('/admin/posts/<int:post_id>/delete', methods=['POST'])
@require_admin
def admin_post_delete(post_id):
    post = Post.query.get_or_404(post_id)
    PostImage.query.filter_by(post_id=post.id).delete()
    db.session.delete(post)
    db.session.commit()
    flash('Post deleted', 'success')
    return redirect(url_for('admin_posts'))


# ─── Admin Users ──────────────────────────────────────────

@app.route('/admin/users')
@require_admin
def is_admin_user(user):
    admin_ids = Config.ADMIN_TELEGRAM_IDS
    if not admin_ids:
        return False
    # Handle both list and string formats
    if isinstance(admin_ids, list):
        return user.telegram_id in admin_ids
    id_list = [int(x.strip()) for x in str(admin_ids).split(',') if x.strip()]
    return user.telegram_id in id_list



# ─── Setup Webhook ────────────────────────────────────────

@app.route('/setup-webhook')
def setup_webhook():
    import requests as http_requests
    webhook_url = Config.APP_URL + '/webhook'
    resp = http_requests.post(
        f"https://api.telegram.org/bot{Config.BOT_TOKEN}/setWebhook",
        json={'url': webhook_url},
        timeout=10
    )
    return jsonify(resp.json())


# ─── Error Handlers ──────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500


# ─── Run ─────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(debug=True, port=5000)
