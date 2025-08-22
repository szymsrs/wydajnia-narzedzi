# app/dal/exceptions_repo.py
from __future__ import annotations

from datetime import datetime
from sqlalchemy import text
from sqlalchemy.engine import Engine


class ExceptionsRepo:
    """DAO for reading transactions flagged as issued_without_return."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def list_exceptions(
        self,
        *,
        employee_id: int | None = None,
        item_id: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ):
        sql = [
            "SELECT operation_uuid, employee, login, item, quantity, created_at, movement_type "
            "FROM vw_exceptions WHERE 1=1"
        ]
        params: dict[str, object] = {}
        if employee_id is not None:
            sql.append("AND employee_id=:emp")
            params["emp"] = employee_id
        if item_id is not None:
            sql.append("AND item_id=:itm")
            params["itm"] = item_id
        if date_from is not None:
            sql.append("AND created_at>=:d_from")
            params["d_from"] = date_from
        if date_to is not None:
            sql.append("AND created_at<=:d_to")
            params["d_to"] = date_to
        sql.append("ORDER BY created_at DESC")
        with self.engine.connect() as conn:
            return conn.execute(text(" ".join(sql)), params).fetchall()
