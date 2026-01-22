from decimal import Decimal
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_required, current_user
from ..models import HouseholdMember, SubBudget, Category, Transaction, CyclicTransaction
from .. import db

bp = Blueprint("transactions", __name__)

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

@bp.route("/add_transaction", methods=["GET", "POST"])
@login_required
def add_transaction():
    user = current_user
    member = HouseholdMember.query.filter_by(id_uzytkownika=user.id).first()
    household_id = member.id_gospodarstwa

    if request.method == "POST":
        nazwa = request.form.get("nazwa")
        kwota = Decimal(request.form.get("kwota"))
        typ = request.form.get("typ")
        cat_id = request.form.get("kategoria")
        bud_id = request.form.get("podbudzet")

        budget = db.session.get(SubBudget, bud_id)
        if typ == "Wydatek":
            budget.saldo -= kwota
        else:
            budget.saldo += kwota

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

    categories = Category.query.filter_by(id_gospodarstwa=household_id).all()
    budgets = SubBudget.query.filter_by(id_gospodarstwa=household_id).all()
    
    active_budget = get_active_budget(household_id)
    active_budget_id = active_budget.id if active_budget else None

    return render_template(
        "add_transaction.html",
        categories=categories,
        budgets=budgets,
        active_budget_id=active_budget_id
    )

@bp.route("/edit_transaction/<int:t_id>", methods=["GET", "POST"])
@login_required
def edit_transaction(t_id):
    transaction = db.session.get(Transaction, t_id)
    if not transaction:
        flash("Transakcja nie istnieje.", "danger")
        return redirect(url_for("main.history"))

    if transaction.kategoria.nazwa in ["Przelew Wychodzący", "Przelew Przychodzący"]:
        flash("Edycja przelewów wewnętrznych jest zablokowana. Aby skorygować błąd, usuń przelew i dodaj go ponownie.", "warning")
        return redirect(url_for("main.index"))

    member = HouseholdMember.query.filter_by(id_uzytkownika=current_user.id).first()

    if request.method == "POST":
        transaction.nazwa = request.form.get("nazwa")
        transaction.kwota = Decimal(request.form.get("kwota"))
        transaction.typ = request.form.get("typ")
        transaction.id_kategorii = request.form.get("kategoria")
        transaction.id_podbudzetu = int(request.form.get("podbudzet"))

        db.session.commit()
        flash("Zapisano zmiany w transakcji.", "success")
        return redirect(url_for("main.index"))

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
        if transaction.kategoria.nazwa in ["Przelew Wychodzący", "Przelew Przychodzący"]:
            flash("Nie można usuwać pojedynczych części przelewu. Funkcja usuwania całych przelewów jest w budowie.", "danger")
            return redirect(url_for("main.index"))

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


@bp.route("/cyclic", methods=["GET", "POST"])
@login_required
def cyclic():
    user = current_user
    member = HouseholdMember.query.filter_by(id_uzytkownika=user.id).first()

    if request.method == "POST":
        nazwa = request.form.get("nazwa")
        kwota = Decimal(request.form.get("kwota"))
        okres = request.form.get("okres")
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
            data_nastepnej_platnosci=data_startu,
            okres=okres,
        )
        db.session.add(new_cyclic)
        db.session.commit()
        flash("Dodano płatność cykliczną.")
        return redirect(url_for("transactions.cyclic"))

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

@bp.route("/delete_cyclic/<int:cyclic_id>", methods=["POST"])
@login_required
def delete_cyclic(cyclic_id):
    user = current_user
    cyclic_trans = db.session.get(CyclicTransaction, cyclic_id)
    if not cyclic_trans:
        flash("Nie znaleziono płatności cyklicznej.", "danger")
        return redirect(url_for("transactions.cyclic"))

    member = HouseholdMember.query.filter_by(id_uzytkownika=user.id).first()
    if cyclic_trans.podbudzet.id_gospodarstwa != member.id_gospodarstwa:
        flash("Brak uprawnień.", "danger")
        return redirect(url_for("transactions.cyclic"))

    db.session.delete(cyclic_trans)
    db.session.commit()
    flash("Usunięto płatność cykliczną.", "success")
    return redirect(url_for("transactions.cyclic"))

@bp.route("/edit_cyclic/<int:cyclic_id>", methods=["GET", "POST"])
@login_required
def edit_cyclic(cyclic_id):
    user = current_user
    cyclic_trans = db.session.get(CyclicTransaction, cyclic_id)
    if not cyclic_trans:
        flash("Nie znaleziono płatności.", "danger")
        return redirect(url_for("transactions.cyclic"))

    member = HouseholdMember.query.filter_by(id_uzytkownika=user.id).first()
    if cyclic_trans.podbudzet.id_gospodarstwa != member.id_gospodarstwa:
        flash("Brak uprawnień.", "danger")
        return redirect(url_for("transactions.cyclic"))

    if request.method == "POST":
        cyclic_trans.typ = request.form.get("typ")
        cyclic_trans.nazwa = request.form.get("nazwa")
        cyclic_trans.kwota = Decimal(request.form.get("kwota"))
        cyclic_trans.okres = request.form.get("okres")
        cyclic_trans.id_kategorii = request.form.get("kategoria")
        cyclic_trans.id_podbudzetu = request.form.get("podbudzet")
        try:
            d_start = datetime.strptime(request.form.get("data_startu"), "%Y-%m-%d")
            cyclic_trans.data_startu = d_start
            if d_start > datetime.utcnow():
                 cyclic_trans.data_nastepnej_platnosci = d_start
        except ValueError:
            pass

        db.session.commit()
        flash("Zaktualizowano płatność cykliczną.", "success")
        return redirect(url_for("transactions.cyclic"))

    categories = Category.query.filter_by(id_gospodarstwa=member.id_gospodarstwa).all()
    budgets = SubBudget.query.filter_by(id_gospodarstwa=member.id_gospodarstwa).all()

    return render_template("edit_cyclic.html", 
                           cyclic=cyclic_trans, 
                           categories=categories, 
                           budgets=budgets)
