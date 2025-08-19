# app.py - 餐飲點餐系統主程式
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import json
import os

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# 資料庫配置
basedir = os.path.abspath(os.path.dirname(__file__))

def process_database_url():
    database_url = os.environ.get('DATABASE_URL')
    if database_url and database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    return database_url

database_url = process_database_url()
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or f'sqlite:///{os.path.join(basedir, "restaurant.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# 添加 Jinja2 過濾器
@app.template_filter('from_json')
def from_json_filter(value):
    """將 JSON 字串轉換為 Python 物件"""
    try:
        return json.loads(value)
    except:
        return []

@app.template_filter('int')
def int_filter(value):
    """轉換為整數"""
    try:
        return int(float(value))
    except:
        return 0

# 資料庫模型
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(200), default='https://via.placeholder.com/200x150?text=食物圖片')
    stock = db.Column(db.Integer, default=99)
    category = db.Column(db.String(50), default='主餐')

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(20))
    order_items = db.Column(db.Text, nullable=False)  # JSON string
    total_price = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='待處理')  # 待處理/製作中/完成
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

# 用戶端路由
@app.route('/')
def index():
    return redirect(url_for('menu'))

@app.route('/menu')
def menu():
    products = Product.query.all()
    return render_template('menu.html', products=products)

@app.route('/cart')
def cart():
    return render_template('cart.html')

