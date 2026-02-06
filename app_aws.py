import os
import boto3
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError

app = Flask(__name__)
app.secret_key = 'bookbazar_secret_key'

# ---------------------------------------------------------
# AWS CONFIGURATION
# ---------------------------------------------------------
REGION = 'us-east-1'
dynamodb = boto3.resource('dynamodb', region_name=REGION)
sns_client = boto3.client('sns', region_name=REGION)

# DynamoDB Tables (Created manually in AWS Console)
books_table = dynamodb.Table('Books')   # Partition Key: id (String)
users_table = dynamodb.Table('Users')   # Partition Key: email (String)
orders_table = dynamodb.Table('Orders') # Partition Key: order_id (String)

# SNS Topic ARN (UPDATE THIS with your actual Topic ARN from AWS Console)
# Format: 'arn:aws:sns:us-east-1:123456789012:BookBazar_Orders'
SNS_TOPIC_ARN = 'arn:aws:sns:us-east-1:YOUR_ACCOUNT_ID:BookBazar_Orders' 

# File Upload Config
UPLOAD_FOLDER = 'static/images'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------------------------------------------------
# AWS Helper Functions
# ---------------------------------------------------------
def send_sns_notification(subject, message):
    """Sends an email notification via AWS SNS"""
    try:
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=message
        )
    except ClientError as e:
        print(f"Error sending SNS: {e}")

