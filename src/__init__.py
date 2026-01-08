from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail  # <--- IMPORT
from .config import Config

db = SQLAlchemy()
mail = Mail()  # <--- TWORZYMY OBIEKT MAIL


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    mail.init_app(app)  

    from . import models
    from . import routes

    app.register_blueprint(routes.bp)

    with app.app_context():
        pass

    return app
