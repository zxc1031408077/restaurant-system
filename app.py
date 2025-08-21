# app.py - 餐飲點餐系統主程式
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import json
import os
from pytz import timezone

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

# 設置時區為 GMT+8
tz = timezone('Asia/Taipei')

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

@app.template_filter('localtime')
def localtime_filter(value):
    """將 UTC 時間轉換為本地時間 (GMT+8)"""
    if value:
        utc_time = value.replace(tzinfo=timezone('UTC'))
        local_time = utc_time.astimezone(tz)
        return local_time.strftime('%Y-%m-%d %H:%M:%S')
    return value

@app.route('/my_orders')
def my_orders():
    return render_template('my_orders.html')

@app.route('/api/my_orders')
def api_my_orders():
    # 這裡應該根據會話或用戶身份獲取訂單
    # 由於我們沒有用戶系統，我們使用客戶姓名和電話來查找訂單
    # 在實際應用中，您可能需要用戶登入系統
    orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()
    
    orders_data = []
    for order in orders:
        try:
            order_items = json.loads(order.order_items)
        except:
            order_items = []
        
        orders_data.append({
            'id': order.id,
            'customer_name': order.customer_name,
            'customer_phone': order.customer_phone,
            'total_price': order.total_price,
            'status': order.status,
            'created_at': order.created_at,
            'order_items': order_items,
            'dine_in': order.dine_in
        })
    
    return jsonify({'success': True, 'orders': orders_data})


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
    cashier_id = db.Column(db.Integer, db.ForeignKey('cashier.id'), nullable=True)  # 處理訂單的收銀員
    dine_in = db.Column(db.Boolean, default=True)  # True為內用，False為外帶
    notified = db.Column(db.Boolean, default=False)  # 是否已通知前端

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

class Cashier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    orders = db.relationship('Order', backref='cashier', lazy=True)

class OperationLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_type = db.Column(db.String(20), nullable=False)  # 'admin' 或 'cashier'
    user_id = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SystemSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(200), nullable=False)

# 記錄操作日誌的函數
def log_operation(user_type, user_id, action, details=None):
    log = OperationLog(
        user_type=user_type,
        user_id=user_id,
        action=action,
        details=details
    )
    db.session.add(log)
    db.session.commit()

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

@app.route('/api/prepare_order', methods=['POST'])
def prepare_order():
    """準備訂單但不創建，將訂單信息存入session"""
    try:
        customer_name = request.json.get('customer_name')
        customer_phone = request.json.get('customer_phone')
        dine_in = request.json.get('dine_in', True)
        cart = session.get('cart', [])
        
        if not cart:
            return jsonify({'success': False, 'message': '購物車是空的'})
        
        total_price = sum(item['price'] * item['quantity'] for item in cart)
        
        # 將訂單信息存入session，但不創建數據庫記錄
        session['pending_order'] = {
            'customer_name': customer_name,
            'customer_phone': customer_phone,
            'dine_in': dine_in,
            'order_items': cart,
            'total_price': total_price
        }
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/payment')
def payment():
    # 從session獲取待處理訂單信息
    pending_order = session.get('pending_order')
    if not pending_order:
        flash('沒有待處理的訂單')
        return redirect(url_for('menu'))
    
    # 創建一個模擬的訂單對象用於顯示
    class MockOrder:
        def __init__(self, order_data):
            self.id = "pending"  # 臨時ID
            self.customer_name = order_data['customer_name']
            self.customer_phone = order_data.get('customer_phone', '')
            self.total_price = order_data['total_price']
            self.order_items = json.dumps(order_data['order_items'])
    
    order = MockOrder(pending_order)
    return render_template('payment.html', order=order)

