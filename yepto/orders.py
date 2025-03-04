from flask import Flask,Blueprint, request, jsonify
from sqlalchemy import select
from flask_jwt_extended import jwt_required, get_jwt_identity
from .models import db, Order, OrderItem, Cart, CartItem, Product, Payment
from datetime import datetime

app = Flask(__name__)

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
        if product:
            product.stock += item.quantity
    
    order.return_status = 'returned'
    
    db.session.commit()  # Commit the session after updating the order
    return jsonify({"message": "Order returned successfully"})





@app.route("/checkout", methods=["POST"])
@jwt_required()
def create_order():
    user_id = get_jwt_identity()
    user_cart = Cart.query.filter_by(user_id=user_id).first()

    if not user_cart or not user_cart.items:
        return jsonify({"error": "Cart is empty"}), 400

    try:
        db.session.begin_nested()  # Start nested transaction

        total = 0
        new_order = Order(user_id=user_id, status="pending_payment")
        db.session.add(new_order)

        for cart_item in user_cart.items:
            product = db.session.execute(
                select(Product).where(Product.id == cart_item.product_id).with_for_update()
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
        CartItem.query.filter_by(cart_id=user_cart.id).delete()
        db.session.commit()
        return jsonify({"message": "Order created", "order_id": new_order.id}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Checkout failed: {str(e)}"}), 500

@app.route("/payments/process", methods=["POST"])
@jwt_required()
def process_payment():
    data = request.get_json()
    
    if 'order_id' not in data or 'payment_method' not in data:
        return jsonify({"error": "Missing order_id or payment_method"}), 400

    try:
        order = db.session.execute(
            select(Order).where(Order.id == data['order_id']).with_for_update()
        ).scalar_one()

        if order.user_id != get_jwt_identity():
            return jsonify({"error": "Unauthorized access"}), 403

        if order.status.value != "pending_payment":
            return jsonify({"error": "Payment already processed"}), 400

        if data['payment_method'] == 'card':
            order.status = "completed"
            new_payment = Payment(
                order_id=order.id,
                amount=order.total,
                payment_method=data['payment_method'],
                status="completed"
            )
            db.session.add(new_payment)
            db.session.commit()
            return jsonify({"message": "Payment successful"}), 200

        return jsonify({"error": "Unsupported payment method"}), 400

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Payment failed: {str(e)}"}), 500



@app.route('/payments/create', methods=['POST'])
@jwt_required()
def initialize_payment():
    user_id = get_jwt_identity()
    data = request.get_json()
    if not all(key in data for key in ['card_number', 'expiry', 'cvv', 'amount']):
        return jsonify({"error": "Invalid payment details"}), 400
    new_order = Order(
        user_id=user_id,
        total_amount=data['amount'],
        status='pending'
    )
    new_payment = Payment(
        order=new_order,
        amount=data['amount'],
        payment_method=data['payment_method'],
        status='completed'
    )
    db.session.add_all([new_order, new_payment])
    db.session.commit()  # Commit the session after adding the order and payment
    return jsonify({"message": "Payment processed successfully"}), 201
