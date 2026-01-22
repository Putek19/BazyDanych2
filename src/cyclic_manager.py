from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from .models import CyclicTransaction, Transaction, Category
from . import db

def check_and_process_cyclic_transactions(app):
    """
    Sprawdza, czy są jakieś zaległe płatności cykliczne i je realizuje.
    Funkcja powinna być wywoływana przy STARCIE aplikacji.
    """
    with app.app_context():
        print("🔄 Sprawdzam płatności cykliczne...")
        
        # Pobieramy wszystkie cykliczne
        cyclic_all = CyclicTransaction.query.all()
        today = datetime.utcnow().date()
        
        count_processed = 0

        for cyc in cyclic_all:
            # Dopóki data następnej płatności jest w przeszłości (lub dzisiaj) -> generuj transakcję
            # Zabezpieczenie: max 50 iteracji, żeby nie wpadło w nieskończoną pętlę przy błędnych danych
            safety_counter = 0 
            
            while cyc.data_nastepnej_platnosci <= today and safety_counter < 50:
                print(f"   -> Przetwarzam: {cyc.nazwa} (Data: {cyc.data_nastepnej_platnosci})")
                
                # 1. Stwórz transakcję
                new_trans = Transaction(
                    id_uzytkownika=cyc.id_uzytkownika,
                    id_podbudzetu=cyc.id_podbudzetu,
                    id_kategorii=cyc.id_kategorii,
                    typ=cyc.typ,
                    nazwa=f"{cyc.nazwa} (Cykliczna)",
                    kwota=cyc.kwota,
                    data=cyc.data_nastepnej_platnosci
                )
                db.session.add(new_trans)
                
                # 2. Update salda budżetu
                if cyc.typ == "Wydatek":
                    cyc.podbudzet.saldo -= cyc.kwota
                else:
                    cyc.podbudzet.saldo += cyc.kwota
                
                # 3. Oblicz następną datę
                if cyc.okres == "MIESIECZNIE":
                    cyc.data_nastepnej_platnosci += relativedelta(months=1)
                elif cyc.okres == "TYGODNIOWO":
                    cyc.data_nastepnej_platnosci += timedelta(weeks=1)
                elif cyc.okres == "ROCZNIE":
                     cyc.data_nastepnej_platnosci += relativedelta(years=1)
                else:
                    # Domyślnie miesięcznie jak coś nie tak
                    cyc.data_nastepnej_platnosci += relativedelta(months=1)
                
                count_processed += 1
                safety_counter += 1
                
        if count_processed > 0:
            db.session.commit()
            print(f"✅ Przetworzono {count_processed} zaległych płatności.")
        else:
            print("✅ Brak zaległych płatności.")
