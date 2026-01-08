from src import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    print("⏳ Łączenie z bazą Oracle...")

    # 1. Usuwanie starych tabel (kolejność jest ważna przez klucze obce!)
    # Używamy drop_all(), ale w Oracle czasem trzeba wymusić usunięcie
    try:
        print("🗑️  Usuwanie starych tabel...")
        db.drop_all()
        print("✅ Stare tabele usunięte.")
    except Exception as e:
        print(f"⚠️  Ostrzeżenie przy usuwaniu (może tabel nie było): {e}")

    # 2. Tworzenie nowych tabel z nową strukturą (Identity)
    print("🔨 Tworzenie nowych tabel...")
    db.create_all()
    print("✅ Sukces! Baza jest czysta i gotowa.")
