"""Public-facing routes"""
from flask import Blueprint, render_template, request, redirect, jsonify
from models import db, Product, Purchase
from r2_storage import get_r2_url
from utils.decorators import limiter

public_bp = Blueprint('public_bp', __name__)


@public_bp.route('/')
def index():
    """Homepage - product listing"""
    products = Product.query.filter_by(is_active=True).order_by(
        Product.created_at.desc()
    ).all()
    
    categories = [
        c[0] for c in db.session.query(Product.category).distinct().all()
    ]
    
    return render_template(
        'index.html',
        products=products,
        categories=categories
    )


@public_bp.route('/product/<int:pid>')
def product_detail(pid):
    """Product detail page"""
    product = Product.query.get_or_404(pid)
    user_id = request.args.get('user_id')
    
    purchased = False
    if user_id:
        try:
            purchased = Purchase.query.filter_by(
                user_id=int(user_id),
                product_id=pid,
                is_verified=True
            ).first() is not None
        except ValueError:
            pass
    
    return render_template(
        'product.html',
        product=product,
        purchased=purchased,
        user_id=user_id
    )


@public_bp.route('/download/<int:pid>')
@limiter.limit("20 per minute")
def download(pid):
    """Download product file"""
    product = Product.query.get_or_404(pid)
    user_id = request.args.get('user_id')
    
    if not product.file_path:
        return jsonify({'error': 'No file available'}), 404
    
    can_download = product.is_free
    
    if not can_download and user_id:
        try:
            user_id_int = int(user_id)
            can_download = Purchase.query.filter_by(
                user_id=user_id_int,
                product_id=pid,
                is_verified=True
            ).first() is not None
        except ValueError:
            pass
    
    if not can_download:
        return jsonify({'error': 'Purchase required'}), 403
    
    download_url = get_r2_url(product.file_path, expires=300)
    if not download_url:
        return jsonify({'error': 'File unavailable'}), 500
    
    product.download_count += 1
    db.session.commit()
    
    return redirect(download_url)
