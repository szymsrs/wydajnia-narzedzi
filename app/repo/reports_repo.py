# app/repo/reports_repo.py
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

import logging
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)


class ReportsRepo:
    def __init__(self, engine: Engine):
        self.engine = engine
        self._ts_cache: dict[str, str | None] = {}  # view_name -> ts col or None

    # ---------- helpers ----------
    def _detect_ts_col(self, view_name: str, candidates: Iterable[str]) -> str | None:
        """
        Zwraca nazwę pierwszej istniejącej kolumny z `candidates` w widoku
        albo None, jeśli żadnej nie ma. Wynik jest cache'owany.
        """
        if view_name in self._ts_cache:
            return self._ts_cache[view_name]

        with self.engine.connect() as conn:
            cols = set(
                conn.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = DATABASE() AND table_name = :t
                        """
                    ),
                    {"t": view_name},
                )
                .scalars()
                .all()
            )
        for c in candidates:
            if c in cols:
                self._ts_cache[view_name] = c
                return c
        self._ts_cache[view_name] = None
        return None

    # ---------- API ----------
    def rw_summary(
        self,
        date_from: datetime | date,
        date_to: datetime | date,
        limit: int = 500,
    ) -> list[dict]:
        sql = text(
            """
            SELECT *
            FROM vw_rw_summary
            WHERE rw_date >= :df
              AND rw_date <  :dt
            ORDER BY rw_date DESC, rw_id DESC
            LIMIT :lim
        """
        )
        with self.engine.connect() as conn:
            rows = (
                conn.execute(
                    sql,
                    {"df": date_from, "dt": date_to, "lim": int(limit)},
                )
                .mappings()
                .all()
            )
        return [dict(r) for r in rows]

    def exceptions(
        self,
        date_from: datetime | date,
        date_to: datetime | date,
        employee_id: int | None = None,
        item_id: int | None = None,
        limit: int = 500,
    ) -> list[dict]:
        """
        Zwraca listę wyjątków. Jeśli widok ma kolumnę czasu (created_at/ts/event_ts),
        filtruje po niej; jeśli nie — działa bez filtra czasowego (ale nadal z limit).
        """
        ts = self._detect_ts_col("vw_exceptions", ("created_at", "ts", "event_ts"))
        params = {
            "df": date_from,
            "dt": date_to,
            "emp": employee_id,
            "itm": item_id,
            "lim": int(limit),
        }
        if ts:
            sql = text(
                f"""
                SELECT *
                FROM vw_exceptions
                WHERE {ts} >= :df AND {ts} < :dt
                  AND (:emp IS NULL OR employee_id = :emp)
                  AND (:itm IS NULL OR item_id = :itm)
                ORDER BY {ts} DESC
                LIMIT :lim
                """
            )
        else:
            log.warning("vw_exceptions bez kolumny czasu – zwracam bez filtra daty")
            sql = text(
                """
                SELECT *
                FROM vw_exceptions
                WHERE (:emp IS NULL OR employee_id = :emp)
                  AND (:itm IS NULL OR item_id = :itm)
                ORDER BY 1 DESC
                LIMIT :lim
                """
            )
            # df/dt pozostają nieużyte — ale trzymamy sygnaturę

        with self.engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
        return [dict(r) for r in rows]

    def employees(self, q: str = "", limit: int = 200) -> list[dict]:
        sql = text(
            """
            SELECT id, first_name, last_name, username AS login, rfid_uid
            FROM employees
            WHERE (
                :q = ''
                OR CONCAT_WS(' ', first_name, last_name, username)
                LIKE CONCAT('%', :q, '%')
            )
            ORDER BY last_name, first_name
            LIMIT :lim
        """
        )
        with self.engine.connect() as conn:
            rows = (
                conn.execute(
                    sql,
                    {"q": q or "", "lim": int(limit)},
                )
                .mappings()
                .all()
            )
        return [dict(r) for r in rows]

    def employee_card(
        self,
        employee_id: int,
        date_from: datetime | date,
        date_to: datetime | date,
    ) -> list[dict]:
        """
        Karta pracownika:
         - jeśli widok ma kolumnę czasu (created_at/ts/event_ts), filtrujemy po niej,
         - jeśli nie ma (u Ciebie są `first_op` / `last_op`), używamy nakładającego
           się przedziału: last_op >= :df AND first_op < :dt.
        """
        ts = self._detect_ts_col("vw_employee_card", ("created_at", "ts", "event_ts"))
        params = {"emp": int(employee_id), "df": date_from, "dt": date_to}
        if ts:
            sql = text(
                f"""
                SELECT *
                FROM vw_employee_card
                WHERE employee_id = :emp
                  AND {ts} >= :df AND {ts} < :dt
                ORDER BY {ts} DESC, item_id DESC
                """
            )
        else:
            # Widok bez timestampu – skorzystaj z first_op/last_op
            sql = text(
                """
                SELECT *
                FROM vw_employee_card
                WHERE employee_id = :emp
                  AND last_op >= :df AND first_op < :dt
                ORDER BY last_op DESC, item_id DESC
                """
            )

        with self.engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
        return [dict(r) for r in rows]
