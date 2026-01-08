from src import create_app, db
from src.models import User, Category, SubBudget

app = create_app()


def seed():
    with app.app_context():
        print("🌱 Rozpoczynam zasiewanie danych...")

        # 1. Znajdź Twojego użytkownika (zmień email na ten, którego użyłeś przy rejestracji!)
        email_admina = "kubanowacki@wp.pl"  # <--- ZMIEŃ NA SWÓJ EMAIL REJESTRACJI
        user = User.query.filter_by(email=email_admina).first()

        if not user:
            print(
                f"❌ Nie znaleziono użytkownika {email_admina}. Zarejestruj się najpierw!"
            )
            return

        # Pobierz ID gospodarstwa tego usera (zakładamy, że ma jedno)
        # Relacja user.gospodarstwa zwraca listę HouseholdMember
        if not user.gospodarstwa:
            print("❌ Użytkownik nie należy do żadnego gospodarstwa.")
            return

        household_id = user.gospodarstwa[0].id_gospodarstwa
        print(f"🏠 Znaleziono gospodarstwo ID: {household_id}")

        # 2. Dodaj Podbudżet "Konto Główne" (jeśli nie istnieje)
        wallet = SubBudget.query.filter_by(
            id_gospodarstwa=household_id, nazwa="Konto Główne"
        ).first()
        if not wallet:
            wallet = SubBudget(
                id_gospodarstwa=household_id, nazwa="Konto Główne", saldo=0.00
            )
            db.session.add(wallet)
            print("✅ Dodano podbudżet: Konto Główne")

        # 3. Dodaj Kategorie (jeśli nie istnieją)
        kategorie_startowe = [
            ("Jedzenie", "Artykuły spożywcze", "Wydatek"),
            ("Transport", "Paliwo, bilety", "Wydatek"),
            ("Rozrywka", "Kino, gry", "Wydatek"),
            ("Rachunki", "Prąd, gaz, czynsz", "Wydatek"),
            (
                "Pensja",
                "Wypłata miesięczna",
                "Wplyw",
            ),  # Uwaga: w bazie 'Wplyw' (bez polskich znaków dla bezpieczeństwa)
        ]

        for nazwa, opis, typ in kategorie_startowe:
            cat = Category.query.filter_by(
                id_gospodarstwa=household_id, nazwa=nazwa
            ).first()
            if not cat:
                new_cat = Category(
                    id_gospodarstwa=household_id, nazwa=nazwa, opis=opis, typ=typ
                )
                db.session.add(new_cat)
                print(f"✅ Dodano kategorię: {nazwa}")

        db.session.commit()
        print("🏁 Gotowe! Możesz teraz dodawać transakcje.")


if __name__ == "__main__":
    seed()
