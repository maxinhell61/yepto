from flask import Flask, Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt, JWTManager
from .models import db, User,Cart

app = Flask(__name__)


@app.route('/auth/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data or 'email' not in data or 'password' not in data or 'username' not in data:
        return jsonify({"error": "Missing email, username, or password"}), 400

    if User.query.filter_by(email=data['email']).first():
        return jsonify({"error": "Email exists"}), 409
    
    try:
        user = User(
            username=data['username'],
            email=data['email'],
            password=generate_password_hash(data['password']),
            is_admin=False  # Explicitly set as False
        )
        db.session.add(user)
        db.session.commit()  # Commit to get user.id
        
        # Create a cart for the new user
        cart = Cart(user_id=user.id)
        db.session.add(cart)
        db.session.commit()
        
        return jsonify({"message": "User created"}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Registration failed"}), 500


@app.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json()
    user = User.query.filter_by(email=data['email']).first()

    if not user or not check_password_hash(user.password, data['password']):
        return jsonify({"error": "Invalid credentials"}), 401

    access_token = create_access_token(identity=user.id)
    return jsonify(access_token=access_token), 200

# app.register_blueprint(api)  


revoked_tokens = set()


@app.route('/auth/logout', methods=['POST'])
@jwt_required()
def logout_user():
    jti = get_jwt()['jti']
    revoked_tokens.add(jti)
    return jsonify({"message": "Successfully logged out"}), 200