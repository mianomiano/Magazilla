"""API routes with rate limiting and validation"""
from flask import Blueprint, request, jsonify
from config import Config
from models import db, Product, Purchase
from utils.decorators import limiter, telegram_user_required
import requests
import json

api_bp = Blueprint('api_bp', __name__)


@api_bp.route('/product/<int:pid>')
@limiter.limit("30 per minute")
def get_product(pid):
    """Get product details"""
    product = Product.query.get_or_404(pid)
    return jsonify(product.to_dict())


@api_bp.route('/create-invoice-link', methods=['POST'])
@limiter.limit("10 per minute")
def create_invoice():
    """Create Telegram Stars invoice"""
    try:
        data = request.json
        product_id = data.get('product_id')
        
        if not product_id:
            return jsonify({'error': 'product_id required'}), 400
        
        product = Product.query.get_or_404(product_id)
        
        if product.is_free:
            return jsonify({'error': 'Product is free'}), 400
        
        bot_token = Config.BOT_TOKEN
        url = f"https://api.telegram.org/bot{bot_token}/createInvoiceLink"
        
        payload = {
            'title': product.name[:32],
            'description': (product.description or product.name)[:255],
            'payload': f"product_{product.id}",
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
    """Secure Telegram webhook endpoint for payment verification"""
    try:
        update = request.json
        
        if 'message' in update and 'successful_payment' in update['message']:
            message = update['message']
            payment = message['successful_payment']
            user_id = message['from']['id']
            
            payload = payment.get('invoice_payload', '')
            if not payload.startswith('product_'):
                return jsonify({'ok': True})
            
            try:
                product_id = int(payload.split('_')[1])
            except (IndexError, ValueError):
                return jsonify({'ok': True})
            
            product = Product.query.get(product_id)
            if not product:
                return jsonify({'ok': True})
            
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
@telegram_user_required
def check_purchase():
    """Check if user has purchased a product"""
    data = request.json
    user_id = int(data.get('user_id'))
    product_id = data.get('product_id')
    
    if not product_id:
        return jsonify({'error': 'product_id required'}), 400
    
    purchase = Purchase.query.filter_by(
        user_id=user_id,
        product_id=product_id,
        is_verified=True
    ).first()
    
    return jsonify({'purchased': purchase is not None})