@app.route('/api/submit_order', methods=['POST'])
def submit_order():
    """在支付頁面確認支付後創建訂單"""
    try:
        pending_order = session.get('pending_order')
        if not pending_order:
            return jsonify({'success': False, 'message': '沒有待處理的訂單'})
        
        customer_name = pending_order['customer_name']
        customer_phone = pending_order.get('customer_phone')
        dine_in = pending_order.get('dine_in', True)
        cart = pending_order['order_items']
        total_price = pending_order['total_price']
        
        order = Order(
            customer_name=customer_name,
            customer_phone=customer_phone,
            order_items=json.dumps(cart),
            total_price=total_price,
            dine_in=dine_in
        )
        
        db.session.add(order)
        db.session.commit()
        
        # 清空session中的購物車和待處理訂單
        session.pop('cart', None)
        session.pop('pending_order', None)
        
        return jsonify({'success': True, 'order_id': order.id})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

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
        session['admin_id'] = admin.id
        session['user_type'] = 'admin'
        
        # 記錄登入日誌
        log_operation('admin', admin.id, '管理員登入')
        
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
    
    # 熱銷商品排行
    today = datetime.utcnow().date()
    orders_today = Order.query.filter(Order.created_at >= today).all()
    
    # 分析熱銷商品
    product_sales = {}
    for order in orders_today:
        try:
            items = json.loads(order.order_items)
            for item in items:
                product_id = item['id']
                quantity = item['quantity']
                if product_id in product_sales:
                    product_sales[product_id]['quantity'] += quantity
                    product_sales[product_id]['revenue'] += item['price'] * quantity
                else:
                    product_sales[product_id] = {
                        'name': item['name'],
                        'quantity': quantity,
                        'revenue': item['price'] * quantity
                    }
        except:
            continue
    
    # 轉換為列表並排序
    top_products = sorted(product_sales.values(), key=lambda x: x['quantity'], reverse=True)[:5]
    
    return render_template('admin_dashboard.html', 
                         total_orders=total_orders,
                         pending_orders=pending_orders,
                         today_orders=today_orders,
                         today_revenue=today_revenue,
                         top_products=top_products)

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
    products = Product.query.all()  # 获取所有商品
    return render_template('admin_orders.html', orders=orders, products=products)

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
        
        # 記錄操作日誌
        log_operation('admin', session.get('admin_id'), '新增商品', f'商品名稱: {name}')
        
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
        
        # 記錄操作日誌
        log_operation('admin', session.get('admin_id'), '更新商品', f'商品ID: {product_id}')
        
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
        
        # 記錄操作日誌
        log_operation('admin', session.get('admin_id'), '刪除商品', f'商品ID: {product_id}')
        
        return jsonify({'success': True, 'message': '商品刪除成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/admin/update_order_status/<int:order_id>', methods=['PUT'])
def update_order_status(order_id):
    if not session.get('admin_logged_in') and not session.get('cashier_logged_in'):
        return jsonify({'success': False, 'message': '未登入'})
    
    try:
        order = Order.query.get_or_404(order_id)
        new_status = request.json.get('status')
        
        if new_status in ['待處理', '製作中', '完成']:
            order.status = new_status
            
            # 如果是收銀員操作，記錄收銀員ID
            if session.get('cashier_logged_in'):
                order.cashier_id = session.get('cashier_id')
            
            db.session.commit()
            
            # 記錄操作日誌
            user_type = 'cashier' if session.get('cashier_logged_in') else 'admin'
            user_id = session.get('cashier_id') if session.get('cashier_logged_in') else session.get('admin_id')
            log_operation(user_type, user_id, '更新訂單狀態', f'訂單ID: {order_id}, 新狀態: {new_status}')
            
            return jsonify({'success': True, 'message': '訂單狀態更新成功'})
        else:
            return jsonify({'success': False, 'message': '無效的狀態'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# 新增：刪除訂單API
@app.route('/api/admin/delete_order/<int:order_id>', methods=['DELETE'])
def delete_order(order_id):
    if not session.get('admin_logged_in') and not session.get('cashier_logged_in'):
        return jsonify({'success': False, 'message': '未登入'})
    
    try:
        order = Order.query.get_or_404(order_id)
        db.session.delete(order)
        db.session.commit()
        
        # 記錄操作日誌
        user_type = 'cashier' if session.get('cashier_logged_in') else 'admin'
        user_id = session.get('cashier_id') if session.get('cashier_logged_in') else session.get('admin_id')
        log_operation(user_type, user_id, '刪除訂單', f'訂單ID: {order_id}')
        
        return jsonify({'success': True, 'message': '訂單刪除成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# 新增：更新訂單資訊API
@app.route('/api/admin/update_order_info/<int:order_id>', methods=['PUT'])
def update_order_info(order_id):
    if not session.get('admin_logged_in') and not session.get('cashier_logged_in'):
        return jsonify({'success': False, 'message': '未登入'})
    
    try:
        order = Order.query.get_or_404(order_id)
        
        order.customer_name = request.json.get('customer_name', order.customer_name)
        order.customer_phone = request.json.get('customer_phone', order.customer_phone)
        
        db.session.commit()
        
        # 記錄操作日誌
        user_type = 'cashier' if session.get('cashier_logged_in') else 'admin'
        user_id = session.get('cashier_id') if session.get('cashier_logged_in') else session.get('admin_id')
        log_operation(user_type, user_id, '更新訂單資訊', f'訂單ID: {order_id}')
        
        return jsonify({'success': True, 'message': '訂單資訊更新成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# 新增：更新訂單商品API
@app.route('/api/admin/update_order_items/<int:order_id>', methods=['PUT'])
def update_order_items(order_id):
    if not session.get('admin_logged_in') and not session.get('cashier_logged_in'):
        return jsonify({'success': False, 'message': '未登入'})
    
    try:
        order = Order.query.get_or_404(order_id)
        new_items = request.json.get('order_items')
        
        # 計算新總價
        total_price = sum(item['price'] * item['quantity'] for item in new_items)
        
        # 更新訂單項目和總價
        order.order_items = json.dumps(new_items)
        order.total_price = total_price
        
        db.session.commit()
        
        # 記錄操作日誌
        user_type = 'cashier' if session.get('cashier_logged_in') else 'admin'
        user_id = session.get('cashier_id') if session.get('cashier_logged_in') else session.get('admin_id')
        log_operation(user_type, user_id, '更新訂單項目', f'訂單ID: {order_id}')
        
        return jsonify({'success': True, 'message': '訂單商品更新成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/check_new_orders')
def check_new_orders():
    if not session.get('admin_logged_in') and not session.get('cashier_logged_in'):
        return jsonify({'success': False, 'message': '未登入'})
    
    last_check = session.get('last_order_check', datetime.utcnow() - timedelta(minutes=5))

    # 查找新訂單（最近5分鐘內創建的且尚未通知過）
    new_orders = Order.query.filter(
        Order.created_at > last_check,
        Order.status == '待處理',
        Order.notified == False  # 只抓尚未通知過的訂單
    ).order_by(Order.created_at.desc()).all()

    # 更新最後檢查時間
    session['last_order_check'] = datetime.utcnow()

    if new_orders:
        order = new_orders[0]
        try:
            order_items = json.loads(order.order_items)
        except:
            order_items = []

        # 標記已通知
        order.notified = True
        db.session.commit()

        return jsonify({
            'success': True,
            'has_new_order': True,
            'order': {
                'id': order.id,
                'customer_name': order.customer_name,
                'customer_phone': order.customer_phone,
                'total_price': order.total_price,
                'order_items': order_items,
                'dine_in': order.dine_in
            }
        })
    else:
        return jsonify({'success': True, 'has_new_order': False})

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
    
    # 熱銷商品排行 (最近30天)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    orders_30_days = Order.query.filter(Order.created_at >= thirty_days_ago).all()
    
    # 分析熱銷商品
    product_sales = {}
    for order in orders_30_days:
        try:
            items = json.loads(order.order_items)
            for item in items:
                product_id = item['id']
                quantity = item['quantity']
                if product_id in product_sales:
                    product_sales[product_id]['quantity'] += quantity
                    product_sales[product_id]['revenue'] += item['price'] * quantity
                else:
                    product_sales[product_id] = {
                        'name': item['name'],
                        'quantity': quantity,
                        'revenue': item['price'] * quantity
                    }
        except:
            continue
    
    # 轉換為列表並排序
    top_products = sorted(product_sales.values(), key=lambda x: x['quantity'], reverse=True)
    
    return render_template('admin_reports.html',
                         today_orders=len(today_orders),
                         today_revenue=today_revenue,
                         month_orders=len(month_orders),
                         month_revenue=month_revenue,
                         week_data=list(reversed(week_data)),
                         top_products=top_products)

@app.route('/admin/cashiers')
def admin_cashiers():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    cashiers = Cashier.query.all()
    return render_template('admin_cashiers.html', cashiers=cashiers)

@app.route('/api/admin/add_cashier', methods=['POST'])
def add_cashier():
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'message': '未登入'})
    
    try:
        username = request.json.get('username')
        password = request.json.get('password')
        
        # 檢查用戶名是否已存在
        existing_cashier = Cashier.query.filter_by(username=username).first()
        if existing_cashier:
            return jsonify({'success': False, 'message': '用戶名已存在'})
        
        cashier = Cashier(
            username=username,
            password_hash=generate_password_hash(password)
        )
        
        db.session.add(cashier)
        db.session.commit()
        
        # 記錄操作日誌
        log_operation('admin', session.get('admin_id'), '新增收銀員', f'收銀員帳號: {username}')
        
        return jsonify({'success': True, 'message': '收銀員新增成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/admin/update_cashier/<int:cashier_id>', methods=['PUT'])
def update_cashier(cashier_id):
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'message': '未登入'})
    
    try:
        cashier = Cashier.query.get_or_404(cashier_id)
        
        if 'username' in request.json:
            # 檢查用戶名是否已存在（排除自己）
            existing_cashier = Cashier.query.filter(
                Cashier.username == request.json.get('username'),
                Cashier.id != cashier_id
            ).first()
            if existing_cashier:
                return jsonify({'success': False, 'message': '用戶名已存在'})
            
            cashier.username = request.json.get('username')
        
        if 'password' in request.json and request.json.get('password'):
            cashier.password_hash = generate_password_hash(request.json.get('password'))
        
        if 'is_active' in request.json:
            cashier.is_active = request.json.get('is_active')
        
        db.session.commit()
        
        # 記錄操作日誌
        log_operation('admin', session.get('admin_id'), '更新收銀員', f'收銀員ID: {cashier_id}')
        
        return jsonify({'success': True, 'message': '收銀員更新成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/admin/delete_cashier/<int:cashier_id>', methods=['DELETE'])
def delete_cashier(cashier_id):
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'message': '未登入'})
    
    try:
        cashier = Cashier.query.get_or_404(cashier_id)
        db.session.delete(cashier)
        db.session.commit()
        
        # 記錄操作日誌
        log_operation('admin', session.get('admin_id'), '刪除收銀員', f'收銀員ID: {cashier_id}')
        
        return jsonify({'success': True, 'message': '收銀員刪除成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/operation_logs')
def admin_operation_logs():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    logs = OperationLog.query.order_by(OperationLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    
    return render_template('admin_operation_logs.html', logs=logs)

@app.route('/admin/cashier_performance')
def admin_cashier_performance():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    # 獲取所有收銀員
    cashiers = Cashier.query.all()
    
    # 計算每個收銀員的績效
    cashier_performance = []
    for cashier in cashiers:
        # 計算訂單數量和總金額
        orders = Order.query.filter_by(cashier_id=cashier.id).all()
        order_count = len(orders)
        total_revenue = sum(order.total_price for order in orders)
        
        # 計算最近30天的訂單
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_orders = Order.query.filter(
            Order.cashier_id == cashier.id,
            Order.created_at >= thirty_days_ago
        ).all()
        recent_order_count = len(recent_orders)
        recent_revenue = sum(order.total_price for order in recent_orders)
        
        cashier_performance.append({
            'id': cashier.id,
            'username': cashier.username,
            'order_count': order_count,
            'total_revenue': total_revenue,
            'recent_order_count': recent_order_count,
            'recent_revenue': recent_revenue,
            'is_active': cashier.is_active,
            'created_at': cashier.created_at
        })
    
    return render_template('admin_cashier_performance.html', cashier_performance=cashier_performance)

@app.route('/admin/logout')
def admin_logout():
    # 記錄登出日誌
    if session.get('admin_logged_in'):
        log_operation('admin', session.get('admin_id'), '管理員登出')
    
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    session.pop('admin_id', None)
    session.pop('user_type', None)
    return redirect(url_for('admin_login'))

# 收銀員登入路由
@app.route('/cashier')
def cashier_login():
    return render_template('cashier_login.html')

@app.route('/api/cashier_login', methods=['POST'])
def cashier_login_api():
    username = request.json.get('username')
    password = request.json.get('password')
    
    cashier = Cashier.query.filter_by(username=username, is_active=True).first()
    
    if cashier and check_password_hash(cashier.password_hash, password):
        session['cashier_logged_in'] = True
        session['cashier_username'] = username
        session['cashier_id'] = cashier.id
        session['user_type'] = 'cashier'
        
        # 記錄登入日誌
        log_operation('cashier', cashier.id, '收銀員登入')
        
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'message': '帳號或密碼錯誤或帳號已停用'})

@app.route('/cashier/dashboard')
def cashier_dashboard():
    if not session.get('cashier_logged_in'):
        return redirect(url_for('cashier_login'))
    
    # 獲取當前收銀員的訂單統計
    cashier_id = session.get('cashier_id')
    total_orders = Order.query.filter_by(cashier_id=cashier_id).count()
    today_orders = Order.query.filter(
        Order.cashier_id == cashier_id,
        Order.created_at >= datetime.utcnow().date()
    ).count()
    today_revenue = db.session.query(db.func.sum(Order.total_price)).filter(
        Order.cashier_id == cashier_id,
        Order.created_at >= datetime.utcnow().date()
    ).scalar() or 0
    
    return render_template('cashier_dashboard.html', 
                         total_orders=total_orders,
                         today_orders=today_orders,
                         today_revenue=today_revenue)

@app.route('/cashier/orders')
def cashier_orders():
    if not session.get('cashier_logged_in'):
        return redirect(url_for('cashier_login'))
    
    orders = Order.query.order_by(Order.created_at.desc()).all()
    products = Product.query.all()
    
    # 獲取通知自動關閉時間設置
    notification_timeout = SystemSetting.query.filter_by(key='notification_timeout').first()
    timeout_seconds = int(notification_timeout.value) if notification_timeout else 10
    
    return render_template('cashier_orders.html', orders=orders, products=products, timeout_seconds=timeout_seconds)

@app.route('/cashier/logout')
def cashier_logout():
    # 記錄登出日誌
    if session.get('cashier_logged_in'):
        log_operation('cashier', session.get('cashier_id'), '收銀員登出')
    
    session.pop('cashier_logged_in', None)
    session.pop('cashier_username', None)
    session.pop('cashier_id', None)
    session.pop('user_type', None)
    return redirect(url_for('cashier_login'))

# 系統設置API
@app.route('/api/admin/update_setting', methods=['POST'])
def update_setting():
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'message': '未登入'})
    
    try:
        key = request.json.get('key')
        value = request.json.get('value')
        
        setting = SystemSetting.query.filter_by(key=key).first()
        if setting:
            setting.value = value
        else:
            setting = SystemSetting(key=key, value=value)
            db.session.add(setting)
        
        db.session.commit()
        
        # 記錄操作日誌
        log_operation('admin', session.get('admin_id'), '更新系統設置', f'設置項: {key}, 值: {value}')
        
        return jsonify({'success': True, 'message': '設置更新成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

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
                Product(name='湯品', price=40, category='配餐', image_url='https://images.unsplash.com-1547592180-85f173990554?w=300&h=200&fit=crop'),
                Product(name='甜點', price=65, category='甜點', image_url='https://images.unsplash.com/photo-1551024506-0bccd828d307?w=300&h=200&fit=crop'),
                Product(name='冰淇淋', price=55, category='甜點', image_url='https://images.unsplash.com/photo-1567206563064-6f60f40a2b57?w=300&h=200&fit=crop'),
                Product(name='蛋糕', price=85, category='甜點', image_url='https://images.unsplash.com/photo-1578985545062-69928b1d9587?w=300&h=200&fit=crop'),
                Product(name='果汁', price=40, category='飲品', image_url='https://images.unsplash.com/photo-1613478223719-2ab802602423?w=300&h=200&fit=crop'),
                Product(name='熱狗', price=70, category='輕食', image_url='https://images.unsplash.com/photo-1552945382-0ca55e2fe2d9?w=300&h=200&fit=crop'),
                Product(name='烤雞翅', price=95, category='配餐', image_url='https://images.unsplash.com/photo-1527477396000-e27163b481c2?w=300&h=200&fit=crop')
            ]
            
            for product in sample_products:
                db.session.add(product)
        
        # 檢查是否已有系統設置
        if not SystemSetting.query.filter_by(key='notification_timeout').first():
            setting = SystemSetting(key='notification_timeout', value='10')
            db.session.add(setting)
        
        db.session.commit()

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))