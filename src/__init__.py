from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
from flask_login import LoginManager  # <--- NOWE: Import biblioteki logowania
from .config import Config

# Inicjalizacja instancji rozszerzeń
db = SQLAlchemy()
mail = Mail()
login_manager = LoginManager()  # <--- NOWE: Tworzymy menedżera logowania


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    mail.init_app(app)

    login_manager.init_app(app)

    login_manager.login_view = 'main.login'
    login_manager.login_message_category = 'info'


    from . import models
    from .blueprints import auth
    from .blueprints import main
    from .blueprints import transactions
    from .blueprints import budgets
    from .blueprints import categories

    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(transactions.bp)
    app.register_blueprint(budgets.bp)
    app.register_blueprint(categories.bp)


    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    with app.app_context():
        pass

    return app