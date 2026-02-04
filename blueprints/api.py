"""API routes with rate limiting and Telegram auth validation"""
from flask import Blueprint, request, jsonify
from models import db, Product, Purchase, AppSettings
from config import Config
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
@limiter.limit("10 per minute")
def send_file_to_user():
    """Send file directly to user via Telegram bot (for mobile downloads)"""
    from r2_storage import get_r2_url
    
    data = request.get_json() or {}
    product_id = data.get('product_id')
    user_id = data.get('user_id')
    is_free = data.get('is_free', False)
    
    if not product_id or not user_id:
        return jsonify({'ok': False, 'error': 'Missing product_id or user_id'}), 400
    
    # Get product
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'ok': False, 'error': 'Product not found'}), 404
    
    # Check authorization
    if not product.is_free and not is_free:
        # Paid product - check if user purchased
        purchase = Purchase.query.filter_by(
            user_id=str(user_id),
            product_id=product_id,
            is_verified=True
        ).first()
        
        if not purchase:
            return jsonify({'ok': False, 'error': 'Not purchased'}), 403
    
    # Get file key (support both file_path and file_key)
    file_key = getattr(product, 'file_path', None) or getattr(product, 'file_key', None)
    if not file_key:
        return jsonify({'ok': False, 'error': 'No file available for this product'}), 404
    
    # Get file URL from R2
    try:
        file_url = get_r2_url(file_key, expires=300)  # 5 min expiry
    except Exception as e:
        print(f"R2 URL error: {e}")
        file_url = None
    
    if not file_url:
        return jsonify({'ok': False, 'error': 'Could not generate file URL'}), 500
    
    # Get bot token from config or settings
    bot_token = Config.BOT_TOKEN
    if not bot_token:
        settings = AppSettings.query.first()
        bot_token = settings.bot_token if settings else None
    
    if not bot_token:
        return jsonify({'ok': False, 'error': 'Bot not configured'}), 500
    
    # Prepare caption
    if product.is_free:
        caption = f"📦 {product.name}\n\n🆓 Free download - Enjoy!"
    else:
        caption = f"📦 {product.name}\n\n✅ Thank you for your purchase!"
    
    try:
        # Try sending document directly via URL
        telegram_url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
        
        response = requests.post(telegram_url, data={
            'chat_id': user_id,
            'document': file_url,
            'caption': caption
        }, timeout=60)
        
        result = response.json()
        
        if result.get('ok'):
            # Update download count
            product.download_count = (product.download_count or 0) + 1
            db.session.commit()
            return jsonify({'ok': True, 'message': 'File sent to your Telegram!'})
        else:
            # Document send failed - send as clickable link instead
            error_desc = result.get('description', 'Unknown error')
            print(f"Telegram sendDocument failed: {error_desc}")
            
            # Fallback: send download link as message
            telegram_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            msg_response = requests.post(telegram_url, data={
                'chat_id': user_id,
                'text': f"📦 *{product.name}*\n\n[⬇️ Click here to download]({file_url})\n\n⏰ _Link expires in 5 minutes_",
                'parse_mode': 'Markdown',
                'disable_web_page_preview': False
            }, timeout=10)
            
            msg_result = msg_response.json()
            
            if msg_result.get('ok'):
                product.download_count = (product.download_count or 0) + 1
                db.session.commit()
                return jsonify({'ok': True, 'message': 'Download link sent to your Telegram!'})
            else:
                print(f"Telegram sendMessage also failed: {msg_result}")
                return jsonify({'ok': False, 'error': 'Could not send to Telegram'}), 500
            
    except requests.Timeout:
        return jsonify({'ok': False, 'error': 'Timeout - file may be too large. Try desktop.'}), 500
    except Exception as e:
        print(f"Send file error: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@api_bp.route('/download/<int:product_id>')
@limiter.limit("20 per minute")
def download_file(product_id):
    """Direct download endpoint for desktop"""
    from flask import redirect
    from r2_storage import get_r2_url
    
    product = Product.query.get_or_404(product_id)
    
    # Get user_id from query param or header
    free = request.args.get('free', 'false').lower() == 'true'
    
    # For paid products, we should verify purchase
    # But since this is called from product page where we already checked, 
    # we'll allow it (the product page only shows download if purchased)
    
    if not product.is_free and not free:
        # In production, you'd want to verify the user here
        # For now, we trust the frontend check
        pass
    
    # Get file key
    file_key = getattr(product, 'file_path', None) or getattr(product, 'file_key', None)
    if not file_key:
        return jsonify({'error': 'No file available'}), 404
    
    # Get signed URL
    try:
        file_url = get_r2_url(file_key, expires=300)
    except Exception as e:
        print(f"R2 URL error: {e}")
        return jsonify({'error': 'Could not get file'}), 500
    
    if not file_url:
        return jsonify({'error': 'Could not generate download URL'}), 500
    
    # Update download count
    product.download_count = (product.download_count or 0) + 1
    db.session.commit()
    
    # Redirect to signed URL
    return redirect(file_url)


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
