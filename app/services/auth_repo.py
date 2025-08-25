# app/services/auth_repo.py
from __future__ import annotations

from typing import Tuple

from app.core.auth import AuthRepo
from app.dal.db import create_engine_and_session, ping
from app.infra.config import AppSettings


def init_auth_repo(settings: AppSettings) -> Tuple[AuthRepo | None, bool, Exception | None]:
    """Initialize :class:`AuthRepo` using database settings.

    Returns a tuple ``(repo, db_ok, error)`` where ``repo`` is the initialized
    repository (or ``None`` on failure), ``db_ok`` indicates whether the
    connection succeeded and ``error`` holds the caught exception if any.
    """

    try:
        cfg = {
            "db": {
                "host": settings.db.host,
                "port": settings.db.port,
                "user": settings.db.user,
                "password": settings.db.password,
                # create_engine_and_session expects 'database'
                "database": settings.db.database,
                # AuthRepo still expects 'name'
                "name": settings.db.database,
            }
        }
        engine, _ = create_engine_and_session(cfg, log_sql=settings.log_sql)
        ping(engine)
        repo = AuthRepo(cfg)
        return repo, True, None
    except Exception as e:  # pragma: no cover - logged in main
        return None, False, e
