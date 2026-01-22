from decimal import Decimal
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_required, current_user
from ..models import HouseholdMember, SubBudget, Category, Transaction
from .. import db

bp = Blueprint("budgets", __name__)

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
        session['active_budget_id'] = new_budget.id
        flash(f"Utworzono nowy budżet wydzielony: {nazwa}", "success")

    return redirect(url_for('main.index'))

@bp.route("/switch_budget/<int:budget_id>")
@login_required
def switch_budget(budget_id):
    member = HouseholdMember.query.filter_by(id_uzytkownika=current_user.id).first()
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
    user = current_user
    member = HouseholdMember.query.filter_by(id_uzytkownika=user.id).first()

    if request.method == "POST":
        source_id = request.form.get("source_budget")
        target_id = request.form.get("target_budget")
        amount_str = request.form.get("amount")

        try:
            amount = Decimal(amount_str)
        except:
            flash("Nieprawidłowa kwota.", "danger")
            return redirect(url_for("budgets.transfer"))

        if amount <= 0:
            flash("Kwota musi być dodatnia.", "warning")
            return redirect(url_for("budgets.transfer"))

        if source_id == target_id:
            flash("Budżet źródłowy i docelowy muszą być różne.", "warning")
            return redirect(url_for("budgets.transfer"))

        source_budget = db.session.get(SubBudget, source_id)
        target_budget = db.session.get(SubBudget, target_id)

        if not source_budget or not target_budget:
            flash("Nie znaleziono budżetu.", "danger")
            return redirect(url_for("budgets.transfer"))

        if source_budget.id_gospodarstwa != member.id_gospodarstwa or target_budget.id_gospodarstwa != member.id_gospodarstwa:
            flash("Brak uprawnień.", "danger")
            return redirect(url_for("budgets.transfer"))

        # --- LOGIKA KATEGORII (BEZ ZMIAN W BAZIE) ---
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

        db.session.flush()

        # --- OPERACJA FINANSOWA ---
        source_budget.saldo -= amount
        target_budget.saldo += amount

        timestamp = datetime.utcnow()

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

    budgets = SubBudget.query.filter_by(id_gospodarstwa=member.id_gospodarstwa).all()
    return render_template("transfer.html", budgets=budgets)
