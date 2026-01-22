from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from ..models import HouseholdMember, Category
from .. import db

bp = Blueprint("categories", __name__)

@bp.route("/categories", methods=["GET", "POST"])
@login_required
def categories():
    user = current_user
    member = HouseholdMember.query.filter_by(id_uzytkownika=user.id).first()

    if request.method == "POST":
        nazwa = request.form.get("nazwa")
        opis = request.form.get("opis")
        typ = request.form.get("typ")

        if not typ:
            typ = "Wydatek"

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

        return redirect(url_for("categories.categories"))

    cats_wydatki = Category.query.filter_by(id_gospodarstwa=member.id_gospodarstwa, typ="Wydatek").all()
    cats_wplywy = Category.query.filter_by(id_gospodarstwa=member.id_gospodarstwa, typ="Wplyw").all()

    return render_template("categories.html", wydatki=cats_wydatki, wplywy=cats_wplywy)


@bp.route("/delete_category/<int:c_id>", methods=["POST"])
@login_required
def delete_category(c_id):
    user = current_user
    member = HouseholdMember.query.filter_by(id_uzytkownika=user.id).first()
    
    cat = db.session.get(Category, c_id)
    if not cat:
        flash("Kategoria nie istnieje.", "danger")
        return redirect(url_for("categories.categories"))

    if cat.id_gospodarstwa != member.id_gospodarstwa:
        flash("Brak uprawnień.", "danger")
        return redirect(url_for("categories.categories"))
    
    if cat.nazwa in ["Przelew Wychodzący", "Przelew Przychodzący"]:
        flash("Nie można usunąć kategorii systemowej.", "warning")
        return redirect(url_for("categories.categories"))

    try:
        db.session.delete(cat)
        db.session.commit()
        flash("Usunięto kategorię.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Nie można usunąć kategorii, która ma przypisane transakcje.", "danger")
        print(f"Błąd usuwania kategorii: {e}")

    return redirect(url_for("categories.categories"))


@bp.route("/edit_category/<int:c_id>", methods=["GET", "POST"])
@login_required
def edit_category(c_id):
    user = current_user
    member = HouseholdMember.query.filter_by(id_uzytkownika=user.id).first()
    
    cat = db.session.get(Category, c_id)
    if not cat:
        flash("Kategoria nie istnieje.", "danger")
        return redirect(url_for("categories.categories"))

    if cat.id_gospodarstwa != member.id_gospodarstwa:
        flash("Brak uprawnień.", "danger")
        return redirect(url_for("categories.categories"))

    if request.method == "POST":
        nazwa = request.form.get("nazwa")
        opis = request.form.get("opis")
        
        exists = Category.query.filter(
            Category.id_gospodarstwa == member.id_gospodarstwa,
            Category.nazwa == nazwa,
            Category.id != c_id
        ).first()

        if exists:
            flash("Kategoria o takiej nazwie już istnieje.", "warning")
        else:
            cat.nazwa = nazwa
            cat.opis = opis
            db.session.commit()
            flash("Zaktualizowano kategorię.", "success")
            return redirect(url_for("categories.categories"))

    return render_template("edit_category.html", category=cat)
