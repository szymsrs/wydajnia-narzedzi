from sqlalchemy import text
from sqlalchemy.engine import Engine


def db_ping(engine: Engine) -> bool:
    """Simple DB healthcheck using SELECT 1."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True
