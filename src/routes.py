from decimal import Decimal
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from . import db
from .models import User, Household, HouseholdMember, SubBudget, Category, Transaction

bp = Blueprint("main", __name__)


@bp.context_processor
def inject_user():
    user = None
    if "user_id" in session:
        user = db.session.get(User, session["user_id"])
    return dict(current_user=user)


# Pomocnik: pobierz aktualnie zalogowanego usera
def get_current_user():
    if "user_id" in session:
        return db.session.get(User, session["user_id"])
    return None


@bp.route("/")
def index():
    user = get_current_user()
    if not user:
        return redirect(url_for("main.login"))

    # Pobierz gospodarstwo usera
    member = HouseholdMember.query.filter_by(id_uzytkownika=user.id).first()
    if not member:
        return "Błąd: Brak gospodarstwa. (Błąd spójności danych)"

    household_id = member.id_gospodarstwa

    # 1. Pobierz podbudżety i oblicz łączne saldo
    budgets = SubBudget.query.filter_by(id_gospodarstwa=household_id).all()
    total_saldo = sum(b.saldo for b in budgets)

    # 2. Pobierz ostatnie 5 transakcji
    recent_transactions = (
        Transaction.query.filter(
            Transaction.podbudzet.has(id_gospodarstwa=household_id)
        )
        .order_by(Transaction.data.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "dashboard.html", user=user, saldo=total_saldo, transakcje=recent_transactions
    )


@bp.route("/add_transaction", methods=["GET", "POST"])
def add_transaction():
    user = get_current_user()
    if not user:
        return redirect(url_for("main.login"))

    member = HouseholdMember.query.filter_by(id_uzytkownika=user.id).first()
    household_id = member.id_gospodarstwa

    if request.method == "POST":
        nazwa = request.form.get("nazwa")

        # --- POPRAWKA TUTAJ ---
        # Zmieniamy float na Decimal, żeby pasowało do typu w bazie Oracle
        kwota = Decimal(request.form.get("kwota"))
        # ----------------------

        typ = request.form.get("typ")
        cat_id = request.form.get("kategoria")
        bud_id = request.form.get("podbudzet")

        # Logika biznesowa: Aktualizacja salda
        budget = db.session.get(SubBudget, bud_id)

        if typ == "Wydatek":
            budget.saldo -= kwota  # Teraz: Decimal - Decimal (Działa!)
        else:
            budget.saldo += kwota

        # Zapis transakcji
        new_trans = Transaction(
            id_uzytkownika=user.id,
            id_podbudzetu=bud_id,
            id_kategorii=cat_id,
            typ=typ,
            nazwa=nazwa,
            kwota=kwota,
            data=datetime.utcnow(),
        )

        db.session.add(new_trans)
        db.session.commit()

        flash("Transakcja dodana pomyślnie!")
        return redirect(url_for("main.index"))

    # GET: Pobierz listy do dropdownów
    categories = Category.query.filter_by(id_gospodarstwa=household_id).all()
    budgets = SubBudget.query.filter_by(id_gospodarstwa=household_id).all()

    return render_template(
        "add_transaction.html", categories=categories, budgets=budgets
    )

    # GET: Pobierz listy do dropdownów
    categories = Category.query.filter_by(id_gospodarstwa=household_id).all()
    budgets = SubBudget.query.filter_by(id_gospodarstwa=household_id).all()

    return render_template(
        "add_transaction.html", categories=categories, budgets=budgets
    )


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
        db.session.flush()

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

        # --- NOWOŚĆ: AUTOMATYCZNE TWORZENIE DANYCH STARTOWYCH ---
        # Żebyś nie musiał ręcznie odpalać seed_data.py dla każdego nowego usera

        # A. Domyślny portfel
        wallet = SubBudget(
            id_gospodarstwa=new_household.id, nazwa="Portfel Główny", saldo=0.00
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
        # --------------------------------------------------------

        db.session.commit()  # Zapisujemy wszystko w Oracle RAZ

        flash("Zarejestrowano pomyślnie. Zaloguj się.")
        return redirect(url_for("main.login"))

    return render_template("register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.haslo_hash, password):
            session["user_id"] = user.id  # ZAPISUJEMY SESJĘ!
            return redirect(url_for("main.index"))
        else:
            flash("Błąd logowania")

    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("main.login"))


@bp.route("/history")
def history():
    user = get_current_user()
    if not user:
        return redirect(url_for("main.login"))

    # Pobierz ID gospodarstwa
    member = HouseholdMember.query.filter_by(id_uzytkownika=user.id).first()

    # Pobierz WSZYSTKIE transakcje, sortuj od najnowszych
    all_transactions = (
        Transaction.query.filter(
            Transaction.podbudzet.has(id_gospodarstwa=member.id_gospodarstwa)
        )
        .order_by(Transaction.data.desc())
        .all()
    )

    return render_template("history.html", transakcje=all_transactions)


@bp.route("/categories", methods=["GET", "POST"])
def categories():
    user = get_current_user()
    if not user:
        return redirect(url_for("main.login"))

    member = HouseholdMember.query.filter_by(id_uzytkownika=user.id).first()

    if request.method == "POST":
        nazwa = request.form.get("nazwa")
        opis = request.form.get("opis")

        # ZMIANA: Nie pobieramy typu z formularza.
        # Ustawiamy na sztywno "Ogólna", żeby pasowała do wszystkiego.
        typ = "Ogólna"

        # Sprawdź czy taka już nie istnieje
        exists = Category.query.filter_by(
            id_gospodarstwa=member.id_gospodarstwa, nazwa=nazwa
        ).first()

        if not exists:
            new_cat = Category(
                id_gospodarstwa=member.id_gospodarstwa, nazwa=nazwa, opis=opis, typ=typ
            )
            db.session.add(new_cat)
            db.session.commit()
            flash(f"Dodano kategorię: {nazwa}")
        else:
            flash("Taka kategoria już istnieje!")

        return redirect(url_for("main.categories"))

    # Wyświetlanie listy
    cats = Category.query.filter_by(id_gospodarstwa=member.id_gospodarstwa).all()
    return render_template("categories.html", categories=cats)
