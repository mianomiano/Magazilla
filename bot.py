import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs, unquote

from telebot import TeleBot, types
from config import Config
from models import db, User, Order, OrderItem, Product

bot = TeleBot(Config.BOT_TOKEN, threaded=False)


# ─── Telegram WebApp Data Validation ───────────────────────────────
def validate_webapp_data(init_data_raw):
    """
    Validate Telegram Mini App initData.
    Returns parsed user data dict or None if invalid.
    """
    try:
        parsed = parse_qs(init_data_raw)
        
        check_hash = parsed.get('hash', [None])[0]
        if not check_hash:
            return None
        
        # Build data-check-string
        data_pairs = []
        for key, values in parsed.items():
            if key == 'hash':
                continue
            data_pairs.append(f"{key}={values[0]}")
        
        data_pairs.sort()
        data_check_string = '\n'.join(data_pairs)
        
        # Compute secret key
        secret_key = hmac.new(
            b'WebAppData',
            Config.BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()
        
        # Compute hash
        computed_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if computed_hash != check_hash:
            return None
        
        # Check auth_date (allow 24 hours)
        auth_date = int(parsed.get('auth_date', [0])[0])
        if time.time() - auth_date > 86400:
            return None
        
        # Parse user
        user_json = parsed.get('user', [None])[0]
        if user_json:
            user_data = json.loads(unquote(user_json))
            return user_data
        
        return None
    except Exception as e:
        print(f"WebApp validation error: {e}")
        return None


def get_or_create_user(telegram_id, username=None, first_name=None, last_name=None, photo_url=None):
    """Get existing user or create new one."""
    user = User.query.filter_by(telegram_id=telegram_id).first()
    
    if not user:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            photo_url=photo_url,
            is_admin=(telegram_id in Config.ADMIN_TELEGRAM_IDS)
        )
        db.session.add(user)
        db.session.commit()
    else:
        # Update info
        changed = False
        if username and user.username != username:
            user.username = username
            changed = True
        if first_name and user.first_name != first_name:
            user.first_name = first_name
            changed = True
        if last_name and user.last_name != last_name:
            user.last_name = last_name
            changed = True
        if photo_url and user.photo_url != photo_url:
            user.photo_url = photo_url
            changed = True
        if telegram_id in Config.ADMIN_TELEGRAM_IDS and not user.is_admin:
            user.is_admin = True
            changed = True
        if changed:
            from datetime import datetime
            user.last_visit = datetime.utcnow()
            db.session.commit()
    
    return user


# ─── Bot Commands ──────────────────────────────────────────────────
@bot.message_handler(commands=['start'])
def cmd_start(message):
    """Send welcome message with Mini App button."""
    webapp_url = f"{Config.APP_URL}/shop"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(
            text="🛍 Open Shop",
            web_app=types.WebAppInfo(url=webapp_url)
        )
    )
    markup.add(
        types.InlineKeyboardButton(
            text="👤 My Profile",
            web_app=types.WebAppInfo(url=f"{Config.APP_URL}/profile")
        )
    )
    
    # Register user
    user = message.from_user
    get_or_create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    bot.send_message(
        message.chat.id,
        f"✨ Welcome to **Magazilla**!\n\n"
        f"🛍 Browse our shop and pay with ⭐ Telegram Stars\n\n"
        f"Tap the button below to start shopping:",
        parse_mode='Markdown',
        reply_markup=markup
    )


@bot.message_handler(commands=['shop'])
def cmd_shop(message):
    """Open shop directly."""
    webapp_url = f"{Config.APP_URL}/shop"
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(
            text="🛍 Open Shop",
            web_app=types.WebAppInfo(url=webapp_url)
        )
    )
    bot.send_message(message.chat.id, "🛍 Tap to open the shop:", reply_markup=markup)


@bot.message_handler(commands=['profile'])
def cmd_profile(message):
    """Open user profile."""
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(
            text="👤 My Profile",
            web_app=types.WebAppInfo(url=f"{Config.APP_URL}/profile")
        )
    )
    bot.send_message(message.chat.id, "👤 Your profile:", reply_markup=markup)


@bot.message_handler(commands=['admin'])
def cmd_admin(message):
    """Admin panel link (only for admins)."""
    if message.from_user.id not in Config.ADMIN_TELEGRAM_IDS:
        bot.send_message(message.chat.id, "⛔ Access denied.")
        return
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(
            text="⚙️ Admin Dashboard",
            web_app=types.WebAppInfo(url=f"{Config.APP_URL}/admin")
        )
    )
    bot.send_message(message.chat.id, "⚙️ Admin panel:", reply_markup=markup)


