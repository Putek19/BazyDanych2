import os
import oracledb
from dotenv import load_dotenv

load_dotenv()


try:
    oracledb.init_oracle_client()
except Exception:
    pass


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
