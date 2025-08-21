# app/dal/db.py
from __future__ import annotations
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
import urllib.parse  # <-- DODANE

def make_conn_str(host: str, port: int, user: str, password: str, database: str) -> str:
    # URL‑encode dla user/pass, żeby znaki typu @ : / ? nie psuły URI
    user_q = urllib.parse.quote_plus(user)
    pass_q = urllib.parse.quote_plus(password)
    host_q = host  # IP/hostname nie kodujemy
    return f"mysql+pymysql://{user_q}:{pass_q}@{host_q}:{port}/{database}?charset=utf8mb4"

def create_engine_and_session(conn_str: str) -> tuple[Engine, sessionmaker]:
    engine = create_engine(
        conn_str,
        pool_pre_ping=True,
        pool_recycle=1800,
        isolation_level="READ COMMITTED",
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return engine, SessionLocal

def ping(engine: Engine) -> bool:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True
