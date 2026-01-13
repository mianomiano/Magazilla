from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from werkzeug.utils import secure_filename
from functools import wraps
import os, time, json, requests as req
from config import Config
from models import db, Product, Purchase, AppSettings
from r2_storage import upload_to_r2, get_r2_url, delete_from_r2

app = Flask(__name__)  # FIXED: was Flask(name)
app.config.from_object(Config)
db.init_app(app)

def allowed(f): return '.' in f and f.rsplit('.',1)[1].lower() in Config.ALLOWED_EXTENSIONS

def settings():
    s = AppSettings.query.first()
    if not s: s = AppSettings(); db.session.add(s); db.session.commit()
    return s

def admin_req(f):
    @wraps(f)
    def dec(*a,**k): return f(*a,**k) if session.get('is_admin') else redirect(url_for('admin_login'))
    return dec

# Template helper to get R2 URLs
@app.context_processor
def utility_processor():
    def r2_url(key, expires=3600):
        return get_r2_url(key, expires) if key else None
    return dict(r2_url=r2_url)

with app.app_context(): db.create_all(); settings()

@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if request.method=='POST':
        if request.form.get('password')==os.environ.get('ADMIN_PASSWORD','admin123'):
            session['is_admin']=True; return redirect(url_for('admin'))
        return render_template('admin_login.html',settings=settings(),error='Wrong password')
    return render_template('admin_login.html',settings=settings(),error=None)

@app.route('/admin/logout')
def admin_logout(): session.pop('is_admin',None); return redirect(url_for('index'))

@app.route('/admin')
@admin_req
def admin():
    prods = Product.query.all()
    stars = 0
    return render_template('admin.html',products=prods,settings=settings(),
        total_downloads=sum(p.download_count for p in prods),total_products=len(prods),
        total_purchases=Purchase.query.count(),total_stars=stars,
        current_user={'id': 'admin'})  # FIXED: current_user for template

@app.route('/')
def index():
    prods = Product.query.filter_by(is_active=True).order_by(Product.created_at.desc()).all()
    cats = [c[0] for c in db.session.query(Product.category).distinct().all()]
    return render_template('index.html',products=prods,categories=cats,settings=settings(),is_admin=session.get('is_admin',False))

@app.route('/product/<int:pid>')
def product_detail(pid):
    p = Product.query.get_or_404(pid)
    uid = request.args.get('user_id')
    purchased = False
    
    # ADMIN BYPASS
    if uid in ['admin', None, '']:
        purchased = True
        
    if uid and uid not in ['admin', None, '']:
        try: 
            purchased = Purchase.query.filter_by(user_id=int(uid),product_id=pid).first() is not None
        except: 
            pass
    return render_template('product.html',product=p,settings=settings(),purchased=purchased,user_id=uid)

@app.route('/api/product/<int:pid>')
def api_product(pid): return jsonify(Product.query.get_or_404(pid).to_dict())

@app.route('/api/create-invoice-link', methods=['POST'])
def invoice():
    try:
        d = request.json
        if not d or 'product_id' not in d:
            return jsonify({'error': 'Missing product_id'}), 400
            
        p = Product.query.get_or_404(d.get('product_id'))
        if p.is_free: 
            return jsonify({'error': 'Free product'}), 400
        
        # ADMIN BYPASS
        uid = request.headers.get('X-User-ID', d.get('user_id', ''))
        if uid == 'admin':
            return jsonify({'invoice_link': 'https://t.me/yourbot/test', 'is_admin': True})
        
        t = os.environ.get('BOT_TOKEN')
        if not t:
            return jsonify({'error': 'Bot token missing'}), 500
        
        # FIXED: Telegram Stars price must be INTEGER
        prices = [{'label': p.name[:64], 'amount': int(p.price)}]
        
        r = req.post(f"https://api.telegram.org/bot{t}/createInvoiceLink", data={
            'title': p.name[:32],
            'description': (p.description or p.name)[:255],
            'payload': f"product_{p.id}",
            'provider_token': '',  # Empty = Telegram Stars
            'currency': 'XTR',
            'prices': json.dumps(prices)
        }, timeout=10).json()
        
        if r.get('ok') and r.get('result'):
            return jsonify({'invoice_link': r['result']})
        else:
            return jsonify({'error': r.get('description', 'Telegram API failed')}), 400
            
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/api/verify-purchase', methods=['POST'])  # NEW ENDPOINT
def verify_purchase():
    try:
        data = request.json
        pid = data.get('product_id')
        uid = data.get('user_id')
        
        if not pid or not uid:
            return jsonify({'error': 'Missing product_id or user_id'}), 400
        
        # Handle string user_id (admin) or int
        try:
            uid_int = int(uid)
        except:
            uid_int = 0  # Admin fallback
            
        # Mark as purchased
        purchase = Purchase.query.filter_by(user_id=uid_int, product_id=pid).first()
        if not purchase:
            purchase = Purchase(user_id=uid_int, product_id=pid)
            db.session.add(purchase)
            db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/download/<int:pid>')
def download(pid):
    p = Product.query.get_or_404(pid)
    uid = request.args.get('user_id')
    
    if not p.file_path: return jsonify({'error':'No file'}),404
    
    can = p.is_free
    if not can and uid:
        try:
            if uid == 'admin':
                can = True
            else:
                can = Purchase.query.filter_by(user_id=int(uid),product_id=pid).first() is not None
        except: 
            pass
    
    if not can: return jsonify({'error':'Purchase required'}),403
    
    # Get presigned URL from R2
    download_url = get_r2_url(p.file_path, expires=300)
    if not download_url: return jsonify({'error':'File unavailable'}),500
    
    p.download_count += 1; db.session.commit()
    return redirect(download_url)

if __name__ == '__main__':
    app.run(debug=True)