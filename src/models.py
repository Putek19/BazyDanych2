from . import db
from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    Numeric,
    Boolean,
    Date,
    LargeBinary,
    Identity,
)
from sqlalchemy.orm import relationship
from datetime import datetime


# Tabela łącząca
class HouseholdMember(db.Model):
    __tablename__ = "czlonek_gospodarstwa"  # Liczba pojedyncza

    id_gospodarstwa = Column(
        Integer, ForeignKey("gospodarstwo_domowe.id"), primary_key=True
    )
    id_uzytkownika = Column(Integer, ForeignKey("uzytkownik.id"), primary_key=True)
    czy_uprawnienia_admina = Column(Boolean, default=False, nullable=False)

    uzytkownik = relationship("User", back_populates="gospodarstwa")
    gospodarstwo = relationship("Household", back_populates="czlonkowie")


class User(db.Model):
    __tablename__ = "uzytkownik"  # Liczba pojedyncza

    id = Column(Integer, Identity(start=1), primary_key=True)
    nazwa_uzytkownika = Column(String(50), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    haslo_hash = Column(String(255), nullable=False)

    gospodarstwa = relationship("HouseholdMember", back_populates="uzytkownik")
    transakcje = relationship("Transaction", back_populates="uzytkownik")
    transakcje_cykliczne = relationship(
        "CyclicTransaction", back_populates="uzytkownik"
    )


class Household(db.Model):
    __tablename__ = "gospodarstwo_domowe"  # Liczba pojedyncza

    id = Column(Integer, Identity(start=1), primary_key=True)
    nazwa_gospodarstwa = Column(String(50), nullable=False)
    wlasciciel_id = Column(Integer, ForeignKey("uzytkownik.id"), nullable=False)
    # USUNIĘTO: kod_zaproszenia

    czlonkowie = relationship("HouseholdMember", back_populates="gospodarstwo")
    podbudzety = relationship("SubBudget", back_populates="gospodarstwo")
    kategorie = relationship("Category", back_populates="gospodarstwo")


class SubBudget(db.Model):
    __tablename__ = "podbudzet"  # Liczba pojedyncza

    id = Column(Integer, Identity(start=1), primary_key=True)
    id_gospodarstwa = Column(
        Integer, ForeignKey("gospodarstwo_domowe.id"), nullable=False
    )
    nazwa = Column(String(50), nullable=False)
    saldo = Column(Numeric(12, 2), default=0.00, nullable=False)

    gospodarstwo = relationship("Household", back_populates="podbudzety")
    transakcje = relationship("Transaction", back_populates="podbudzet")
    transakcje_cykliczne = relationship("CyclicTransaction", back_populates="podbudzet")


class Category(db.Model):
    __tablename__ = "kategoria"  # Liczba pojedyncza

    id = Column(Integer, Identity(start=1), primary_key=True)
    id_gospodarstwa = Column(
        Integer, ForeignKey("gospodarstwo_domowe.id"), nullable=False
    )
    nazwa = Column(String(50), nullable=False)
    opis = Column(String(255), nullable=True)  # DODANO: Opis
    typ = Column(String(20), nullable=False)

    gospodarstwo = relationship("Household", back_populates="kategorie")
    transakcje = relationship("Transaction", back_populates="kategoria")
    transakcje_cykliczne = relationship("CyclicTransaction", back_populates="kategoria")


class Transaction(db.Model):
    __tablename__ = "transakcja"  # Liczba pojedyncza

    id = Column(Integer, Identity(start=1), primary_key=True)
    id_uzytkownika = Column(Integer, ForeignKey("uzytkownik.id"), nullable=False)
    id_podbudzetu = Column(Integer, ForeignKey("podbudzet.id"), nullable=False)
    id_kategorii = Column(Integer, ForeignKey("kategoria.id"), nullable=False)

    typ = Column(String(10), nullable=False)
    nazwa = Column(String(100), nullable=False)
    kwota = Column(Numeric(10, 2), nullable=False)
    data = Column(Date, default=datetime.utcnow, nullable=False)
    zdjecie = Column(LargeBinary, nullable=True)
    uzytkownik = relationship("User", back_populates="transakcje")
    podbudzet = relationship("SubBudget", back_populates="transakcje")
    kategoria = relationship("Category", back_populates="transakcje")


# NOWA TABELA: Transakcja Cykliczna
class CyclicTransaction(db.Model):
    __tablename__ = "transakcja_cykliczna"  # Liczba pojedyncza

    id = Column(Integer, Identity(start=1), primary_key=True)
    id_uzytkownika = Column(Integer, ForeignKey("uzytkownik.id"), nullable=False)
    id_podbudzetu = Column(Integer, ForeignKey("podbudzet.id"), nullable=False)
    id_kategorii = Column(Integer, ForeignKey("kategoria.id"), nullable=False)

    typ = Column(String(10), nullable=False)
    nazwa = Column(String(100), nullable=False)
    kwota = Column(Numeric(10, 2), nullable=False)
    data_startu = Column(Date, nullable=False)
    okres = Column(String(20), nullable=False)  # np. 'MIESIECZNIE', 'TYGODNIOWO'
    zdjecie = Column(LargeBinary, nullable=True)

    uzytkownik = relationship("User", back_populates="transakcje_cykliczne")
    podbudzet = relationship("SubBudget", back_populates="transakcje_cykliczne")
    kategoria = relationship("Category", back_populates="transakcje_cykliczne")