@app.route('/api/add_to_cart', methods=['POST'])
def add_to_cart():
    try:
        product_id = request.json.get('product_id')
        quantity = request.json.get('quantity', 1)
        
        product = Product.query.get_or_404(product_id)
        
        cart = session.get('cart', [])
        
        # 檢查商品是否已在購物車中
        found = False
        for item in cart:
            if item['id'] == product_id:
                item['quantity'] += quantity
                found = True
                break
        
        if not found:
            cart.append({
                'id': product_id,
                'name': product.name,
                'price': product.price,
                'quantity': quantity,
                'image_url': product.image_url
            })
        
        session['cart'] = cart
        return jsonify({'success': True, 'message': '已加入購物車'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/remove_from_cart', methods=['POST'])
def remove_from_cart():
    try:
        product_id = request.json.get('product_id')
        cart = session.get('cart', [])
        cart = [item for item in cart if item['id'] != product_id]
        session['cart'] = cart
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/update_cart', methods=['POST'])
def update_cart():
    try:
        product_id = request.json.get('product_id')
        quantity = request.json.get('quantity')
        
        cart = session.get('cart', [])
        for item in cart:
            if item['id'] == product_id:
                if quantity <= 0:
                    cart.remove(item)
                else:
                    item['quantity'] = quantity
                break
        
        session['cart'] = cart
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/get_cart')
def get_cart():
    cart = session.get('cart', [])
    total = sum(item['price'] * item['quantity'] for item in cart)
    return jsonify({'cart': cart, 'total': total})

@app.route('/checkout')
def checkout():
    cart = session.get('cart', [])
    if not cart:
        flash('購物車是空的')
        return redirect(url_for('menu'))
    
    total = sum(item['price'] * item['quantity'] for item in cart)
    return render_template('checkout.html', cart=cart, total=total)

@app.route('/api/submit_order', methods=['POST'])
def submit_order():
    try:
        customer_name = request.json.get('customer_name')
        customer_phone = request.json.get('customer_phone')
        cart = session.get('cart', [])
        
        if not cart:
            return jsonify({'success': False, 'message': '購物車是空的'})
        
        total_price = sum(item['price'] * item['quantity'] for item in cart)
        
        order = Order(
            customer_name=customer_name,
            customer_phone=customer_phone,
            order_items=json.dumps(cart),
            total_price=total_price
        )
        
        db.session.add(order)
        db.session.commit()
        
        # 清空購物車
        session.pop('cart', None)
        
        return jsonify({'success': True, 'order_id': order.id})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/payment/<int:order_id>')
def payment(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template('payment.html', order=order)

@app.route('/order_success/<int:order_id>')
def order_success(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template('order_success.html', order=order)

@app.route('/order_status/<int:order_id>')
def order_status(order_id):
    order = Order.query.get_or_404(order_id)
    # 解析訂單項目
    try:
        order_items = json.loads(order.order_items)
    except:
        order_items = []
    return render_template('order_status.html', order=order, order_items=order_items)

# 商家端路由
@app.route('/admin')
def admin_login():
    return render_template('admin_login.html')

@app.route('/api/admin_login', methods=['POST'])
def admin_login_api():
    username = request.json.get('username')
    password = request.json.get('password')
    
    admin = Admin.query.filter_by(username=username).first()
    
    if admin and check_password_hash(admin.password_hash, password):
        session['admin_logged_in'] = True
        session['admin_username'] = username
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'message': '帳號或密碼錯誤'})

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    # 統計資料
    total_orders = Order.query.count()
    pending_orders = Order.query.filter_by(status='待處理').count()
    today_orders = Order.query.filter(Order.created_at >= datetime.utcnow().date()).count()
    today_revenue = db.session.query(db.func.sum(Order.total_price)).filter(
        Order.created_at >= datetime.utcnow().date()
    ).scalar() or 0
    
    return render_template('admin_dashboard.html', 
                         total_orders=total_orders,
                         pending_orders=pending_orders,
                         today_orders=today_orders,
                         today_revenue=today_revenue)

@app.route('/admin/products')
def admin_products():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    products = Product.query.all()
    return render_template('admin_products.html', products=products)

@app.route('/admin/orders')
def admin_orders():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template('admin_orders.html', orders=orders)

@app.route('/api/admin/add_product', methods=['POST'])
def add_product():
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'message': '未登入'})
    
    try:
        name = request.json.get('name')
        price = float(request.json.get('price'))
        image_url = request.json.get('image_url', 'https://via.placeholder.com/200x150?text=食物圖片')
        stock = int(request.json.get('stock', 99))
        category = request.json.get('category', '主餐')
        
        product = Product(name=name, price=price, image_url=image_url, stock=stock, category=category)
        db.session.add(product)
        db.session.commit()
        
        return jsonify({'success': True, 'message': '商品新增成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/admin/update_product/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'message': '未登入'})
    
    try:
        product = Product.query.get_or_404(product_id)
        
        product.name = request.json.get('name', product.name)
        product.price = float(request.json.get('price', product.price))
        product.image_url = request.json.get('image_url', product.image_url)
        product.stock = int(request.json.get('stock', product.stock))
        product.category = request.json.get('category', product.category)
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': '商品更新成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/admin/delete_product/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'message': '未登入'})
    
    try:
        product = Product.query.get_or_404(product_id)
        db.session.delete(product)
        db.session.commit()
        
        return jsonify({'success': True, 'message': '商品刪除成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/admin/update_order_status/<int:order_id>', methods=['PUT'])
def update_order_status(order_id):
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'message': '未登入'})
    
    try:
        order = Order.query.get_or_404(order_id)
        new_status = request.json.get('status')
        
        if new_status in ['待處理', '製作中', '完成']:
            order.status = new_status
            db.session.commit()
            return jsonify({'success': True, 'message': '訂單狀態更新成功'})
        else:
            return jsonify({'success': False, 'message': '無效的狀態'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/reports')
def admin_reports():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    # 今日報表
    today = datetime.utcnow().date()
    today_orders = Order.query.filter(Order.created_at >= today).all()
    today_revenue = sum(order.total_price for order in today_orders)
    
    # 本月報表
    this_month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_orders = Order.query.filter(Order.created_at >= this_month_start).all()
    month_revenue = sum(order.total_price for order in month_orders)
    
    # 最近7天的銷售數據
    week_data = []
    for i in range(7):
        date = datetime.utcnow().date() - timedelta(days=i)
        day_orders = Order.query.filter(
            Order.created_at >= date,
            Order.created_at < date + timedelta(days=1)
        ).all()
        week_data.append({
            'date': date.strftime('%Y-%m-%d'),
            'orders': len(day_orders),
            'revenue': sum(order.total_price for order in day_orders)
        })
    
    return render_template('admin_reports.html',
                         today_orders=len(today_orders),
                         today_revenue=today_revenue,
                         month_orders=len(month_orders),
                         month_revenue=month_revenue,
                         week_data=list(reversed(week_data)))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    return redirect(url_for('admin_login'))

# 初始化資料庫和示例資料
def init_db():
    with app.app_context():
        db.create_all()
        
        # 檢查是否已有管理員帳號
        if not Admin.query.first():
            admin = Admin(
                username='admin',
                password_hash=generate_password_hash('123456')
            )
            db.session.add(admin)
        
        # 檢查是否已有示例商品
        if not Product.query.first():
            sample_products = [
                Product(name='牛肉漢堡', price=120, category='漢堡', image_url='https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=300&h=200&fit=crop'),
                Product(name='雞肉漢堡', price=100, category='漢堡', image_url='https://images.unsplash.com/photo-1571091718767-18b5b1457add?w=300&h=200&fit=crop'),
                Product(name='魚肉漢堡', price=110, category='漢堡', image_url='https://images.unsplash.com/photo-1553979459-d2229ba7433a?w=300&h=200&fit=crop'),
                Product(name='薯條', price=60, category='配餐', image_url='https://images.unsplash.com/photo-1573080496219-bb080dd4f877?w=300&h=200&fit=crop'),
                Product(name='雞塊', price=80, category='配餐', image_url='https://images.unsplash.com/photo-1562967914-608f82629710?w=300&h=200&fit=crop'),
                Product(name='可樂', price=30, category='飲品', image_url='https://images.unsplash.com/photo-1581636625402-29b2a704ef13?w=300&h=200&fit=crop'),
                Product(name='咖啡', price=50, category='飲品', image_url='https://images.unsplash.com/photo-1509042239860-f550ce710b93?w=300&h=200&fit=crop'),
                Product(name='奶茶', price=45, category='飲品', image_url='https://images.unsplash.com/photo-1578662996442-48f60103fc96?w=300&h=200&fit=crop'),
                Product(name='義大利麵', price=150, category='主餐', image_url='https://images.unsplash.com/photo-1563379091339-03246963d51a?w=300&h=200&fit=crop'),
                Product(name='炒飯', price=90, category='主餐', image_url='https://images.unsplash.com/photo-1512058564366-18510be2db19?w=300&h=200&fit=crop'),
                Product(name='沙拉', price=85, category='輕食', image_url='https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=300&h=200&fit=crop'),
                Product(name='三明治', price=75, category='輕食', image_url='https://images.unsplash.com/photo-1539252554453-80ab65ce3586?w=300&h=200&fit=crop'),
                Product(name='比薩', price=180, category='主餐', image_url='https://images.unsplash.com/photo-1565299624946-b28f40a0ca4b?w=300&h=200&fit=crop'),
                Product(name='湯品', price=40, category='配餐', image_url='https://images.unsplash.com/photo-1547592180-85f173990554?w=300&h=200&fit=crop'),
                Product(name='甜點', price=65, category='甜點', image_url='https://images.unsplash.com/photo-1551024506-0bccd828d307?w=300&h=200&fit=crop'),
                Product(name='冰淇淋', price=55, category='甜點', image_url='https://images.unsplash.com/photo-1567206563064-6f60f40a2b57?w=300&h=200&fit=crop'),
                Product(name='蛋糕', price=85, category='甜點', image_url='https://images.unsplash.com/photo-1578985545062-69928b1d9587?w=300&h=200&fit=crop'),
                Product(name='果汁', price=40, category='飲品', image_url='https://images.unsplash.com/photo-1613478223719-2ab802602423?w=300&h=200&fit=crop'),
                Product(name='熱狗', price=70, category='輕食', image_url='https://images.unsplash.com/photo-1552945382-0ca55e2fe2d9?w=300&h=200&fit=crop'),
                Product(name='烤雞翅', price=95, category='配餐', image_url='https://images.unsplash.com/photo-1527477396000-e27163b481c2?w=300&h=200&fit=crop')
            ]
            
            for product in sample_products:
                db.session.add(product)
        
        db.session.commit()

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))