# ─── Telegram Stars Payment ───────────────────────────────────────
def create_stars_invoice(chat_id, order_id, title, description, total_stars):
    """
    Send a Telegram Stars invoice to the user.
    """
    prices = [types.LabeledPrice(label=title, amount=total_stars)]
    
    bot.send_invoice(
        chat_id=chat_id,
        title=title,
        description=description,
        invoice_payload=f"order_{order_id}",
        provider_token="",  # Empty string for Telegram Stars
        currency="XTR",  # XTR = Telegram Stars
        prices=prices,
    )


@bot.pre_checkout_query_handler(func=lambda query: True)
def handle_pre_checkout(pre_checkout_query):
    """
    Telegram sends this before completing payment.
    We validate the order exists and is still valid.
    """
    try:
        payload = pre_checkout_query.invoice_payload
        
        if not payload.startswith('order_'):
            bot.answer_pre_checkout_query(pre_checkout_query.id, ok=False, error_message="Invalid order.")
            return
        
        order_id = int(payload.replace('order_', ''))
        order = Order.query.get(order_id)
        
        if not order:
            bot.answer_pre_checkout_query(pre_checkout_query.id, ok=False, error_message="Order not found.")
            return
        
        if order.status != 'pending':
            bot.answer_pre_checkout_query(pre_checkout_query.id, ok=False, error_message="Order already processed.")
            return
        
        # Check stock for all items
        for item in order.items:
            product = Product.query.get(item.product_id)
            if product and product.stock != -1 and product.stock < item.quantity:
                bot.answer_pre_checkout_query(
                    pre_checkout_query.id, ok=False,
                    error_message=f"'{product.title}' is out of stock."
                )
                return
        
        # All good
        bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
        
    except Exception as e:
        print(f"Pre-checkout error: {e}")
        bot.answer_pre_checkout_query(pre_checkout_query.id, ok=False, error_message="Server error. Try again.")


@bot.message_handler(content_types=['successful_payment'])
def handle_successful_payment(message):
    """
    Called after successful Telegram Stars payment.
    """
    from datetime import datetime
    
    try:
        payment = message.successful_payment
        payload = payment.invoice_payload
        
        if not payload.startswith('order_'):
            return
        
        order_id = int(payload.replace('order_', ''))
        order = Order.query.get(order_id)
        
        if not order:
            return
        
        # Update order
        order.status = 'paid'
        order.telegram_payment_id = payment.telegram_payment_charge_id
        order.paid_at = datetime.utcnow()
        
        # Update user total spent
        user = User.query.get(order.user_id)
        if user:
            user.total_spent = (user.total_spent or 0) + order.total_stars
        
        # Update product stats and stock
        for item in order.items:
            product = Product.query.get(item.product_id)
            if product:
                product.purchases = (product.purchases or 0) + item.quantity
                if product.stock > 0:
                    product.stock = max(0, product.stock - item.quantity)
        
        # Clear user's cart
        from models import CartItem
        CartItem.query.filter_by(user_id=order.user_id).delete()
        
        db.session.commit()
        
        # Send confirmation
        bot.send_message(
            message.chat.id,
            f"✅ **Payment successful!**\n\n"
            f"Order #{order.id}\n"
            f"Amount: ⭐ {order.total_stars} Stars\n\n"
            f"Thank you for your purchase! 🎉",
            parse_mode='Markdown'
        )
        
        # If digital products, send content
        for item in order.items:
            product = Product.query.get(item.product_id)
            if product and product.is_digital and product.digital_content:
                bot.send_message(
                    message.chat.id,
                    f"📦 **{product.title}**\n\n{product.digital_content}",
                    parse_mode='Markdown'
                )
        
        # Notify admin
        for admin_id in Config.ADMIN_TELEGRAM_IDS:
            try:
                bot.send_message(
                    admin_id,
                    f"💰 **New Order Paid!**\n\n"
                    f"Order #{order.id}\n"
                    f"User: @{user.username or 'N/A'} ({user.telegram_id})\n"
                    f"Amount: ⭐ {order.total_stars} Stars\n"
                    f"Items: {len(order.items)}",
                    parse_mode='Markdown'
                )
            except:
                pass
    
    except Exception as e:
        print(f"Payment processing error: {e}")


def setup_webhook():
    """Set up Telegram webhook."""
    bot.remove_webhook()
    time.sleep(0.5)
    result = bot.set_webhook(url=Config.WEBHOOK_URL)
    print(f"Webhook set: {result} -> {Config.WEBHOOK_URL}")
    return result


def process_webhook_update(update_json):
    """Process incoming webhook update."""
    update = types.Update.de_json(update_json)
    bot.process_new_updates([update])