# ---------------------------------------------------------
# Core Routes
# ---------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html', user=session.get('user'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        
        # AWS: Check if user exists in DynamoDB
        response = users_table.get_item(Key={'email': email})
        if 'Item' in response:
            flash('Email already registered!', 'danger')
            return redirect(url_for('signup'))
        
        # AWS: Add User to DynamoDB
        users_table.put_item(Item={
            'email': email,
            'name': name,
            'password': password,
            'role': 'customer' # Default role
        })
        
        # AWS: Notify Admin
        send_sns_notification("New User Signup", f"User {name} ({email}) has joined BookBazar.")
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        # AWS: Fetch user from DynamoDB
        response = users_table.get_item(Key={'email': email})
        
        if 'Item' in response:
            user = response['Item']
            if check_password_hash(user['password'], password):
                session['user'] = user
                
                # Reset Cart
                if 'cart' in session and isinstance(session['cart'], list):
                    session['cart'] = {}
                
                # Check Admin Role
                if user['email'] == 'admin@bookbazar.com':
                    return redirect(url_for('admin_dashboard'))
                return redirect(url_for('browse_books'))
            else:
                flash('Invalid password', 'danger')
        else:
            flash('User not found', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    session.pop('cart', None)
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        flash(f'Thank you, {name}! We have received your message.', 'success')
        return redirect(url_for('contact'))
    return render_template('contact_us.html', user=session.get('user'))

# ---------------------------------------------------------
# Shop Routes
# ---------------------------------------------------------
@app.route('/browse')
def browse_books():
    if 'user' not in session: return redirect(url_for('login'))
    
    # AWS: Scan returns all items from DynamoDB
    response = books_table.scan()
    books = response.get('Items', [])
    
    # Convert Decimal to float/int for display if needed
    # (DynamoDB returns Decimal types, Jinja handles them fine usually)
    return render_template('browse_books.html', books=books, user=session['user'])

@app.route('/book/<book_id>')
def book_details(book_id):
    if 'user' not in session: return redirect(url_for('login'))
    
    # AWS: Get specific item using Key
    # Ensure ID is treated as string since DynamoDB keys are usually strings
    response = books_table.get_item(Key={'id': str(book_id)})
    book = response.get('Item')
    
    if not book:
        flash('Book not found.', 'danger')
        return redirect(url_for('browse_books'))
        
    return render_template('book_details.html', book=book, user=session['user'])

@app.route('/add_to_cart/<book_id>', methods=['POST'])
def add_to_cart(book_id):
    if 'user' not in session: return redirect(url_for('login'))
    if 'cart' not in session or isinstance(session['cart'], list): session['cart'] = {}
    
    # AWS: Check Stock in DynamoDB
    response = books_table.get_item(Key={'id': str(book_id)})
    book = response.get('Item')
    
    if not book: 
        flash('Book not found', 'danger')
        return redirect(url_for('browse_books'))

    cart = session['cart']
    str_id = str(book_id)
    current_qty = cart.get(str_id, 0)
    
    # Logic: DynamoDB uses Decimals, cast to int for comparison
    stock_available = int(book.get('stock', 0))
    
    if current_qty + 1 > stock_available:
        flash(f'Sorry, only {stock_available} copies available!', 'warning')
    else:
        cart[str_id] = current_qty + 1
        session['cart'] = cart
        flash('Cart updated! 🛒', 'success')
        
    return redirect(request.referrer or url_for('browse_books'))

@app.route('/decrease_cart/<book_id>', methods=['POST'])
def decrease_cart(book_id):
    if 'user' not in session: return redirect(url_for('login'))
    cart = session.get('cart', {})
    str_id = str(book_id)
    if str_id in cart:
        if cart[str_id] > 1: cart[str_id] -= 1
        else: del cart[str_id]
    session['cart'] = cart
    flash('Cart updated.', 'info')
    return redirect(request.referrer or url_for('browse_books'))

@app.route('/cart')
def view_cart():
    if 'user' not in session: return redirect(url_for('login'))
    
    cart = session.get('cart', {})
    cart_items = []
    grand_total = 0
    
    # AWS: Must fetch details for every ID in the cart
    for str_id, quantity in cart.items():
        response = books_table.get_item(Key={'id': str_id})
        book = response.get('Item')
        
        if book:
            price = float(book['price'])
            line_total = price * quantity
            grand_total += line_total
            
            # Inject float price for template math
            book['price'] = price 
            cart_items.append({'book': book, 'quantity': quantity, 'line_total': round(line_total, 2)})
            
    return render_template('cart.html', cart_items=cart_items, grand_total=round(grand_total, 2))

@app.route('/remove_from_cart/<book_id>')
def remove_from_cart(book_id):
    if 'cart' in session:
        cart = session['cart']
        str_id = str(book_id)
        if isinstance(cart, dict) and str_id in cart:
            del cart[str_id]
            session['cart'] = cart
            flash('Item removed from cart.', 'warning')
    return redirect(url_for('view_cart'))

@app.route('/checkout', methods=['POST'])
def checkout():
    if 'user' not in session: return redirect(url_for('login'))
    cart = session.get('cart', {})
    if not cart: 
        flash('Your cart is empty!', 'danger')
        return redirect(url_for('browse_books'))
    
    # 1. Validation Loop (Check Stock against DynamoDB)
    for str_id, quantity in cart.items():
        response = books_table.get_item(Key={'id': str_id})
        book = response.get('Item')
        if book and quantity > int(book.get('stock', 0)):
            flash(f"Error: Not enough stock for '{book['title']}'. Only {book['stock']} left.", 'danger')
            return redirect(url_for('view_cart'))

    # 2. Processing Loop (Update Stock & Create Order in DynamoDB)
    for str_id, quantity in cart.items():
        # A. Atomic Update: Decrease Stock
        books_table.update_item(
            Key={'id': str_id},
            UpdateExpression="set stock = stock - :q",
            ExpressionAttributeValues={':q': quantity}
        )
        
        # Fetch book data for receipt
        response = books_table.get_item(Key={'id': str_id})
        book = response['Item']
        
        # B. Create Order ID (UUID)
        order_id = str(uuid.uuid4())
        
        # C. Save Order to DynamoDB
        orders_table.put_item(Item={
            'order_id': order_id,
            'user_id': session['user']['email'],
            'user_name': session['user']['name'], # Saved for Admin view
            'book_title': book['title'],
            'price': book['price'], 
            'quantity': quantity,
            'status': 'Pending',
            'order_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        # D. AWS SNS Notification
        msg_body = f"Order Received!\nUser: {session['user']['name']}\nItem: {book['title']}\nQty: {quantity}"
        send_sns_notification("BookBazar: New Order", msg_body)

    session.pop('cart', None)
    flash('Order placed successfully!', 'success')
    return redirect(url_for('my_orders'))

@app.route('/my_orders')
def my_orders():
    if 'user' not in session: return redirect(url_for('login'))
    
    # AWS: Scan Orders with Filter for current user
    response = orders_table.scan(
        FilterExpression=Attr('user_id').eq(session['user']['email'])
    )
    user_orders = response.get('Items', [])
    
    # Sort orders by date (newest first)
    user_orders.sort(key=lambda x: x['order_date'], reverse=True)
    
    return render_template('my_orders.html', orders=user_orders)

# ---------------------------------------------------------
# Admin Routes
# ---------------------------------------------------------
@app.route('/admin')
def admin_dashboard():
    if 'user' not in session or session['user']['email'] != 'admin@bookbazar.com':
        return redirect(url_for('index'))
    
    # AWS: Fetch all data for Dashboard
    books = books_table.scan().get('Items', [])
    orders = orders_table.scan().get('Items', [])
    orders.sort(key=lambda x: x['order_date'], reverse=True)
    
    # Calculate Stats
    total_sales = sum(float(o['price']) * int(o.get('quantity', 1)) for o in orders)
    total_stock = sum(int(b.get('stock', 0)) for b in books)
    
    return render_template('admin_dashboard.html', 
                           books=books, 
                           orders=orders, 
                           total_sales=round(total_sales, 2), 
                           total_orders=len(orders), 
                           total_stock=total_stock, 
                           user=session['user'])

@app.route('/admin/update_order/<order_id>', methods=['POST'])
def update_order_status(order_id):
    if 'user' not in session or session['user']['email'] != 'admin@bookbazar.com': return redirect(url_for('index'))
    
    new_status = request.form.get('status')
    
    # AWS: Update Item Status in DynamoDB
    # We use order_id as string because we saved it as string UUID
    orders_table.update_item(
        Key={'order_id': str(order_id)},
        UpdateExpression="set #s = :status",
        ExpressionAttributeNames={'#s': 'status'}, # 'status' is a reserved keyword
        ExpressionAttributeValues={':status': new_status}
    )
            
    flash(f'Order updated to {new_status}.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/add', methods=['GET', 'POST'])
def add_book():
    if 'user' not in session or session['user']['email'] != 'admin@bookbazar.com': return redirect(url_for('index'))
    if request.method == 'POST':
        image_filename = 'default_book.jpg'
        if 'image' in request.files:
            file = request.files['image']
            if file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_filename = filename

        # AWS: Generate UUID for new Book ID
        new_id = str(uuid.uuid4())
        
        # AWS: Put Item in DynamoDB
        books_table.put_item(Item={
            'id': new_id, 
            'title': request.form['title'], 
            'author': request.form['author'], 
            'price': int(float(request.form['price'])), # Store numbers as int/decimal
            'description': request.form['description'],
            'stock': int(request.form['stock']),
            'image': image_filename
        })
        
        flash('Book added successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('book_form.html', action='Add')

@app.route('/admin/edit/<book_id>', methods=['GET', 'POST'])
def edit_book(book_id):
    if 'user' not in session or session['user']['email'] != 'admin@bookbazar.com': return redirect(url_for('index'))
    
    # AWS: Get current data
    response = books_table.get_item(Key={'id': str(book_id)})
    book = response.get('Item')
    
    if request.method == 'POST':
        image_filename = book.get('image', 'default_book.jpg')
        if 'image' in request.files:
            file = request.files['image']
            if file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_filename = filename
        
        # AWS: Overwrite Item in DynamoDB
        books_table.put_item(Item={
            'id': str(book_id),
            'title': request.form['title'], 
            'author': request.form['author'], 
            'price': int(float(request.form['price'])),
            'description': request.form['description'],
            'stock': int(request.form['stock']),
            'image': image_filename
        })
        
        flash('Book updated successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
        
    return render_template('book_form.html', action='Edit', book=book)

@app.route('/admin/delete/<book_id>')
def delete_book(book_id):
    if 'user' not in session or session['user']['email'] != 'admin@bookbazar.com': return redirect(url_for('index'))
    
    # AWS: Delete Item from DynamoDB
    books_table.delete_item(Key={'id': str(book_id)})
    
    flash('Book deleted successfully!', 'warning')
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    # Host 0.0.0.0 is REQUIRED for AWS EC2 Deployment
    app.run(host='0.0.0.0', port=5000, debug=True)