from contextlib import contextmanager
from sqlalchemy.orm import sessionmaker


def transaction(SessionLocal: sessionmaker):
    @contextmanager
    def _tx():
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return _tx


def for_update(query):
    """Apply SQL-level FOR UPDATE locking."""

    return query.with_for_update()
