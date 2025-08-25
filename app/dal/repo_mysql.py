# app/dal/repo_mysql.py
from __future__ import annotations
import json
from typing import Any, Iterable, List, Tuple, Dict, Optional
from decimal import Decimal
import uuid  # legacy / przyszłe użycie
import pymysql
from app.core.auth import AuthRepo


class RepoMySQL:
    """Legacy repository. @deprecated Use AuthRepo instead."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.conn = pymysql.connect(
            host=cfg["db"]["host"],
            port=cfg["db"].get("port", 3306),
            user=cfg["db"]["user"],
            password=cfg["db"]["password"],
            database=cfg["db"]["database"],
            autocommit=False,
            cursorclass=pymysql.cursors.DictCursor,
        )
        # Adapter do nowej warstwy (AuthRepo) – do stopniowej migracji
        self._auth_repo = AuthRepo(
            {
                "db": {
                    "host": cfg["db"]["host"],
                    "port": cfg["db"].get("port", 3306),
                    "user": cfg["db"]["user"],
                    "password": cfg["db"]["password"],
                    "database": cfg["db"]["database"],
                    "name": cfg["db"]["database"],
                }
            }
        )

    # ---------- helpers ----------
    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    # ---------- ISSUE ----------
    def issue_to_employee(self, *, employee_id: int, employee_name: str, item_id: int, qty: Decimal):
        with self.conn:
            cur = self.conn.cursor()
            cur.callproc("sp_issue_to_employee", (employee_id, employee_name, item_id, str(qty)))
            self.conn.commit()

    # ---------- RETURN (alokacje) ----------
    def return_from_employee(self, *, employee_id: int, employee_name: str, allocations: List[Dict]):
        """
        allocations: [{"lot_id": int, "qty": Decimal}, ...] – dla konkretnych LOTÓW, bez movement_id
        """
        with self.conn:
            cur = self.conn.cursor()
            cur.execute("CREATE TEMPORARY TABLE tmp_return_allocs (lot_id BIGINT, qty DECIMAL(12,3))")
            if allocations:
                args = []
                sql = "INSERT INTO tmp_return_allocs(lot_id,qty) VALUES "
                sql += ",".join(["(%s,%s)"] * len(allocations))
                for a in allocations:
                    args.extend([int(a["lot_id"]), str(Decimal(a["qty"]))])
                cur.execute(sql, args)
            cur.callproc("sp_return_from_employee", (employee_id, employee_name))
            self.conn.commit()

    # ---------- Zapytania pod GUI ----------
    def get_employee_location_id(self, employee_id: int) -> Optional[int]:
        cur = self.conn.cursor()
        cur.execute("SELECT id FROM locations WHERE type='EMPLOYEE' AND employee_id=%s", (employee_id,))
        row = cur.fetchone()
        return row["id"] if row else None

    def list_employee_allocations(self, employee_id: int) -> List[dict]:
        """
        Co trzyma pracownik – rozbicie na LOT (FIFO koszt).
        Zwraca: lot_id, item_id, unit_cost_netto, qty_held
        """
        cur = self.conn.cursor()
        cur.execute(
            """
        WITH emp AS (SELECT id AS loc_id FROM locations WHERE type='EMPLOYEE' AND employee_id=%s)
        SELECT ma.lot_id, l.item_id, l.unit_cost_netto,
               SUM(CASE WHEN m.movement_type='ISSUE'  AND m.to_location_id   = emp.loc_id THEN ma.qty ELSE 0 END)
             - SUM(CASE WHEN m.movement_type='RETURN' AND m.from_location_id = emp.loc_id THEN ma.qty ELSE 0 END)
             - SUM(CASE WHEN m.movement_type='SCRAP'  AND m.from_location_id = emp.loc_id THEN ma.qty ELSE 0 END) AS qty_held
        FROM movement_allocations ma
        JOIN movements m ON m.id=ma.movement_id
        JOIN lots l ON l.id=ma.lot_id
        JOIN emp ON 1=1
        GROUP BY ma.lot_id, l.item_id, l.unit_cost_netto
        HAVING qty_held > 0
        ORDER BY l.item_id, l.unit_cost_netto;
        """,
            (employee_id,),
        )
        return cur.fetchall() or []

    def list_v_employee_holdings(self, emp_loc_id: int | None = None) -> List[dict]:
        cur = self.conn.cursor()
        if emp_loc_id:
            cur.execute("SELECT * FROM v_employee_holdings WHERE emp_loc=%s", (emp_loc_id,))
        else:
            cur.execute("SELECT * FROM v_employee_holdings")
        return cur.fetchall() or []

    def list_recent_movements(self, limit: int = 200) -> List[dict]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT id, ts, movement_type, item_id, qty, from_location_id, to_location_id
            FROM movements
            ORDER BY ts DESC, id DESC
            LIMIT %s
        """,
            (int(limit),),
        )
        return cur.fetchall() or []
