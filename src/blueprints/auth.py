from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from flask_mail import Message
from ..models import User, Household, HouseholdMember, SubBudget, Category
from .. import db, mail

bp = Blueprint("auth", __name__)

@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        name = request.form.get("name")
        household_name = request.form.get("household_name")
        invite_code = request.form.get("invite_code")  # NOWE: Kod zaproszenia

        user_exists = User.query.filter_by(email=email).first()
        if user_exists:
            flash("Ten email jest już zajęty.")
            return redirect(url_for("auth.register"))

        # 1. Tworzymy usera
        new_user = User(
            email=email,
            nazwa_uzytkownika=name,
            haslo_hash = generate_password_hash(password, method='pbkdf2:sha256')
        )
        db.session.add(new_user)
        db.session.flush()

        # 2. Obsługa Gospodarstwa (Nowe lub Istniejące)
        target_household_id = None
        is_admin = True # Domyślnie admin, chyba że dołącza

        if invite_code:
            # Próba dekodowania tokenu
            s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
            try:
                # Odkoduj ID gospodarstwa (zakładamy, że token jest trwały lub ma długi czas życia, np. 7 dni)
                # Możesz ustawić max_age=None jeśli kody mają być wieczne
                target_household_id = s.loads(invite_code, salt="invite-code")
                
                # Sprawdź czy takie gospodarstwo istnieje
                household = db.session.get(Household, target_household_id)
                if not household:
                    flash("Nieprawidłowy kod zaproszenia (gospodarstwo nie istnieje).", "danger")
                    return redirect(url_for("auth.register"))
                
                is_admin = False # Dołączający nie jest adminem (opcjonalnie)
                flash(f"Dołączasz do gospodarstwa: {household.nazwa_gospodarstwa}", "info")

            except (SignatureExpired, BadSignature):
                flash("Kod zaproszenia jest nieprawidłowy lub wygasł.", "warning")
                return redirect(url_for("auth.register"))
        
        else:
            # Tworzymy nowe gospodarstwo (standardowa ścieżka)
            if not household_name:
                flash("Podaj nazwę gospodarstwa.", "warning")
                return redirect(url_for("auth.register"))
                
            new_household = Household(
                nazwa_gospodarstwa=household_name,
                wlasciciel_id=new_user.id,
            )
            db.session.add(new_household)
            db.session.flush()
            target_household_id = new_household.id

            # --- AUTOMATYCZNE TWORZENIE DANYCH STARTOWYCH (Tylko dla nowego domu) ---
            
            # A. Domyślny budżet
            wallet = SubBudget(
                id_gospodarstwa=new_household.id, nazwa="Budżet Główny", saldo=0.00
            )
            db.session.add(wallet)

            # B. Domyślne kategorie
            kategorie = [
                ("Jedzenie", "Artykuły spożywcze", "Wydatek"),
                ("Transport", "Paliwo, bilety", "Wydatek"),
                ("Rozrywka", "Kino, gry", "Wydatek"),
                ("Rachunki", "Prąd, gaz", "Wydatek"),
                ("Pensja", "Wypłata", "Wplyw"),
            ]
            for k_nazwa, k_opis, k_typ in kategorie:
                cat = Category(
                    id_gospodarstwa=new_household.id, nazwa=k_nazwa, opis=k_opis, typ=k_typ
                )
                db.session.add(cat)
            # ------------------------------------------------------------------------

        # 3. Przypisujemy usera do gospodarstwa
        member = HouseholdMember(
            id_gospodarstwa=target_household_id,
            id_uzytkownika=new_user.id,
            czy_uprawnienia_admina=is_admin,
        )
        db.session.add(member)

        db.session.commit()
        flash("Zarejestrowano pomyślnie. Zaloguj się.")
        return redirect(url_for("auth.login"))

    return render_template("register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.haslo_hash, password):
            login_user(user, remember=True)
            return redirect(url_for("main.index")) # Zakładamy że index będzie w main
        else:
            flash("Błąd logowania")

    return render_template("login.html")


@bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


def send_reset_email(user):
    s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    token = s.dumps(user.email, salt="email-confirm")

    msg = Message(
        "Reset Hasła - Budżet Domowy",
        sender="twoj.adres@gmail.com",
        recipients=[user.email],
    )
    link = url_for("auth.reset_token", token=token, _external=True)

    msg.body = f"""Witaj {user.nazwa_uzytkownika},

Aby zresetować hasło, kliknij w poniższy link:
{link}

Jeśli to nie Ty prosiłeś o reset, zignoruj tę wiadomość.
"""
    try:
        mail.send(msg)
    except Exception as e:
        print(f"Błąd wysyłania maila: {e}")


@bp.route("/reset_password", methods=["GET", "POST"])
def reset_request():
    if request.method == "POST":
        email = request.form.get("email")
        user = User.query.filter_by(email=email).first()
        if user:
            send_reset_email(user)
        flash("Jeśli konto istnieje, wysłaliśmy instrukcję na email.", "info")
        return redirect(url_for("auth.login"))
    return render_template("reset_request.html")


@bp.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_token(token):
    s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    try:
        email = s.loads(token, salt="email-confirm", max_age=3600)
    except Exception as e:
        print(f"Błąd tokena: {e}")
        flash("Link jest nieprawidłowy lub wygasł.", "danger")
        return redirect(url_for("auth.reset_request"))

    if request.method == "POST":
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()
        if user:
            user.haslo_hash = generate_password_hash(password)
            db.session.commit()
            flash("Twoje hasło zostało zmienione! Możesz się zalogować.", "success")
            return redirect(url_for("auth.login"))

    return render_template("reset_token.html")
