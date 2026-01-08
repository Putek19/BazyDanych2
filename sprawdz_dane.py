from src import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    print("\n🕵️  TRWA ŚLEDZTWO: Gdzie są tabele? ...\n")

    # Lista tabel, których szukamy
    moje_tabele = ["UZYTKOWNICY", "GOSPODARSTWA_DOMOWE", "TRANSAKCJE"]

    znaleziono_cokolwiek = False

    for tabela in moje_tabele:
        # Zapytanie do słownika danych Oracle (all_tables widzi wszystko)
        sql = text(
            f"SELECT owner, table_name FROM all_tables WHERE upper(table_name) = '{tabela}'"
        )
        wynik = db.session.execute(sql).fetchall()

        if wynik:
            znaleziono_cokolwiek = True
            for row in wynik:
                wlasciciel = row[0]  # To jest nazwa SCHEMATU
                nazwa = row[1]
                print(f"✅ ZNALEZIONO TABELĘ: {nazwa}")
                print(f"   🏠 Jej 'adres' (Schema): {wlasciciel}")
                print(
                    f"   👉 W VS Code klikaj: Schemas -> {wlasciciel} -> Tables -> {nazwa}"
                )
                print("-" * 50)
        else:
            print(f"❌ Tabela {tabela} nie została odnaleziona w bazie.")

    if not znaleziono_cokolwiek:
        print(
            "\n⚠️  Dziwne... Baza nie widzi żadnych tabel. Uruchom najpierw 'python reset_db.py'."
        )
