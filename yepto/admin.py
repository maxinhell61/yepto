from flask import Flask, jsonify, request, Blueprint, make_response
from flask_cors import CORS
from .config import Config  # Import the Config class from the correct module


from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt, JWTManager
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
from .models import db, Product, Category, Cart, CartItem, Order, Payment, OrderItem, User, OrderStatus

app = Flask(__name__)
CORS(app)


def admin_required(fn):
    @wraps(fn)  # Preserve function metadata
    @jwt_required()
    def wrapper(*args, **kwargs):
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user or not user.is_admin:  # Ensure user exists before checking is_admin
            return jsonify({"error": "Admin access required"}), 403
        return fn(*args, **kwargs)
    return wrapper

@app.route('/admin/orders', methods=['GET'])
@admin_required
def get_all_orders():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    orders = Order.query.paginate(page=page, per_page=per_page).items  # Extracting items

    return jsonify([{
        "id": order.id,
        "user_id": order.user_id,
        "total": order.total,
        "status": order.status.value,  # Ensuring proper Enum handling
        "created_at": order.created_at.isoformat()
    } for order in orders])

@app.route('/admin/orders/<int:order_id>', methods=['PUT'])
@admin_required
def update_order_status(order_id):

    data = request.get_json()

    order = Order.query.get(order_id)
    if not order:
        return jsonify({"error": "Order not found"}), 404
    valid_statuses = [status.value for status in OrderStatus]
    if data['status'] not in valid_statuses:
        return jsonify({"error": "Invalid status"}), 400
    if data['status'] not in valid_statuses:
        return jsonify({"error": "Invalid status"}), 400
    
    order.status = data['status']
    
    return jsonify({"message": "Order updated"}) 

 



@app.route('/admin/dashboard/sales', methods=['GET'])
@admin_required
def get_sales_report():
    total_sales = db.session.query(db.func.sum(Order.total)).filter(Order.status == 'completed').scalar() or 0
    return jsonify({"total_sales": total_sales})

@app.route('/admin/dashboard/orders', methods=['GET'])
@admin_required
def get_order_count():
    total_orders = Order.query.count()
    return jsonify({"total_orders": total_orders})

@app.route('/admin/dashboard/users', methods=['GET'])
@admin_required
def get_user_count():
    total_users = User.query.count()
    return jsonify({"total_users": total_users})


@app.route('/admin/users', methods=['GET'])
@admin_required
def get_all_users():
    users = User.query.all()
    return jsonify([{
        "id": user.id,
        "email": user.email,
        "is_admin": user.is_admin
    } for user in users])

@app.route('/admin/users/<int:user_id>/promote', methods=['POST'])
@admin_required
def promote_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User  not found"}), 404
    
    user.is_admin = True
    
    return jsonify({"message": f"User  {user_id} promoted to admin"})

@app.route('/admin/users/<int:user_id>/deactivate', methods=['POST'])
@admin_required
def deactivate_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User  not found"}), 404
    
    db.session.delete(user)
    
    return jsonify({"message": f"User  {user_id} deactivated"})
