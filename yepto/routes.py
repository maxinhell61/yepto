from flask import Flask, Blueprint, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import select
from datetime import datetime
from .models import db, Product, Category, Cart, CartItem, Order, Payment, OrderItem, User, OrderStatus

app = Flask(__name__)
CORS(app)

@app.route('/api/products', methods=['GET'])
def get_products():
    category = request.args.get('category')
    search = request.args.get('search')

    query = Product.query
    if category:
        query = query.join(Category).filter(Category.name == category)
    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))

    products = query.all()
    return jsonify({'products': [
        {'id': p.id, 'name': p.name, 'price': p.price, 'image_url': p.image_url, 'category': p.category.name}
        for p in products
    ]})

@app.route('/api/categories', methods=['GET'])
def get_categories():
    categories = Category.query.all()
    return jsonify({'categories': [cat.name for cat in categories]})

# # Ensure you define the api blueprint if you intend to use it
# api = Blueprint('api', __name__)

@app.route('/cart/items', methods=['GET'])
@jwt_required()
def get_cart_items():
    user_id = get_jwt_identity()
    cart = Cart.query.filter_by(user_id=user_id).first()
    if not cart:
        return jsonify({"message": "Cart is empty"}), 404
    return jsonify([{
        "product_id": item.product_id,
        "name": item.product.name,
        "price": item.product.price,
        "quantity": item.quantity
    } for item in cart.items]), 200

@app.route('/cart/items', methods=['POST'])
@jwt_required()
def add_item_to_cart():
    user_id = get_jwt_identity()
    data = request.get_json()
    cart = Cart.query.filter_by(user_id=user_id).first() or Cart(user_id=user_id)
    product = Product.query.get(data['product_id'])
    if not product or product.stock < data.get('quantity', 1):
        return jsonify({"error": "Invalid product or insufficient stock"}), 400
    cart_item = CartItem(
        cart_id=cart.id,
        product_id=data['product_id'],
        quantity=data['quantity']
    )
    db.session.add(cart_item)
    product.stock -= data['quantity']
    db.session.commit()  # Commit the session after adding the item
    return jsonify({"message": "Item added to cart"}), 201

