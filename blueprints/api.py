"""API routes with rate limiting and Telegram auth validation"""
from flask import Blueprint, request, jsonify, redirect
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


@api_bp.route('/create-donation-invoice', methods=['POST'])
@limiter.limit("10 per minute")
@telegram_auth_required
def create_donation_invoice():
    """Create Telegram Stars invoice for donation"""
    try:
        data = request.json
        amount = data.get('amount')
        if not amount or int(amount) < 1:
            return jsonify({'error': 'amount required (min 1 Star)'}), 400

        amount = int(amount)
        settings = AppSettings.query.first()
        app_name = settings.app_name if settings else 'Magazilla'
        user_id = get_telegram_user_id()

        bot_token = Config.BOT_TOKEN
        url = f"https://api.telegram.org/bot{bot_token}/createInvoiceLink"

        payload = {
            'title': f'Donate to {app_name}'[:32],
            'description': f'Support {app_name} with {amount} Stars — thank you!'[:255],
            'payload': json.dumps({'type': 'donation', 'user_id': user_id, 'amount': amount}),
            'provider_token': '',
            'currency': 'XTR',
            'prices': json.dumps([{'label': 'Donation', 'amount': amount}])
        }

        response = requests.post(url, data=payload, timeout=10)
        result = response.json()

        if result.get('ok'):
            return jsonify({'invoice_link': result['result']})
        else:
            return jsonify({'error': result.get('description', 'Failed to create invoice')}), 400

    except Exception as e:
        print(f"Donation invoice error: {e}")
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
    """Send file directly to user via Telegram bot - downloads first to hide URL"""
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
    
    # Check authorization for paid products
    if not product.is_free and not is_free:
        purchase = Purchase.query.filter_by(
            user_id=str(user_id),
            product_id=product_id,
            is_verified=True
        ).first()
        
        if not purchase:
            return jsonify({'ok': False, 'error': 'Not purchased'}), 403
    
    # Get file key
    file_key = product.file_path
    if not file_key:
        return jsonify({'ok': False, 'error': 'No file available'}), 404
    
    bot_token = Config.BOT_TOKEN
    if not bot_token:
        return jsonify({'ok': False, 'error': 'Bot not configured'}), 500
    
    # Check if user has started the bot
    try:
        check_url = f"https://api.telegram.org/bot{bot_token}/sendChatAction"
        check_response = requests.post(check_url, json={
            'chat_id': user_id,
            'action': 'upload_document'
        }, timeout=5)
        
        check_result = check_response.json()
        if not check_result.get('ok'):
            error_desc = check_result.get('description', '').lower()
            if 'chat not found' in error_desc or 'bot was blocked' in error_desc:
                return jsonify({
                    'ok': False, 
                    'error': 'Please start the bot first'
                }), 400
    except Exception as e:
        print(f"Chat action check error: {e}")
    
    # Get signed URL from R2
    try:
        file_url = get_r2_url(file_key, expires=300)
    except Exception as e:
        print(f"R2 URL error: {e}")
        return jsonify({'ok': False, 'error': 'Could not get file URL'}), 500
    
    if not file_url:
        return jsonify({'ok': False, 'error': 'Could not generate file URL'}), 500
    
    # Prepare caption
    caption = f"📦 {product.name}"
    if product.is_free:
        caption += "\n\n🆓 Free download"
    else:
        caption += "\n\n✅ Thank you for your purchase!"
    
    # Get filename from file_key
    filename = file_key.split('/')[-1] if '/' in file_key else file_key
    # Create nicer filename based on product name
    ext = filename.split('.')[-1] if '.' in filename else ''
    nice_filename = f"{product.name.replace(' ', '_')}.{ext}" if ext else filename
    
    # METHOD 1: Download file first, then upload to Telegram (hides URL completely)
    try:
        print(f"Downloading file from R2: {file_key}")
        file_response = requests.get(file_url, timeout=60, stream=True)
        
        if file_response.status_code == 200:
            # Check file size (Telegram limit is 50MB for bots)
            content_length = file_response.headers.get('content-length')
            file_size = int(content_length) if content_length else len(file_response.content)
            
            if file_size <= 50 * 1024 * 1024:  # 50MB limit
                # Send using multipart form (file upload)
                telegram_url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
                
                files = {
                    'document': (nice_filename, file_response.content)
                }
                data_payload = {
                    'chat_id': user_id,
                    'caption': caption
                }
                
                response = requests.post(telegram_url, data=data_payload, files=files, timeout=120)
                result = response.json()
                
                print(f"Telegram sendDocument (upload) response: {result.get('ok')}")
                
                if result.get('ok'):
                    # Success! Update download count
                    product.download_count = (product.download_count or 0) + 1
                    db.session.commit()
                    return jsonify({'ok': True, 'message': 'File sent!'})
            else:
                print(f"File too large for upload ({file_size} bytes), using URL method")
        
    except Exception as e:
        print(f"Direct upload error: {e}")
    
    # METHOD 2: Fallback - send via URL (for large files or if upload fails)
    try:
        telegram_url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
        
        response = requests.post(telegram_url, json={
            'chat_id': user_id,
            'document': file_url,
            'caption': caption
        }, timeout=60)
        
        result = response.json()
        print(f"Telegram sendDocument (URL) response: {result}")
        
        if result.get('ok'):
            product.download_count = (product.download_count or 0) + 1
            db.session.commit()
            return jsonify({'ok': True, 'message': 'File sent!'})
        else:
            error_desc = result.get('description', 'Unknown error')
            print(f"sendDocument failed: {error_desc}")
            
            # Last resort: send download link as message
            if 'wrong file identifier' in error_desc.lower() or 'failed to get' in error_desc.lower():
                msg_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                msg_response = requests.post(msg_url, json={
                    'chat_id': user_id,
                    'text': f"📦 <b>{product.name}</b>\n\n<a href=\"{file_url}\">⬇️ Click here to download</a>\n\n⏰ <i>Link expires in 5 minutes</i>",
                    'parse_mode': 'HTML',
                    'disable_web_page_preview': False
                }, timeout=10)
                
                msg_result = msg_response.json()
                if msg_result.get('ok'):
                    product.download_count = (product.download_count or 0) + 1
                    db.session.commit()
                    return jsonify({'ok': True, 'message': 'Download link sent!'})
            
            return jsonify({'ok': False, 'error': error_desc}), 500
            
    except requests.Timeout:
        return jsonify({'ok': False, 'error': 'Timeout - file may be too large'}), 500
    except Exception as e:
        print(f"Send file error: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@api_bp.route('/download/<int:product_id>')
@limiter.limit("20 per minute")
def download_file(product_id):
    """Direct download endpoint - redirects to signed R2 URL"""
    from r2_storage import get_r2_url
    
    product = Product.query.get_or_404(product_id)
    
    # Check if free download is allowed
    free_param = request.args.get('free', 'false').lower() == 'true'
    
    if not product.is_free and not free_param:
        # For paid products, verify purchase via initData header
        init_data = request.headers.get('X-Telegram-Init-Data')
        if init_data:
            user_data = validate_telegram_init_data(init_data, Config.BOT_TOKEN)
            if user_data:
                user_id = user_data.get('id')
                purchase = Purchase.query.filter_by(
                    user_id=str(user_id),
                    product_id=product_id,
                    is_verified=True
                ).first()
                if not purchase:
                    return jsonify({'error': 'Not purchased'}), 403
    
    # Get file key
    file_key = product.file_path
    if not file_key:
        return jsonify({'error': 'No file available'}), 404
    
    # Get signed URL from R2
    try:
        file_url = get_r2_url(file_key, expires=300)
    except Exception as e:
        print(f"R2 URL error: {e}")
        return jsonify({'error': 'Could not generate download URL'}), 500
    
    if not file_url:
        return jsonify({'error': 'Could not get file URL'}), 500
    
    # Update download count
    product.download_count = (product.download_count or 0) + 1
    db.session.commit()
    
    # Redirect to the signed URL
    return redirect(file_url, code=302)


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
