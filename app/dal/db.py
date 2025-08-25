# app/dal/db.py
from __future__ import annotations
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL
from sqlalchemy.orm import sessionmaker


def make_engine(cfg: dict) -> Engine:
    """Zbuduj Engine bezpiecznie, bez ręcznego sklejania DSN."""
    db = cfg.get("db", cfg)  # pozwala podać cały cfg lub sam słownik db
    url = URL.create(
        "mysql+pymysql",
        username=db["user"],
        password=db["password"],  # znaki specjalne (np. @) są poprawnie escapowane
        host=db["host"],
        port=int(db.get("port", 3306)),
        database=db["database"],
        query={"charset": "utf8mb4"},
    )
    engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=1800,
        isolation_level="READ COMMITTED",
        future=True,
    )
    return engine


def create_engine_and_session(cfg: dict) -> tuple[Engine, sessionmaker]:
    """Zwraca (Engine, SessionLocal) na podstawie konfiguracji."""
    engine = make_engine(cfg)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return engine, SessionLocal


def ping(engine: Engine) -> bool:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True


# (Opcjonalnie) Pomocniczo: bezpieczne budowanie DSN jako string, jeśli gdzieś potrzebujesz.
def make_conn_str(host: str, port: int, user: str, password: str, database: str) -> str:
    url = URL.create(
        "mysql+pymysql",
        username=user,
        password=password,
        host=host,
        port=int(port),
        database=database,
        query={"charset": "utf8mb4"},
    )
    return str(url)