@app.route('/api/cart', methods=['POST'])
@jwt_required()
def add_to_cart():
    user_id = get_jwt_identity()
    data = request.get_json()

    if 'product_id' not in data or 'quantity' not in data:
        return jsonify({"error": "Missing product_id or quantity"}), 400

    try:
        product = db.session.execute(
            select(Product)
            .where(Product.id == data['product_id'])
            .with_for_update()
        ).scalar_one()

        if product.stock < data['quantity']:
            return jsonify({"error": "Insufficient stock"}), 400

        cart = Cart.query.filter_by(user_id=user_id).first()
        if not cart:
            cart = Cart(user_id=user_id)
            db.session.add(cart)

        existing_item = next((i for i in cart.items if i.product_id == product.id), None)
        if existing_item:
            existing_item.quantity += data['quantity']
        else:
            cart_item = CartItem(cart_id=cart.id, product_id=product.id, quantity=data['quantity'])
            db.session.add(cart_item)

        product.stock -= data['quantity']
        db.session.commit()
        return jsonify({"message": "Item added to cart"}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Failed to update cart"}), 500
@app.route('/api/cart-summary', methods=['GET'])
@jwt_required()
def get_cart_summary():
    user_id = get_jwt_identity()
    cart_items = Cart.query.filter_by(user_id=user_id).all()
    total_price = sum(item.product.price * item.quantity for item in cart_items)
    return jsonify({'total_items': len(cart_items), 'total_price': total_price})


@app.route('/api/dashboard', methods=['GET'])
def get_dashboard():
    categories = Category.query.all()
    products = Product.query.limit(10).all()
    return jsonify({
        'categories': [cat.name for cat in categories],
        'featured_products': [{'id': p.id, 'name': p.name, 'price': p.price} for p in products]
    })


@app.route('/api/orders/<int:order_id>/return', methods=['POST'])
@jwt_required()
def return_order(order_id):
    user_id = get_jwt_identity()
    order = Order.query.filter_by(id=order_id, user_id=user_id).first()
    
    if not order:
        return jsonify({"error": "Order not found"}), 404
    
    if order.return_status is not None:
        return jsonify({"error": "Order already returned"}), 400
    
    if (datetime.utcnow() - order.created_at).days > 30:
        return jsonify({"error": "Order return period has expired"}), 400
    
    for item in order.items:
        product = Product.query.get(item.product_id)
        if product:
            product.stock += item.quantity
    
    order.return_status = 'returned'
    db.session.commit()  # Commit the session after updating the order
    return jsonify({"message": "Order returned successfully"})

@app.route('/api/checkout', methods=['POST'])
@jwt_required()
def create_order():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user.cart or not user.cart.items:
        return jsonify({"error": "Cart is empty"}), 400

    try:
        db.session.begin_nested()

        total = 0
        new_order = Order(user_id=user_id, status="pending_payment")
        db.session.add(new_order)

        for cart_item in user.cart.items:
            product = db.session.execute(
                select(Product)
                .where(Product.id == cart_item.product_id)
                .with_for_update()
            ).scalar_one()

            if product.stock < cart_item.quantity:
                db.session.rollback()
                return jsonify({"error": f"Insufficient stock for {product.name}"}), 400

            total += cart_item.quantity * product.price
            new_order.items.append(OrderItem(
                product_id=product.id,
                quantity=cart_item.quantity,
                price=product.price
            ))
            product.stock -= cart_item.quantity

        new_order.total = total
        CartItem.query.filter_by(cart_id=user.cart.id).delete()
        db.session.commit()
        return jsonify({"message": "Order created", "order_id": new_order.id}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Checkout failed: {str(e)}"}), 500

@app.route('/api/orders/<int:order_id>/cancel', methods=['POST'])
@jwt_required()
def cancel_order(order_id):
    user_id = get_jwt_identity()
    order = Order.query.filter_by(id=order_id, user_id=user_id).first()
    if not order:
        return jsonify({"error": "Order not found"}), 404

    if order.status not in [OrderStatus.PENDING.value, OrderStatus.COMPLETED.value]:
        return jsonify({"error": "Order cannot be cancelled"}), 400

    for item in order.items:
        product = Product.query.get(item.product_id)
        if product:
            product.stock += item.quantity

    order.status = OrderStatus.CANCELLED.value
    db.session.commit()

    return jsonify({"message": "Order cancelled successfully"}), 200


@app.route('/api/orders/<int:order_id>/return', methods=['POST'])
@jwt_required()
def return_order(order_id):
    user_id = get_jwt_identity()
    order = Order.query.filter_by(id=order_id, user_id=user_id).first()
    
    if not order:
        return jsonify({"error": "Order not found"}), 404
    
    if order.return_status is not None:
        return jsonify({"error": "Order already returned"}), 400
    
    # Check if the order is eligible for return (e.g., within 30 days)
    if (datetime.utcnow() - order.created_at).days > 30:
        return jsonify({"error": "Order return period has expired"}), 400
    
    # Restore stock
    for item in order.items:
        product = Product.query.get(item.product_id)
        if product: #
            product.stock += item.quantity
    
    order.return_status = 'returned'
    
    
    return jsonify({"message": "Order returned successfully"})





























































# from flask import Flask, Blueprint, jsonify,request
# from flask_cors import CORS
# from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt, JWTManager
# from .models import db, Product, Category,Cart,CartItem,Payment,OrderItem,OrderStatus
# from datetime import datetime




# app = Flask(__name__)
# CORS(app)

# @app.route('/api/products', methods=['GET'])
# def get_products():
#     category = request.args.get('category')
#     search = request.args.get('search')

#     query = Product.query
#     if category:
#         query = query.join(Category).filter(Category.name == category)  # Fix category filtering
#     if search:
#         query = query.filter(Product.name.ilike(f"%{search}%"))

#     products = query.all()
#     return jsonify({'products': [
#         {'id': p.id, 'name': p.name, 'price': p.price, 'image_url': p.image_url, 'category': p.category.name}
#         for p in products
#     ]}) 

# @app.route('/api/categories', methods=['GET'])
# def get_categories():
#     categories = Category.query.all()
#     return jsonify({'categories': [cat.name for cat in categories]})

# admin = db.relationship('User', backref='audit_logs')




# @api.route('/cart/items', methods=['GET'])
# @jwt_required()
# def get_cart_items():
#     user_id = get_jwt_identity()
#     cart = Cart.query.filter_by(user_id=user_id).first()
#     if not cart:
#         return jsonify({"message": "Cart is empty"}), 404
#     return jsonify([{
#         "product_id": item.product_id,
#         "name": item.product.name,
#         "price": item.product.price,
#         "quantity": item.quantity
#     } for item in cart.items]), 200


# @api.route('/cart/items', methods=['POST'])
# @jwt_required()
# def add_item_to_cart():
#     user_id = get_jwt_identity()
#     data = request.get_json()
#     cart = Cart.query.filter_by(user_id=user_id).first() or Cart(user_id=user_id)
#     product = Product.query.get(data['product_id'])
#     if not product or product.stock < data.get('quantity', 1):
#         return jsonify({"error": "Invalid product or insufficient stock"}), 400
#     cart_item = CartItem(
#         cart_id=cart.id,
#         product_id=data['product_id'],
#         quantity=data['quantity']
#     )
#     db.session.add(cart_item)
#     product.stock -= data['quantity']
    
#     return jsonify({"message": "Item added to cart"}), 201

# @app.route('/api/cart', methods=['POST'])
# @jwt_required()
# def add_to_cart():
#     user_id = get_jwt_identity()
#     data = request.get_json()

#     if 'product_id' not in data or 'quantity' not in data:
#         return jsonify({"error": "Missing product_id or quantity"}), 400

#     try:
#         product = db.session.execute(
#             select(Product)
#             .where(Product.id == data['product_id'])
#             .with_for_update()
#         ).scalar_one()

#         if product.stock < data['quantity']:
#             return jsonify({"error": "Insufficient stock"}), 400

#         cart = Cart.query.filter_by(user_id=user_id).first()
#         if not cart:
#             cart = Cart(user_id=user_id)
#             db.session.add(cart)

#         existing_item = next((i for i in cart.items if i.product_id == product.id), None)
#         if existing_item:
#             existing_item.quantity += data['quantity']
#         else:
#             cart_item = CartItem(cart_id=cart.id, product_id=product.id, quantity=data['quantity'])
#             db.session.add(cart_item)

#         # existing_item = next((i for i in cart.items if i.product_id == product.id), None)
#         # if existing_item:
#         #     existing_item.quantity += data['quantity']
#         # else:
#         #     cart.items.append(CartItem(
#         #         product_id=product.id,
#         #         quantity=data['quantity']
#         #     ))

#         product.stock -= data['quantity']
#         db.session.commit()
#         return jsonify({"message": "Item added to cart"}), 201

#     except Exception as e:
#         db.session.rollback()
#         return jsonify({"error": "Failed to update cart"}), 500


# @app.route('/api/dashboard', methods=['GET'])
# def get_dashboard():
#     categories = Category.query.all()
#     products = Product.query.limit(10).all()  # Get top 10 products
#     return jsonify({
#         'categories': [cat.name for cat in categories],
#         'featured_products': [{'id': p.id, 'name': p.name, 'price': p.price} for p in products]
#     })


# @app.route('/api/cart-summary', methods=['GET'])
# @jwt_required()
# def get_cart_summary():
#     user_id = get_jwt_identity()
#     cart_items = Cart.query.filter_by(user_id=user_id).all()
#     total_price = sum(item.product.price * item.quantity for item in cart_items)
#     return jsonify({'total_items': len(cart_items), 'total_price': total_price})


# @api.route('/payments/create', methods=['POST'])
# @jwt_required()
# def initialize_payment():
#     user_id = get_jwt_identity()
#     data = request.get_json()
#     if not all(key in data for key in ['card_number', 'expiry', 'cvv']):
#         return jsonify({"error": "Invalid payment details"}), 400
#     new_order = Order(
#         user_id=user_id,
#         total_amount=data['amount'],
#         status='pending'
#     )
#     new_payment = Payment(
#         order=new_order,
#         amount=data['amount'],
#         payment_method=data['payment_method'],
#         status='completed'
#     )
#     db.session.add_all([new_order, new_payment])
    
#     return jsonify({"message": "Payment processed successfully"}), 201


# @app.route('/api/orders/<int:order_id>/return', methods=['POST'])
# @jwt_required()
# def return_order(order_id):
#     user_id = get_jwt_identity()
#     order = Order.query.filter_by(id=order_id, user_id=user_id).first()
    
#     if not order:
#         return jsonify({"error": "Order not found"}), 404
    
#     if order.return_status is not None:
#         return jsonify({"error": "Order already returned"}), 400
    
#     # Check if the order is eligible for return (e.g., within 30 days)
#     if (datetime.utcnow() - order.created_at).days > 30:
#         return jsonify({"error": "Order return period has expired"}), 400
    
#     # Restore stock
#     for item in order.items:
#         product = Product.query.get(item.product_id)
#         if product: #
#             product.stock += item.quantity
    
#     order.return_status = 'returned'
    
    
#     return jsonify({"message": "Order returned successfully"})




# @app.route('/api/checkout', methods=['POST'])
# @jwt_required()
# def create_order():
#     user_id = get_jwt_identity()
#     user = User.query.get(user_id)

#     if not user.cart:
#         return jsonify({"error": "Cart is empty"}), 400

#     if not user.cart.items:
#         return jsonify({"error": "Cart is empty"}), 400  # Additional check

#     try:
#         db.session.begin_nested()  # Start nested transaction

#         total = 0
#         new_order = Order(user_id=user_id, status="pending_payment")
#         db.session.add(new_order)

#         for cart_item in user.cart.items:
#             product = db.session.execute(
#                 select(Product)
#                 .where(Product.id == cart_item.product_id)
#                 .with_for_update()  # Lock product row
#             ).scalar_one()

#             if product.stock < cart_item.quantity:
#                 db.session.rollback()
#                 return jsonify({"error": f"Insufficient stock for {product.name}"}), 400

#             total += cart_item.quantity * product.price
#             new_order.items.append(OrderItem(
#                 product_id=product.id,
#                 quantity=cart_item.quantity,
#                 price=product.price
#             ))
#             product.stock -= cart_item.quantity

#         new_order.total = total
#         CartItem.query.filter_by(cart_id=user.cart.id).delete()
#         db.session.commit()
#         return jsonify({"message": "Order created", "order_id": new_order.id}), 201

#     except Exception as e:
#         db.session.rollback()
#         return jsonify({"error": f"Checkout failed: {str(e)}"}), 500
    
# @app.route('/api/orders/<int:order_id>/cancel', methods=['POST'])
# @jwt_required()
# def cancel_order(order_id):
#     user_id = get_jwt_identity()
#     order = Order.query.filter_by(id=order_id, user_id=user_id).first()
#     if not order:
#         return jsonify({"error": "Order not found"}), 404

#     if order.status not in [OrderStatus.PENDING.value, OrderStatus.COMPLETED.value]:
#         return jsonify({"error": "Order cannot be cancelled"}), 400

#     # Restore stock
#     for item in order.items:
#         product = Product.query.get(item.product_id)
#         if product:
#             product.stock += item.quantity

#     order.status = OrderStatus.CANCELLED.value  # Ensure proper Enum usage
#     db.session.commit()

#     return jsonify({"message": "Order cancelled successfully"}), 200
