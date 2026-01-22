from flask import Blueprint, render_template, redirect, url_for, session, current_app
from flask_login import login_required, current_user
from sqlalchemy import desc, func
from ..models import HouseholdMember, SubBudget, Transaction, Category
from .. import db
from itsdangerous import URLSafeTimedSerializer

bp = Blueprint("main", __name__)

def get_active_budget(household_id):
    active_id = session.get('active_budget_id')
    if active_id:
        budget = SubBudget.query.filter_by(id=active_id, id_gospodarstwa=household_id).first()
        if budget:
            return budget
    default_budget = SubBudget.query.filter_by(id_gospodarstwa=household_id).first()
    if default_budget:
        session['active_budget_id'] = default_budget.id
    return default_budget


@bp.route("/")
@login_required
def index():
    user = current_user
    member = HouseholdMember.query.filter_by(id_uzytkownika=user.id).first()
    if not member:
        return "Błąd: Brak gospodarstwa. (Błąd spójności danych)"

    household_id = member.id_gospodarstwa

    # 1. LOGIKA BUDŻETÓW
    active_budget = get_active_budget(household_id)
    all_budgets = SubBudget.query.filter_by(id_gospodarstwa=household_id).all()

    if not active_budget:
        return render_template("dashboard.html",
                               active_budget=None,
                               budgets=[],
                               transactions=[],
                               invite_code=None)

    # 2. POBIERANIE TRANSAKCJI
    recent_transactions = (
        Transaction.query.filter_by(id_podbudzetu=active_budget.id)
        .order_by(desc(Transaction.data))
        .limit(10)
        .all()
    )

    # 3. GENEROWANIE KODU ZAPROSZENIA
    # Generujemy kod ważny np. bezterminowo lub długo. 
    # Używamy salt="invite-code" tak jak przy rejestracji.
    s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    invite_code = s.dumps(household_id, salt="invite-code")

    return render_template(
        "dashboard.html",
        active_budget=active_budget,
        budgets=all_budgets,
        transactions=recent_transactions,
        invite_code=invite_code  # Przekazujemy kod do widoku
    )


@bp.route("/history")
@login_required
def history():
    user = current_user
    member = HouseholdMember.query.filter_by(id_uzytkownika=user.id).first()
    
    all_transactions = (
        Transaction.query.filter(
            Transaction.podbudzet.has(id_gospodarstwa=member.id_gospodarstwa)
        )
        .order_by(Transaction.data.desc())
        .all()
    )

    return render_template("history.html", transakcje=all_transactions)


@bp.route("/analysis")
@login_required
def analysis():
    user = current_user
    member = HouseholdMember.query.filter_by(id_uzytkownika=user.id).first()

    data = (
        db.session.query(Category.nazwa, func.sum(Transaction.kwota))
        .join(Transaction)
        .filter(Transaction.podbudzet.has(id_gospodarstwa=member.id_gospodarstwa))
        .filter(Transaction.typ == "Wydatek")
        .group_by(Category.nazwa)
        .all()
    )

    labels = [row[0] for row in data]
    values = [float(row[1]) for row in data]

    return render_template("analysis.html", labels=labels, values=values)
