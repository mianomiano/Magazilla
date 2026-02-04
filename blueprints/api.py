"""API routes with rate limiting and Telegram auth validation"""
from flask import Blueprint, request, jsonify
from config import Config
from models import db, Product, Purchase
from utils.decorators import limiter
from utils.telegram_auth import telegram_auth_required, get_telegram_user_id, validate_telegram_init_data
import requests
import json

api_bp = Blueprint('api_bp', __name__)


@api_bp.route('/product/<int:pid>')
@limiter.limit("30 per minute")
def get_product(pid):
    """Get product details - public endpoint"""
    product = Product.query.get_or_404(pid)
    return jsonify(product.to_dict())


@api_bp.route('/create-invoice-link', methods=['POST'])
@limiter.limit("10 per minute")
@telegram_auth_required
def create_invoice():
    """Create Telegram Stars invoice - requires Telegram auth"""
    try:
        data = request.json
        product_id = data.get('product_id')
        
        if not product_id:
            return jsonify({'error': 'product_id required'}), 400
        
        product = Product.query.get(product_id)
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        if product.is_free:
            return jsonify({'error': 'Product is free'}), 400
        
        bot_token = Config.BOT_TOKEN
        url = f"https://api.telegram.org/bot{bot_token}/createInvoiceLink"
        
        # Include user_id in payload for tracking
        user_id = get_telegram_user_id()
        
        payload = {
            'title': product.name[:32],
            'description': (product.description or product.name)[:255],
            'payload': json.dumps({
                'product_id': product.id,
                'user_id': user_id
            }),
            'provider_token': '',
            'currency': 'XTR',
            'prices': json.dumps([{
                'label': product.name[:64],
                'amount': product.price
            }])
        }
        
        response = requests.post(url, data=payload, timeout=10)
        result = response.json()
        
        if result.get('ok'):
            return jsonify({'invoice_link': result['result']})
        else:
            return jsonify({
                'error': result.get('description', 'Failed to create invoice')
            }), 400
    
    except Exception as e:
        print(f"Invoice creation error: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@api_bp.route('/webhook/telegram', methods=['POST'])
def telegram_webhook():
    """Telegram webhook - verified by Telegram's servers"""
    try:
        update = request.json
        
        if 'message' in update and 'successful_payment' in update['message']:
            message = update['message']
            payment = message['successful_payment']
            user_id = message['from']['id']
            
            # Parse payload
            payload_str = payment.get('invoice_payload', '')
            try:
                payload = json.loads(payload_str)
                product_id = payload.get('product_id')
            except json.JSONDecodeError:
                # Fallback for old format
                if payload_str.startswith('product_'):
                    product_id = int(payload_str.split('_')[1])
                else:
                    return jsonify({'ok': True})
            
            if not product_id:
                return jsonify({'ok': True})
            
            product = Product.query.get(product_id)
            if not product:
                return jsonify({'ok': True})
            
            # Prevent duplicate purchases
            existing = Purchase.query.filter_by(
                telegram_payment_id=payment['telegram_payment_charge_id']
            ).first()
            
            if existing:
                return jsonify({'ok': True})
            
            purchase = Purchase(
                user_id=user_id,
                product_id=product_id,
                telegram_payment_id=payment['telegram_payment_charge_id'],
                stars_paid=payment['total_amount'],
                is_verified=True,
                is_test=False
            )
            
            db.session.add(purchase)
            db.session.commit()
            
            print(f"✅ Verified purchase: user={user_id}, product={product_id}")
        
        elif 'pre_checkout_query' in update:
            query = update['pre_checkout_query']
            bot_token = Config.BOT_TOKEN
            url = f"https://api.telegram.org/bot{bot_token}/answerPreCheckoutQuery"
            
            requests.post(url, json={
                'pre_checkout_query_id': query['id'],
                'ok': True
            }, timeout=5)
        
        return jsonify({'ok': True})
    
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({'ok': True})


@api_bp.route('/check-purchase', methods=['POST'])
@limiter.limit("20 per minute")
@telegram_auth_required
def check_purchase():
    """Check if user has purchased a product - requires Telegram auth"""
    data = request.json
    user_id = get_telegram_user_id()  # Get verified user ID from initData
    product_id = data.get('product_id')
    
    if not product_id:
        return jsonify({'error': 'product_id required'}), 400
    
    purchase = Purchase.query.filter_by(
        user_id=user_id,
        product_id=product_id,
        is_verified=True
    ).first()
    
    return jsonify({'purchased': purchase is not None})


@api_bp.route('/my-purchases', methods=['GET'])
@limiter.limit("20 per minute")
@telegram_auth_required
def my_purchases():
    """Get current user's purchases - requires Telegram auth"""
    user_id = get_telegram_user_id()
    
    purchases = Purchase.query.filter_by(
        user_id=user_id,
        is_verified=True
    ).all()
    
    result = []
    for p in purchases:
        product = Product.query.get(p.product_id)
        result.append({
            'product_id': p.product_id,
            'product_name': product.name if product else 'Unknown',
            'stars_paid': p.stars_paid,
            'purchased_at': p.purchased_at.isoformat() if p.purchased_at else None
        })
    
    return jsonify({'purchases': result})
@api_bp.route('/send-file', methods=['POST'])
def send_file_to_user():
    """Send purchased file directly to user via Telegram bot"""
    import requests
    
    data = request.get_json() or {}
    purchase_id = data.get('purchase_id')
    user_id = data.get('user_id')
    
    if not purchase_id or not user_id:
        return jsonify({'ok': False, 'error': 'Missing data'}), 400
    
    # Get purchase
    purchase = Purchase.query.get(purchase_id)
    if not purchase:
        return jsonify({'ok': False, 'error': 'Purchase not found'}), 404
    
    # Verify user owns this purchase
    if str(purchase.user_id) != str(user_id):
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 403
    
    # Get product
    product = Product.query.get(purchase.product_id)
    if not product or not product.file_key:
        return jsonify({'ok': False, 'error': 'File not found'}), 404
    
    # Get file URL from R2
    from r2_storage import get_r2_url
    file_url = get_r2_url(product.file_key, expires=300)  # 5 min expiry
    
    if not file_url:
        return jsonify({'ok': False, 'error': 'Could not get file'}), 500
    
    # Send file to user via Telegram Bot
    settings = AppSettings.query.first()
    bot_token = settings.bot_token if settings else None
    
    if not bot_token:
        return jsonify({'ok': False, 'error': 'Bot not configured'}), 500
    
    try:
        # Send document to user
        telegram_url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
        
        response = requests.post(telegram_url, data={
            'chat_id': user_id,
            'document': file_url,
            'caption': f"📦 Here's your file: {product.name}\n\nThank you for your purchase!"
        }, timeout=30)
        
        result = response.json()
        
        if result.get('ok'):
            return jsonify({'ok': True, 'message': 'File sent to your Telegram!'})
        else:
            # If URL method fails, try sending message with download link
            telegram_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            requests.post(telegram_url, data={
                'chat_id': user_id,
                'text': f"📦 *{product.name}*\n\n[Click here to download your file]({file_url})\n\n⏰ Link expires in 5 minutes!",
                'parse_mode': 'Markdown'
            }, timeout=10)
            return jsonify({'ok': True, 'message': 'Download link sent to your Telegram!'})
            
    except Exception as e:
        print(f"Error sending file: {e}")
        return jsonify({'ok': False, 'error': 'Failed to send file'}), 500


@api_bp.route('/check-admin', methods=['POST'])
@limiter.limit("30 per minute")
def check_admin():
    """Check if current user is admin - requires Telegram auth"""
    init_data = (
        request.headers.get('X-Telegram-Init-Data') or
        (request.json or {}).get('initData')
    )
    
    if not init_data:
        return jsonify({'is_admin': False})
    
    user_data = validate_telegram_init_data(init_data, Config.BOT_TOKEN)
    if not user_data:
        return jsonify({'is_admin': False})
    
    user_id = user_data.get('id')
    is_admin = user_id in Config.ADMIN_TELEGRAM_IDS
    
    return jsonify({'is_admin': is_admin})
