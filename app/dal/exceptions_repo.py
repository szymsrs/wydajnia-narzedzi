# app/dal/exceptions_repo.py
from __future__ import annotations

from datetime import datetime
from typing import Iterable
from sqlalchemy import text
from sqlalchemy.engine import Engine
import logging

log = logging.getLogger(__name__)


class ExceptionsRepo:
    """DAO for reading transactions flagged as issued_without_return."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self._cols_cache: set[str] | None = None

    # --- helpers -------------------------------------------------------------
    def _get_columns(self) -> set[str]:
        if self._cols_cache is not None:
            return self._cols_cache
        with self.engine.connect() as conn:
            cols = set(
                conn.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = DATABASE() AND table_name = 'vw_exceptions'
                        """
                    )
                ).scalars()
            )
        self._cols_cache = cols
        return cols

    @staticmethod
    def _pick(cols: set[str], *candidates: Iterable[str]) -> str | None:
        for c in candidates:
            if c in cols:
                return c
        return None

    # --- API ----------------------------------------------------------------
    def list_exceptions(
        self,
        *,
        employee_id: int | None = None,
        item_id: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ):
        cols = self._get_columns()

        uuid_col = self._pick(cols, "operation_uuid", "op_uuid", "uuid", "operation_id")
        emp_name_col = self._pick(
            cols, "employee", "employee_name", "employee_fullname", "emp_name", "full_name", "name"
        )
        login_col = self._pick(cols, "login", "username", "user_login", "user")
        item_col = self._pick(cols, "item", "item_name", "name", "sku", "item_code")
        qty_col = self._pick(cols, "quantity", "qty", "amount")
        ts_col = self._pick(cols, "created_at", "ts", "event_ts", "timestamp", "event_time", "created")
        mvt_col = self._pick(cols, "movement_type", "movement", "movement_kind", "kind", "op_type")

        # zbuduj SELECT z aliasami oczekiwanymi przez UI/CSV
        select_parts: list[str] = []
        select_parts.append(f"{uuid_col} AS operation_uuid" if uuid_col else "'' AS operation_uuid")
        select_parts.append(f"{emp_name_col} AS employee" if emp_name_col else "'' AS employee")
        select_parts.append(f"{login_col} AS login" if login_col else "'' AS login")
        select_parts.append(f"{item_col} AS item" if item_col else "'' AS item")
        select_parts.append(f"{qty_col} AS quantity" if qty_col else "0 AS quantity")
        if ts_col:
            select_parts.append(f"{ts_col} AS created_at")
        else:
            select_parts.append("CURRENT_TIMESTAMP AS created_at")
        select_parts.append(f"{mvt_col} AS movement_type" if mvt_col else "'' AS movement_type")

        sql_parts = [f"SELECT {', '.join(select_parts)}", "FROM vw_exceptions", "WHERE 1=1"]
        params: dict[str, object] = {}

        # filtry — tylko jeśli kolumny istnieją
        if employee_id is not None and "employee_id" in cols:
            sql_parts.append("AND employee_id = :emp")
            params["emp"] = employee_id
        if item_id is not None and "item_id" in cols:
            sql_parts.append("AND item_id = :itm")
            params["itm"] = item_id
        if date_from is not None and ts_col:
            sql_parts.append(f"AND {ts_col} >= :d_from")
            params["d_from"] = date_from
        if date_to is not None and ts_col:
            sql_parts.append(f"AND {ts_col} < :d_to")
            params["d_to"] = date_to

        # sortowanie — po kolumnie czasu jeśli jest, inaczej po pierwszej kolumnie
        if ts_col:
            sql_parts.append(f"ORDER BY {ts_col} DESC")
        elif uuid_col:
            sql_parts.append(f"ORDER BY {uuid_col} DESC")
        else:
            sql_parts.append("ORDER BY 1 DESC")

        sql = " ".join(sql_parts)

        # log diagnostyczny (raz, gdy wykryjemy brak jakiejś kolumny)
        missing = [name for name, col in {
            "employee": emp_name_col, "login": login_col, "item": item_col,
            "quantity": qty_col, "created_at": ts_col, "movement_type": mvt_col
        }.items() if col is None]
        if missing:
            log.warning("vw_exceptions: brak kolumn %s – używam pustych aliasów", ", ".join(missing))

        with self.engine.connect() as conn:
            return conn.execute(text(sql), params).fetchall()
