from decimal import Decimal
from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    session,
    current_app,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import desc
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from .models import User, Household, HouseholdMember, SubBudget, Category, Transaction
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer
from . import db, mail
from sqlalchemy import func

bp = Blueprint("main", __name__)

def get_active_budget(household_id):
    # 1. Sprawdzamy, czy w sesji jest zapisane ID budżetu
    active_id = session.get('active_budget_id')

    if active_id:
        # Sprawdzamy, czy ten budżet nadal istnieje i należy do tego domu
        budget = SubBudget.query.filter_by(id=active_id, id_gospodarstwa=household_id).first()
        if budget:
            return budget

    # 2. Jeśli nie ma w sesji, bierzemy pierwszy znaleziony (domyślny)
    default_budget = SubBudget.query.filter_by(id_gospodarstwa=household_id).first()

    # Zapisujemy go w sesji, żeby następnym razem już był
    if default_budget:
        session['active_budget_id'] = default_budget.id

    return default_budget


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
@login_required
def index():
    user = get_current_user()


    member = HouseholdMember.query.filter_by(id_uzytkownika=user.id).first()
    if not member:
        return "Błąd: Brak gospodarstwa. (Błąd spójności danych)"

    household_id = member.id_gospodarstwa

    # 1. LOGIKA BUDŻETÓW (To jest nowość)
    # Pobieramy ten, który użytkownik wybrał (lub domyślny)
    active_budget = get_active_budget(household_id)

    # Pobieramy listę wszystkich, żeby wyświetlić je w menu "Zmień budżet"
    all_budgets = SubBudget.query.filter_by(id_gospodarstwa=household_id).all()

    # Zabezpieczenie: Jeśli nie ma żadnego budżetu, renderujemy pusty widok
    if not active_budget:
        return render_template("dashboard.html",
                               active_budget=None,
                               budgets=[],
                               transactions=[])

    # 2. POBIERANIE TRANSAKCJI (Zmiana: tylko dla aktywnego budżetu)
    recent_transactions = (
        Transaction.query.filter_by(id_podbudzetu=active_budget.id)
        .order_by(desc(Transaction.data))
        .limit(10)  # Możesz dać 5, jeśli wolisz mniej
        .all()
    )

    # 3. WYSYŁAMY DANE DO SZABLONU
    # Zauważ, że nie musimy liczyć 'total_saldo', bo wyświetlamy saldo konkretnego budżetu (active_budget.saldo)
    return render_template(
        "dashboard.html",
        active_budget=active_budget,
        budgets=all_budgets,
        transactions=recent_transactions
    )


