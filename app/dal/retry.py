import time
from functools import wraps

from pymysql.err import OperationalError
from sqlalchemy.exc import OperationalError as SAOperationalError


def retry_deadlock(max_tries: int = 3, base_sleep: float = 0.1):
    """Retry decorator for deadlocks (1213) and lock timeouts (1205)."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            tries = 0
            while True:
                try:
                    return fn(*args, **kwargs)
                except (OperationalError, SAOperationalError) as exc:
                    code = exc.args[0] if exc.args else None
                    if code in (1205, 1213) and tries < max_tries - 1:
                        time.sleep(base_sleep * (2 ** tries))
                        tries += 1
                        continue
                    raise

        return wrapper

    return decorator
