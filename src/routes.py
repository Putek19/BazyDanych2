from flask import Blueprint, render_template, redirect, url_for, flash, request
from werkzeug.security import generate_password_hash, check_password_hash
from . import db
from .models import User, Household, HouseholdMember

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    return render_template("base.html")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        name = request.form.get("name")
        household_name = request.form.get("household_name")

        user_exists = User.query.filter_by(email=email).first()
        if user_exists:
            flash("Ten email jest już zajęty.")
            return redirect(url_for("main.register"))

        # 1. Tworzymy usera
        new_user = User(
            email=email,
            nazwa_uzytkownika=name,
            haslo_hash=generate_password_hash(password),
        )
        db.session.add(new_user)
        db.session.flush()  # Nadaje ID przed zapisem do bazy

        # 2. Tworzymy gospodarstwo
        new_household = Household(
            nazwa_gospodarstwa=household_name,
            wlasciciel_id=new_user.id,
        )
        db.session.add(new_household)
        db.session.flush()

        # 3. Przypisujemy usera do gospodarstwa
        member = HouseholdMember(
            id_gospodarstwa=new_household.id,
            id_uzytkownika=new_user.id,
            czy_uprawnienia_admina=True,
        )
        db.session.add(member)

        db.session.commit()  # Zapisujemy wszystko w Oracle

        flash("Konto utworzone! Zaloguj się.")
        return redirect(url_for("main.login"))

    return render_template("register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.haslo_hash, password):
            flash(f"Witaj, {user.nazwa_uzytkownika}!")
            return redirect(url_for("main.index"))
        else:
            flash("Błędne dane.")

    return render_template("login.html")