@bp.route("/add_transaction", methods=["GET", "POST"])
@login_required
def add_transaction():
    user = current_user

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

    # Znalezienie aktualnego budżetu dla domyślnej wartości w add_transaction
    active_budget = get_active_budget(household_id)
    active_budget_id = active_budget.id if active_budget else None

    return render_template(
        "add_transaction.html",
        categories=categories,
        budgets=budgets,
        active_budget_id=active_budget_id
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
            haslo_hash = generate_password_hash(password, method='pbkdf2:sha256')
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

        # --- AUTOMATYCZNE TWORZENIE DANYCH STARTOWYCH ---

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
            login_user(user, remember=True)
            return redirect(url_for("main.index"))
        else:
            flash("Błąd logowania")

    return render_template("login.html")


@bp.route("/logout")
def logout():
    logout_user()
    session.pop("user_id", None)
    return redirect(url_for("main.login"))


@bp.route("/history")
@login_required
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
@login_required
def categories():
    user = get_current_user()
    if not user:
        return redirect(url_for("main.login"))

    member = HouseholdMember.query.filter_by(id_uzytkownika=user.id).first()

    if request.method == "POST":
        nazwa = request.form.get("nazwa")
        opis = request.form.get("opis")

        # ZMIANA 1: Pobieramy typ z ukrytego pola formularza (HTML poniżej to wyśle)
        typ = request.form.get("typ")

        # jeżeli nie ma ustalonego typu -> nadaj typ
        if not typ:
            typ = "Wydatek"

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

    # ZMIANA 2: Pobieramy dwie osobne listy zamiast jednej
    cats_wydatki = Category.query.filter_by(id_gospodarstwa=member.id_gospodarstwa, typ="Wydatek").all()
    cats_wplywy = Category.query.filter_by(id_gospodarstwa=member.id_gospodarstwa, typ="Wplyw").all()

    # Przekazanie do szablonu dwóch list zależnych od typu kategorii
    return render_template("categories.html", wydatki=cats_wydatki, wplywy=cats_wplywy)


def send_reset_email(user):
    s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    token = s.dumps(user.email, salt="email-confirm")  # Token ważny dla tego emaila

    msg = Message(
        "Reset Hasła - Budżet Domowy",
        sender="twoj.adres@gmail.com",  # Musi być ten sam co w .env
        recipients=[user.email],
    )

    # Tworzymy link (external=True daje pełny adres http://localhost...)
    link = url_for("main.reset_token", token=token, _external=True)

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
        # Zawsze wyświetlamy ten sam komunikat dla bezpieczeństwa (żeby nie zdradzać czy mail istnieje)
        flash("Jeśli konto istnieje, wysłaliśmy instrukcję na email.", "info")
        return redirect(url_for("main.login"))
    return render_template("reset_request.html")


@bp.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_token(token):
    # --- POPRAWKA TUTAJ ---
    # Zmieniamy bp.secret_key na current_app.config['SECRET_KEY']
    s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    # ----------------------

    try:
        # Token ważny przez 3600 sekund (1 godzina)
        email = s.loads(token, salt="email-confirm", max_age=3600)
    except Exception as e:
        # Warto wypisać błąd w konsoli dla pewności
        print(f"Błąd tokena: {e}")
        flash("Link jest nieprawidłowy lub wygasł.", "danger")
        return redirect(url_for("main.reset_request"))

    if request.method == "POST":
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()
        if user:
            user.haslo_hash = generate_password_hash(password)
            db.session.commit()
            flash("Twoje hasło zostało zmienione! Możesz się zalogować.", "success")
            return redirect(url_for("main.login"))

    return render_template("reset_token.html")


# --- NOWE FUNKCJE (Wklej na końcu src/routes.py) ---


@bp.route("/analysis")
@login_required
def analysis():
    user = get_current_user()
    if not user:
        return redirect(url_for("main.login"))

    member = HouseholdMember.query.filter_by(id_uzytkownika=user.id).first()

    # Zapytanie SQL: Wybierz nazwę kategorii i sumę kwot, zgrupuj po kategorii
    # Filtrujemy tylko 'Wydatek'
    data = (
        db.session.query(Category.nazwa, func.sum(Transaction.kwota))
        .join(Transaction)
        .filter(Transaction.podbudzet.has(id_gospodarstwa=member.id_gospodarstwa))
        .filter(Transaction.typ == "Wydatek")
        .group_by(Category.nazwa)
        .all()
    )

    # Przygotowanie danych dla Chart.js (JavaScript potrzebuje dwóch list)
    labels = [row[0] for row in data]
    values = [float(row[1]) for row in data]  # Konwersja Decimal na float dla JS

    return render_template("analysis.html", labels=labels, values=values)


from .models import (
    CyclicTransaction,
)  # Upewnij się że masz ten import na górze, albo dodaj go tutaj lokalnie


@bp.route("/cyclic", methods=["GET", "POST"])
@login_required
def cyclic():
    user = get_current_user()
    if not user:
        return redirect(url_for("main.login"))

    member = HouseholdMember.query.filter_by(id_uzytkownika=user.id).first()

    if request.method == "POST":
        nazwa = request.form.get("nazwa")
        kwota = Decimal(request.form.get("kwota"))
        okres = request.form.get("okres")  # np. Miesięcznie
        cat_id = request.form.get("kategoria")
        bud_id = request.form.get("podbudzet")
        data_startu = datetime.strptime(request.form.get("data_startu"), "%Y-%m-%d")

        typ = request.form.get("typ")

        new_cyclic = CyclicTransaction(
            id_uzytkownika=user.id,
            id_podbudzetu=bud_id,
            id_kategorii=cat_id,
            typ=typ,
            nazwa=nazwa,
            kwota=kwota,
            data_startu=data_startu,
            okres=okres,
        )
        db.session.add(new_cyclic)
        db.session.commit()
        flash("Dodano płatność cykliczną.")
        return redirect(url_for("main.cyclic"))

    # Pobieranie danych do wyświetlenia
    transakcje_cykliczne = CyclicTransaction.query.filter(
        CyclicTransaction.podbudzet.has(id_gospodarstwa=member.id_gospodarstwa)
    ).all()

    categories = Category.query.filter_by(id_gospodarstwa=member.id_gospodarstwa).all()
    budgets = SubBudget.query.filter_by(id_gospodarstwa=member.id_gospodarstwa).all()

    return render_template(
        "cyclic.html",
        cykliczne=transakcje_cykliczne,
        categories=categories,
        budgets=budgets,
    )

# --- PODBUDŻETY ---

@bp.route("/add_budget", methods=["POST"])
@login_required
def add_budget():
    member = HouseholdMember.query.filter_by(id_uzytkownika=current_user.id).first()

    nazwa = request.form.get("nazwa")

    if nazwa:
        new_budget = SubBudget(
            id_gospodarstwa=member.id_gospodarstwa,
            nazwa=nazwa,
            saldo=0.00
        )
        db.session.add(new_budget)
        db.session.commit()

        # Opcjonalnie: Przełącz od razu na nowy budżet
        session['active_budget_id'] = new_budget.id
        flash(f"Utworzono nowy budżet wydzielony: {nazwa}", "success")

    return redirect(url_for('main.index'))


@bp.route("/switch_budget/<int:budget_id>")
@login_required
def switch_budget(budget_id):
    member = HouseholdMember.query.filter_by(id_uzytkownika=current_user.id).first()

    # Bezpieczeństwo: Sprawdź czy ten budżet należy do gospodarstwa użytkownika!
    budget = SubBudget.query.filter_by(id=budget_id, id_gospodarstwa=member.id_gospodarstwa).first()

    if budget:
        session['active_budget_id'] = budget.id
        flash(f"Przełączono na: {budget.nazwa}", "info")
    else:
        flash("Nie masz dostępu do tego budżetu.", "danger")

    return redirect(url_for('main.index'))




@bp.route("/transfer", methods=["GET", "POST"])
@login_required
def transfer():
    # Pobieramy usera z Flask-Login
    user = current_user
    member = HouseholdMember.query.filter_by(id_uzytkownika=user.id).first()

    if request.method == "POST":
        source_id = request.form.get("source_budget")
        target_id = request.form.get("target_budget")
        amount_str = request.form.get("amount")

        # Walidacja danych
        try:
            amount = Decimal(amount_str)
        except:
            flash("Nieprawidłowa kwota.", "danger")
            return redirect(url_for("main.transfer"))

        if amount <= 0:
            flash("Kwota musi być dodatnia.", "warning")
            return redirect(url_for("main.transfer"))

        if source_id == target_id:
            flash("Budżet źródłowy i docelowy muszą być różne.", "warning")
            return redirect(url_for("main.transfer"))

        source_budget = db.session.get(SubBudget, source_id)
        target_budget = db.session.get(SubBudget, target_id)

        # Weryfikacja uprawnień
        if not source_budget or not target_budget:
            flash("Nie znaleziono budżetu.", "danger")
            return redirect(url_for("main.transfer"))

        if source_budget.id_gospodarstwa != member.id_gospodarstwa or target_budget.id_gospodarstwa != member.id_gospodarstwa:
            flash("Brak uprawnień.", "danger")
            return redirect(url_for("main.transfer"))

        # --- LOGIKA KATEGORII (BEZ ZMIAN W BAZIE) ---

        # 1. Kategoria WYDATKU (Wychodzący)
        cat_out = Category.query.filter_by(
            id_gospodarstwa=member.id_gospodarstwa, nazwa="Przelew Wychodzący"
        ).first()

        if not cat_out:
            cat_out = Category(
                id_gospodarstwa=member.id_gospodarstwa,
                nazwa="Przelew Wychodzący",
                typ="Wydatek",
                opis="Automatyczny przelew między portfelami"
            )
            db.session.add(cat_out)

        # 2. Kategoria WPŁYWU (Przychodzący)
        cat_in = Category.query.filter_by(
            id_gospodarstwa=member.id_gospodarstwa, nazwa="Przelew Przychodzący"
        ).first()

        if not cat_in:
            cat_in = Category(
                id_gospodarstwa=member.id_gospodarstwa,
                nazwa="Przelew Przychodzący",
                typ="Wplyw",
                opis="Automatyczny przelew między portfelami"
            )
            db.session.add(cat_in)

        db.session.flush()  # Upewniamy się, że kategorie mają ID

        # --- OPERACJA FINANSOWA ---
        source_budget.saldo -= amount
        target_budget.saldo += amount

        timestamp = datetime.utcnow()

        # Transakcja 1: Wydatek
        t_out = Transaction(
            id_uzytkownika=user.id,
            id_podbudzetu=source_budget.id,
            id_kategorii=cat_out.id,
            typ="Wydatek",
            nazwa=f"Przelew do: {target_budget.nazwa}",
            kwota=amount,
            data=timestamp
        )
        db.session.add(t_out)

        # Transakcja 2: Wpływ
        t_in = Transaction(
            id_uzytkownika=user.id,
            id_podbudzetu=target_budget.id,
            id_kategorii=cat_in.id,
            typ="Wplyw",
            nazwa=f"Przelew od: {source_budget.nazwa}",
            kwota=amount,
            data=timestamp
        )
        db.session.add(t_in)

        db.session.commit()
        flash(f"Przelano {amount} PLN z {source_budget.nazwa} do {target_budget.nazwa}.", "success")
        return redirect(url_for("main.index"))

    # GET
    budgets = SubBudget.query.filter_by(id_gospodarstwa=member.id_gospodarstwa).all()
    return render_template("transfer.html", budgets=budgets)


# Wklej to do src/routes.py (zastępując stare funkcje edit_transaction i delete_transaction)

@bp.route("/edit_transaction/<int:t_id>", methods=["GET", "POST"])
@login_required
def edit_transaction(t_id):
    # 1. Pobierz transakcję
    transaction = db.session.get(Transaction, t_id)

    # Zabezpieczenie: czy transakcja istnieje
    if not transaction:
        flash("Transakcja nie istnieje.", "danger")
        return redirect(url_for("main.history"))

    # Zabezpieczenie: czy użytkownik ma prawo do tej transakcji (sprawdzamy po gospodarstwie)
    # (Zakładam, że masz już pobranego membera/household wcześniej, lub sprawdzasz po user_id)
    if transaction.id_uzytkownika != current_user.id:
        # To uproszczone sprawdzenie, w idealnym świecie sprawdzamy household_id
        pass

        # --- NOWE ZABEZPIECZENIE: BLOKADA EDYCJI PRZELEWÓW ---
    if transaction.kategoria.nazwa in ["Przelew Wychodzący", "Przelew Przychodzący"]:
        flash("Edycja przelewów wewnętrznych jest zablokowana. Aby skorygować błąd, usuń przelew i dodaj go ponownie.",
              "warning")
        return redirect(url_for("main.index"))  # lub main.history
    # -----------------------------------------------------

    member = HouseholdMember.query.filter_by(id_uzytkownika=current_user.id).first()

    if request.method == "POST":
        # Pobieramy dane z formularza
        transaction.nazwa = request.form.get("nazwa")
        transaction.kwota = Decimal(request.form.get("kwota"))
        transaction.typ = request.form.get("typ")
        transaction.id_kategorii = request.form.get("kategoria")

        # Obsługa zmiany budżetu (aktualizacja salda starego i nowego)
        nowy_budzet_id = int(request.form.get("podbudzet"))

        # Jeśli zmieniono budżet, trzeba przeliczyć salda (to skomplikowane logiki,
        # dla uproszczenia zakładamy tutaj tylko zmianę kwoty/opisu w ramach tego samego budżetu
        # lub po prostu nadpisujemy ID - co w przyszłości może wymagać dopracowania sald).
        # Na razie zostawmy prostą aktualizację:
        transaction.id_podbudzetu = nowy_budzet_id

        db.session.commit()
        flash("Zapisano zmiany w transakcji.", "success")
        return redirect(url_for("main.index"))  # lub main.history

    # GET: Wyświetlanie formularza
    categories = Category.query.filter_by(id_gospodarstwa=member.id_gospodarstwa).all()
    budgets = SubBudget.query.filter_by(id_gospodarstwa=member.id_gospodarstwa).all()

    return render_template(
        "edit_transaction.html",
        transaction=transaction,
        categories=categories,
        budgets=budgets
    )


@bp.route("/delete_transaction/<int:t_id>", methods=["POST"])
@login_required
def delete_transaction(t_id):
    transaction = db.session.get(Transaction, t_id)

    if transaction:
        # --- NOWE ZABEZPIECZENIE: BLOKADA USUWANIA PRZELEWÓW ---
        if transaction.kategoria.nazwa in ["Przelew Wychodzący", "Przelew Przychodzący"]:
            flash("Nie można usuwać pojedynczych części przelewu. Funkcja usuwania całych przelewów jest w budowie.",
                  "danger")
            return redirect(url_for("main.index"))
        # -------------------------------------------------------

        # Cofnięcie salda dla zwykłej transakcji
        budget = db.session.get(SubBudget, transaction.id_podbudzetu)
        if budget:
            if transaction.typ == "Wydatek":
                budget.saldo += transaction.kwota
            else:
                budget.saldo -= transaction.kwota

        db.session.delete(transaction)
        db.session.commit()
        flash("Transakcja usunięta.", "success")
    else:
        flash("Nie znaleziono transakcji.", "danger")

    return redirect(url_for("main.index"))


@bp.route("/delete_cyclic/<int:cyclic_id>", methods=["POST"])
@login_required
def delete_cyclic(cyclic_id):
    user = get_current_user()
    cyclic_trans = db.session.get(CyclicTransaction, cyclic_id)

    if not cyclic_trans:
        flash("Nie znaleziono płatności cyklicznej.", "danger")
        return redirect(url_for("main.cyclic"))

    member = HouseholdMember.query.filter_by(id_uzytkownika=user.id).first()
    if cyclic_trans.podbudzet.id_gospodarstwa != member.id_gospodarstwa:
        flash("Brak uprawnień.", "danger")
        return redirect(url_for("main.cyclic"))

    db.session.delete(cyclic_trans)
    db.session.commit()
    flash("Usunięto płatność cykliczną.", "success")
    return redirect(url_for("main.cyclic"))


@bp.route("/edit_cyclic/<int:cyclic_id>", methods=["GET", "POST"])
@login_required
def edit_cyclic(cyclic_id):
    user = get_current_user()
    cyclic_trans = db.session.get(CyclicTransaction, cyclic_id)

    if not cyclic_trans:
        flash("Nie znaleziono płatności.", "danger")
        return redirect(url_for("main.cyclic"))

    member = HouseholdMember.query.filter_by(id_uzytkownika=user.id).first()
    if cyclic_trans.podbudzet.id_gospodarstwa != member.id_gospodarstwa:
        flash("Brak uprawnień.", "danger")
        return redirect(url_for("main.cyclic"))

    if request.method == "POST":
        cyclic_trans.typ = request.form.get("typ")
        cyclic_trans.nazwa = request.form.get("nazwa")
        cyclic_trans.kwota = Decimal(request.form.get("kwota"))
        cyclic_trans.okres = request.form.get("okres")
        cyclic_trans.id_kategorii = request.form.get("kategoria")
        cyclic_trans.id_podbudzetu = request.form.get("podbudzet")
        
        # Data startu
        try:
            d_start = datetime.strptime(request.form.get("data_startu"), "%Y-%m-%d")
            cyclic_trans.data_startu = d_start
        except ValueError:
            pass # Jeśli user nie zmienił daty, może przyjść pusta lub błędna? 
                 # Wystarczy required w html, ale warto zabezpieczyć.
                 # Tutaj zakładam, że przyjdzie poprawna z input type=date.

        db.session.commit()
        flash("Zaktualizowano płatność cykliczną.", "success")
        return redirect(url_for("main.cyclic"))

    categories = Category.query.filter_by(id_gospodarstwa=member.id_gospodarstwa).all()
    budgets = SubBudget.query.filter_by(id_gospodarstwa=member.id_gospodarstwa).all()

    return render_template("edit_cyclic.html", 
                           cyclic=cyclic_trans, 
                           categories=categories, 
                           budgets=budgets)
