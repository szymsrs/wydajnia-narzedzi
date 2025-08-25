# app/repo/reports_repo.py
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.engine import Engine


class ReportsRepo:
    def __init__(self, engine: Engine):
        self.engine = engine

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
        """Return list of exception events.

        Optional ``employee_id`` and ``item_id`` parameters allow narrowing the
        results to a specific employee or item.
        """
        sql = text(
            """
            SELECT *
            FROM vw_exceptions
            WHERE event_ts >= :df
              AND event_ts <  :dt
              AND (:emp IS NULL OR employee_id = :emp)
              AND (:itm IS NULL OR item_id = :itm)
            ORDER BY event_ts DESC
            LIMIT :lim
        """
        )
        params = {
            "df": date_from,
            "dt": date_to,
            "emp": employee_id,
            "itm": item_id,
            "lim": int(limit),
        }
        with self.engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
        return [dict(r) for r in rows]

    def employees(self, q: str = "", limit: int = 200) -> list[dict]:
        sql = text(
            """
            SELECT id, first_name, last_name, login, rfid_uid
            FROM employees
            WHERE (
                :q = ''
                OR CONCAT_WS(' ', first_name, last_name, login)
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
        sql = text(
            """
            SELECT *
            FROM vw_employee_card
            WHERE employee_id = :emp
              AND event_ts >= :df
              AND event_ts <  :dt
            ORDER BY event_ts DESC, id DESC
        """
        )
        with self.engine.connect() as conn:
            rows = (
                conn.execute(
                    sql,
                    {"emp": int(employee_id), "df": date_from, "dt": date_to},
                )
                .mappings()
                .all()
            )
        return [dict(r) for r in rows]
