from flask import Flask,redirect,url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from yepto.config import Config
from yepto.models import db
from yepto.routes import routes
from yepto.auth import auth
from yepto.admin import admin  # Importing admin blueprint

from yepto.orders import orders  # Add this
app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
Migrate(app, db)
JWTManager(app)
CORS(app)

# Register blueprints
app.register_blueprint(routes, url_prefix="/api")  # Registering routes blueprint

app.register_blueprint(auth, url_prefix="/api/auth")  # Registering auth blueprint

app.register_blueprint(admin, url_prefix="/api/admin")  # Registering admin blueprint

app.register_blueprint(orders, url_prefix="/api/orders")  # Registering orders blueprint



# @app.route('/')
# def home():
#     return redirect(url_for(login))


if __name__ == "__main__":
    app.run(debug=True)






git status
git add yepto/
git add .
git commit -m "Updated complete yepto folder"
git push origin main
























# from flask import Flask
# from flask_sqlalchemy import SQLAlchemy
# from flask_migrate import Migrate
# from flask_jwt_extended import JWTManager
# from flask_cors import CORS
# from config import Config
# from models import db




# def create_app():
#     app = Flask(__name__)
#     app.config.from_object(Config)

#     db.init_app(app)
#     Migrate(app, db)
#     JWTManager(app)
#     CORS(app)

#     return app














# # app = Flask(__name__)
# # app.config.from_object(Config)

# # # Initialize extensions

# # migrate = Migrate(app, db)
# # jwt = JWTManager(app)
# # CORS(app)


# # db.init_app(app)
# # migrate = Migrate(app, db)

# # with app.app_context():
# #     db.create_all()  # Ensures tables are created

# # if __name__ == "__main__":
# #     app.run(debug=True)
