from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from werkzeug.utils import secure_filename
from functools import wraps
import os, time, json, requests as req
from config import Config
from models import db, Product, Purchase, AppSettings
from r2_storage import upload_to_r2, get_r2_url, delete_from_r2

app = Flask(__name__)
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
    if uid:
        try: purchased = Purchase.query.filter_by(user_id=int(uid),product_id=pid).first() is not None
        except: pass
    return render_template('product.html',product=p,settings=settings(),purchased=purchased,user_id=uid)

@app.route('/api/product/<int:pid>')
def api_product(pid): return jsonify(Product.query.get_or_404(pid).to_dict())

@app.route('/api/create-invoice-link', methods=['POST'])
def invoice():
    try:
        d = request.json; p = Product.query.get_or_404(d.get('product_id'))
        if p.is_free: return jsonify({'error':'Free'}),400
        t = os.environ.get('BOT_TOKEN',Config.BOT_TOKEN)
        r = req.post(f"https://api.telegram.org/bot{t}/createInvoiceLink",data={
            'title':p.name[:32],'description':(p.description or p.name)[:255],'payload':f"product_{p.id}",
            'provider_token':'','currency':'XTR','prices':json.dumps([{'label':p.name[:64],'amount':p.price}])
        },timeout=10).json()
        return jsonify({'invoice_link':r['result']}) if r.get('ok') else jsonify({'error':r.get('description','Failed')}),400
    except Exception as e: return jsonify({'error':str(e)}),500

@app.route('/download/<int:pid>')
def download(pid):
    p = Product.query.get_or_404(pid)
    uid = request.args.get('user_id')
    
    if not p.file_path: return jsonify({'error':'No file'}),404
    
    can = p.is_free
    if not can and uid:
        try: can = Purchase.query.filter_by(user_id=int(uid),product_id=pid).first() is not None
        except: pass
    
    if not can: return jsonify({'error':'Purchase required'}),403
    
    # Get presigned URL from R2
    download_url = get_r2_url(p.file_path, expires=300)  # 5 min expiry
    if not download_url: return jsonify({'error':'File unavailable'}),500
    
    p.download_count += 1; db.session.commit()
    
    # Redirect to R2 presigned URL
    return redirect(download_url)

@app.route('/admin')
@admin_req
def admin():
    prods = Product.query.order_by(Product.created_at.desc()).all()
    stars = db.session.query(db.func.sum(Purchase.stars_paid)).scalar() or 0
    return render_template('admin.html',products=prods,settings=settings(),
        total_downloads=sum(p.download_count for p in prods),total_products=len(prods),
        total_purchases=Purchase.query.count(),total_stars=stars)

@app.route('/admin/product/new', methods=['GET','POST'])
@admin_req
def new_product():
    cats = list(set([c[0] for c in db.session.query(Product.category).distinct().all()]+['Icons','UI Kits','Templates','Stickers','General']))
    if request.method=='POST':
        free = request.form.get('is_free')=='on'
        cat = request.form.get('category','General')
        if cat=='_custom': cat = request.form.get('custom_category','General')
        p = Product(name=request.form.get('name','Untitled'),description=request.form.get('description',''),
            price=0 if free else int(request.form.get('price',1) or 1),is_free=free,category=cat)
        
        # Upload thumbnail to R2
        if 'thumbnail' in request.files:
            f = request.files['thumbnail']
            if f and f.filename and allowed(f.filename):
                key = upload_to_r2(f, 'thumbnails')
                if key: p.thumbnail = key
        
        # Upload file to R2
        if 'file' in request.files:
            f = request.files['file']
            if f and f.filename:
                key = upload_to_r2(f, 'files')
                if key: p.file_path = key
        
        db.session.add(p); db.session.commit(); return redirect(url_for('admin'))
    return render_template('edit_product.html',product=None,settings=settings(),categories=cats)

@app.route('/admin/product/<int:pid>/edit', methods=['GET','POST'])
@admin_req
def edit_product(pid):
    p = Product.query.get_or_404(pid)
    cats = list(set([c[0] for c in db.session.query(Product.category).distinct().all()]+['Icons','UI Kits','Templates','Stickers','General']))
    if request.method=='POST':
        p.name = request.form.get('name',p.name); p.description = request.form.get('description','')
        p.is_free = request.form.get('is_free')=='on'
        p.price = 0 if p.is_free else int(request.form.get('price',1) or 1)
        cat = request.form.get('category','General')
        p.category = request.form.get('custom_category','General') if cat=='_custom' else cat
        p.is_active = request.form.get('is_active')=='on'
        
        # Upload new thumbnail to R2
        if 'thumbnail' in request.files:
            f = request.files['thumbnail']
            if f and f.filename and allowed(f.filename):
                # Delete old thumbnail
                if p.thumbnail: delete_from_r2(p.thumbnail)
                key = upload_to_r2(f, 'thumbnails')
                if key: p.thumbnail = key
        
        # Upload new file to R2
        if 'file' in request.files:
            f = request.files['file']
            if f and f.filename:
                # Delete old file
                if p.file_path: delete_from_r2(p.file_path)
                key = upload_to_r2(f, 'files')
                if key: p.file_path = key
        
        db.session.commit(); return redirect(url_for('admin'))
    return render_template('edit_product.html',product=p,settings=settings(),categories=cats)

@app.route('/admin/product/<int:pid>/delete', methods=['POST'])
@admin_req
def delete_product(pid):
    p = Product.query.get_or_404(pid)
    # Delete files from R2
    if p.thumbnail: delete_from_r2(p.thumbnail)
    if p.file_path: delete_from_r2(p.file_path)
    db.session.delete(p); db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/settings', methods=['GET','POST'])
@admin_req
def admin_settings():
    s = settings()
    if request.method=='POST':
        s.app_name = request.form.get('app_name','Magazilla')
        s.primary_color = request.form.get('primary_color','#090c11')
        s.secondary_color = request.form.get('secondary_color','#afe81f')
        s.accent_color = request.form.get('accent_color','#1534fe')
        
        # Upload logo to R2
        if 'logo' in request.files:
            f = request.files['logo']
            if f and f.filename:
                # Delete old logo
                if s.logo_path: delete_from_r2(s.logo_path)
                key = upload_to_r2(f, 'logos')
                if key: s.logo_path = key
        
        db.session.commit(); return redirect(url_for('admin'))
    return render_template('settings.html',settings=s)

@app.route('/api/verify-purchase', methods=['POST'])
def verify():
    d = request.json; uid,pid = d.get('user_id'),d.get('product_id')
    if not uid or not pid: return jsonify({'error':'Missing'}),400
    if Purchase.query.filter_by(user_id=uid,product_id=pid).first(): return jsonify({'success':True})
    p = Product.query.get(pid)
    db.session.add(Purchase(user_id=uid,product_id=pid,telegram_payment_id=d.get('payment_id',''),stars_paid=p.price if p else 0))
    db.session.commit(); return jsonify({'success':True})

@app.route('/health')
def health(): return 'ok'

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)))
