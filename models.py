from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
db = SQLAlchemy()

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Integer, default=0)
    is_free = db.Column(db.Boolean, default=True)
    category = db.Column(db.String(100), default='General')
    thumbnail = db.Column(db.String(500))  # R2 key for thumbnail
    file_path = db.Column(db.String(500))  # R2 key for file
    download_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    def to_dict(self):
        return {'id':self.id,'name':self.name,'description':self.description,'price':self.price,'is_free':self.is_free,'category':self.category,'thumbnail':self.thumbnail,'file_path':self.file_path,'download_count':self.download_count,'is_active':self.is_active}

class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.BigInteger, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    telegram_payment_id = db.Column(db.String(200))
    stars_paid = db.Column(db.Integer, default=0)
    purchased_at = db.Column(db.DateTime, default=datetime.utcnow)

class AppSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    app_name = db.Column(db.String(200), default='Magazilla')
    logo_path = db.Column(db.String(500), default='')  # R2 key for logo
    primary_color = db.Column(db.String(20), default='#090c11')
    secondary_color = db.Column(db.String(20), default='#afe81f')
    accent_color = db.Column(db.String(20), default='#1534fe')
