from contextlib import contextmanager

def transaction(SessionLocal):
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
