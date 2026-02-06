import os
import json
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'bookbazar_secret_key'

# Configuration
UPLOAD_FOLDER = 'static/images'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
DATA_FILE = 'books.json'

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------------------------------------------------
# Helper Functions (Read/Write JSON)
# ---------------------------------------------------------
def load_books():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, 'r') as file:
            return json.load(file)
    except:
        return []

def save_books(books_list):
    with open(DATA_FILE, 'w') as file:
        json.dump(books_list, file, indent=4)

# ---------------------------------------------------------
# Data Storage
# ---------------------------------------------------------
users = [
    {'id': 1, 'name': 'Admin', 'email': 'admin@bookbazar.com', 'password': generate_password_hash('admin123')}
]
orders = []
order_counter = 1

# ---------------------------------------------------------
# Core Routes
# ---------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = next((u for u in users if u['email'] == email), None)
        
        if user and check_password_hash(user['password'], password):
            session['user'] = user
            if 'cart' in session and isinstance(session['cart'], list):
                session['cart'] = {}
            if user['email'] == 'admin@bookbazar.com':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('browse_books'))
        else:
            flash('Invalid email or password', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    session.pop('cart', None)
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        if any(u['email'] == email for u in users):
            flash('Email already registered!', 'danger')
            return redirect(url_for('signup'))
        new_user = {'id': len(users) + 1, 'name': name, 'email': email, 'password': password}
        users.append(new_user)
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/about')
def about():
    return render_template('about.html', user=session.get('user'))

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
    if 'cart' in session and isinstance(session['cart'], list):
        session['cart'] = {}
    books = load_books()
    return render_template('browse_books.html', books=books, user=session['user'])

@app.route('/book/<int:book_id>')
def book_details(book_id):
    if 'user' not in session: return redirect(url_for('login'))
    books = load_books()
    book = next((b for b in books if b['id'] == book_id), None)
    if not book:
        flash('Book not found.', 'danger')
        return redirect(url_for('browse_books'))
    return render_template('book_details.html', book=book, user=session['user'])

@app.route('/add_to_cart/<int:book_id>', methods=['POST'])
def add_to_cart(book_id):
    if 'user' not in session: return redirect(url_for('login'))
    
    if 'cart' not in session or isinstance(session['cart'], list):
        session['cart'] = {}
    
    books = load_books()
    book = next((b for b in books if b['id'] == book_id), None)
    if not book:
        flash('Book not found.', 'danger')
        return redirect(url_for('browse_books'))

    cart = session['cart']
    str_id = str(book_id)
    current_qty = cart.get(str_id, 0)
    
    # Stock Check
    if current_qty + 1 > book.get('stock', 0):
        flash(f'Sorry, only {book["stock"]} copies available!', 'warning')
    else:
        cart[str_id] = current_qty + 1
        session['cart'] = cart
        flash('Cart updated! 🛒', 'success')
        
    return redirect(request.referrer or url_for('browse_books'))

@app.route('/decrease_cart/<int:book_id>', methods=['POST'])
def decrease_cart(book_id):
    if 'user' not in session: return redirect(url_for('login'))
    cart = session.get('cart', {})
    str_id = str(book_id)
    if str_id in cart:
        if cart[str_id] > 1:
            cart[str_id] -= 1
        else:
            del cart[str_id]
    session['cart'] = cart
    flash('Cart updated.', 'info')
    return redirect(request.referrer or url_for('browse_books'))

@app.route('/cart')
def view_cart():
    if 'user' not in session: return redirect(url_for('login'))
    books = load_books()
    cart = session.get('cart', {})
    if isinstance(cart, list):
        session['cart'] = {}
        cart = {}
    cart_items = []
    grand_total = 0
    for str_id, quantity in cart.items():
        book = next((b for b in books if str(b['id']) == str_id), None)
        if book:
            line_total = book['price'] * quantity
            grand_total += line_total
            cart_items.append({'book': book, 'quantity': quantity, 'line_total': round(line_total, 2)})
    return render_template('cart.html', cart_items=cart_items, grand_total=round(grand_total, 2))

@app.route('/remove_from_cart/<int:book_id>')
def remove_from_cart(book_id):
    if 'cart' in session:
        cart = session['cart']
        str_id = str(book_id)
        if isinstance(cart, dict) and str_id in cart:
            del cart[str_id]
            session['cart'] = cart
            flash('Item removed from cart.', 'warning')
        elif isinstance(cart, list):
             session['cart'] = {}
    return redirect(url_for('view_cart'))

# --- UPDATED: Checkout with Status & Stock Validation ---
@app.route('/checkout', methods=['POST'])
def checkout():
    if 'user' not in session: return redirect(url_for('login'))
    cart = session.get('cart', {})
    if not cart or isinstance(cart, list):
        flash('Your cart is empty!', 'danger')
        return redirect(url_for('browse_books'))
    
    books = load_books()
    global order_counter
    
    # 1. Validation Loop
    for str_id, quantity in cart.items():
        book = next((b for b in books if str(b['id']) == str_id), None)
        if book and quantity > book.get('stock', 0):
            flash(f"Error: Not enough stock for '{book['title']}'. Only {book['stock']} left.", 'danger')
            return redirect(url_for('view_cart'))

    # 2. Processing Loop
    for str_id, quantity in cart.items():
        book = next((b for b in books if str(b['id']) == str_id), None)
        if book:
            book['stock'] -= quantity
            for _ in range(quantity):
                new_order = {
                    'order_id': order_counter,
                    'user_id': session['user']['id'],
                    'user_name': session['user']['name'], # NEW: Save user name for Admin
                    'book_title': book['title'],
                    'price': book['price'],
                    'status': 'Pending', # NEW: Default status
                    'order_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                orders.append(new_order)
                order_counter += 1
                
    save_books(books)
    session.pop('cart', None)
    flash(f'Order placed successfully!', 'success')
    return redirect(url_for('my_orders'))

@app.route('/my_orders')
def my_orders():
    if 'user' not in session: return redirect(url_for('login'))
    user_orders = [o for o in orders if o['user_id'] == session['user']['id']]
    # Reverse to show newest orders first
    return render_template('my_orders.html', orders=user_orders[::-1])

# ---------------------------------------------------------
# Admin Routes
# ---------------------------------------------------------
@app.route('/admin')
def admin_dashboard():
    if 'user' not in session or session['user']['email'] != 'admin@bookbazar.com':
        return redirect(url_for('index'))
    books = load_books()
    total_sales = sum(o['price'] for o in orders)
    total_stock = sum(book.get('stock', 0) for book in books)
    
    # Pass 'orders' to template (reversed for newest first)
    return render_template('admin_dashboard.html', 
                           books=books, 
                           orders=orders[::-1], 
                           total_sales=round(total_sales, 2), 
                           total_orders=len(orders), 
                           total_stock=total_stock, 
                           user=session['user'])

# --- NEW: Update Order Status Route ---
@app.route('/admin/update_order/<int:order_id>', methods=['POST'])
def update_order_status(order_id):
    if 'user' not in session or session['user']['email'] != 'admin@bookbazar.com': return redirect(url_for('index'))
    
    new_status = request.form.get('status')
    for order in orders:
        if order['order_id'] == order_id:
            order['status'] = new_status
            break
            
    flash(f'Order #{order_id} updated to {new_status}.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/add', methods=['GET', 'POST'])
def add_book():
    if 'user' not in session or session['user']['email'] != 'admin@bookbazar.com': return redirect(url_for('index'))
    if request.method == 'POST':
        books = load_books()
        image_filename = 'default_book.jpg'
        if 'image' in request.files:
            file = request.files['image']
            if file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_filename = filename

        new_id = max([b['id'] for b in books] or [0]) + 1
        new_book = {
            'id': new_id, 
            'title': request.form['title'], 
            'author': request.form['author'], 
            'price': float(request.form['price']), 
            'description': request.form['description'],
            'stock': int(request.form['stock']),
            'image': image_filename
        }
        books.append(new_book)
        save_books(books)
        flash('Book added successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('book_form.html', action='Add')

@app.route('/admin/edit/<int:book_id>', methods=['GET', 'POST'])
def edit_book(book_id):
    if 'user' not in session or session['user']['email'] != 'admin@bookbazar.com': return redirect(url_for('index'))
    books = load_books()
    book_index = next((i for i, b in enumerate(books) if b['id'] == book_id), None)
    if book_index is None: return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        books[book_index]['title'] = request.form['title']
        books[book_index]['author'] = request.form['author']
        books[book_index]['price'] = float(request.form['price'])
        books[book_index]['description'] = request.form['description']
        books[book_index]['stock'] = int(request.form['stock'])
        
        if 'image' in request.files:
            file = request.files['image']
            if file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                books[book_index]['image'] = filename
        save_books(books)
        flash('Book updated successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('book_form.html', action='Edit', book=books[book_index])

@app.route('/admin/delete/<int:book_id>')
def delete_book(book_id):
    if 'user' not in session or session['user']['email'] != 'admin@bookbazar.com': return redirect(url_for('index'))
    books = load_books()
    book_to_delete = next((b for b in books if b['id'] == book_id), None)
    if book_to_delete:
        image_name = book_to_delete.get('image')
        if image_name and image_name != 'default_book.jpg':
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], image_name)
            if os.path.exists(file_path):
                try: os.remove(file_path)
                except: pass
        books = [b for b in books if b['id'] != book_id]
        save_books(books)
        flash('Book and image deleted successfully!', 'warning')
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)