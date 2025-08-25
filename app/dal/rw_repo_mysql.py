# app/dal/rw_repo_mysql.py
from __future__ import annotations
from typing import List, Tuple, Optional, Dict, Any
from decimal import Decimal
import uuid
import pymysql
from app.core.auth import AuthRepo


class RWRepoMySQL:
    """Cienka warstwa nad MariaDB (legacy). @deprecated Use AuthRepo instead."""

    def __init__(self, *, host: str, port: int, user: str, password: str, database: str):
        self.conn = pymysql.connect(
            host=host, port=port, user=user, password=password,
            database=database, autocommit=False, cursorclass=pymysql.cursors.DictCursor
        )
        self._auth_repo = AuthRepo(
            {
                "db": {
                    "host": host,
                    "port": port,
                    "user": user,
                    "password": password,
                    "database": database,
                    "name": database,
                }
            }
        )

    # -------------------- EMPLOYEES --------------------
    def resolve_employee(self, hint: Optional[str]) -> Tuple[Optional[int], List[Dict[str, Any]]]:
        """
        Heurystyka:
        - jeśli hint w formie "J.Kowalski" → dopasuj po inicjale + nazwisku (case-insens).
        - w innym razie LIKE po imieniu+nazwisku.
        Wymaga tabeli employees(id, first_name, last_name, card_uid?).
        """
        if not hint:
            return None, []
        cur = self.conn.cursor()
        hint = hint.strip()
        emp_id: Optional[int] = None
        candidates: List[Dict[str, Any]] = []

        # Spróbuj formatu "J.Kowalski"
        if "." in hint:
            ini, last = hint.split(".", 1)
            ini = ini.strip().lower()
            last = last.strip().lower()
            cur.execute("""
                SELECT id, first_name, last_name
                FROM employees
                WHERE LOWER(last_name)=%s AND LOWER(LEFT(first_name,1))=%s
                LIMIT 10
            """, (last, ini))
            rows = cur.fetchall() or []
            candidates = rows
            if len(rows) == 1:
                emp_id = rows[0]["id"]
                return emp_id, candidates

        # Ogólny LIKE po imieniu+nazwisku
        like = f"%{hint.lower()}%"
        cur.execute("""
            SELECT id, first_name, last_name
            FROM employees
            WHERE LOWER(CONCAT(first_name,' ',last_name)) LIKE %s
            LIMIT 10
        """, (like,))
        rows = cur.fetchall() or []
        candidates = rows
        if len(rows) == 1:
            emp_id = rows[0]["id"]
        return emp_id, candidates

    # -------------------- ITEMS --------------------
    def find_item_by_sku(self, sku: str) -> Optional[int]:
        cur = self.conn.cursor()
        cur.execute("SELECT id FROM items WHERE sku=%s", (sku.strip(),))
        row = cur.fetchone()
        return int(row["id"]) if row else None

    def ensure_item(self, sku: str, name: str, uom: str) -> int:
        cur = self.conn.cursor()
        sku = sku.strip()
        cur.execute("SELECT id FROM items WHERE sku=%s", (sku,))
        row = cur.fetchone()
        if row:
            return int(row["id"])
        cur.execute(
            "INSERT INTO items(sku, name, uom) VALUES(%s,%s,%s)",
            (sku, name.strip(), (uom or "SZT").upper())
        )
        self.conn.commit()
        return int(cur.lastrowid)

    # -------------------- RECEIPT (z parsera) --------------------
    def create_document(self, doc_type: str, number: str, doc_date: str, currency: str = "PLN",
                        suma_netto=None, suma_vat=None, suma_brutto=None) -> int:
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO documents(doc_type, number, doc_date, currency, suma_netto, suma_vat, suma_brutto)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (doc_type, number, doc_date, currency, suma_netto, suma_vat, suma_brutto))
        self.conn.commit()
        return int(cur.lastrowid)

    def receipt_from_line(self, document_id: int, item_id: int,
                          qty: Decimal, unit_price: Decimal, line_netto: Decimal,
                          vat_proc: Optional[Decimal], currency: str = "PLN") -> None:
        cur = self.conn.cursor()
        cur.callproc('sp_receipt_from_line', (
            int(document_id), int(item_id),
            str(qty.quantize(Decimal('0.001'))),
            str(unit_price.quantize(Decimal('0.0001'))),
            str(line_netto.quantize(Decimal('0.01'))),
            vat_proc, currency
        ))
        self.conn.commit()

    # -------------------- ISSUE/RETURN delegowane --------------------
    def create_operation(
        self,
        *,
        kind: str,
        station: str,
        operator_user_id: int,
        employee_user_id: int,
        lines: list[tuple[int, int]],
        issued_without_return: bool,
        note: str,
        operation_uuid: Optional[str] = None,
    ) -> str:
        """@deprecated Deleguje do AuthRepo."""
        op_uuid = operation_uuid or str(uuid.uuid4())
        if kind.upper() == "ISSUE":
            for item_id, qty in lines:
                self._auth_repo.issue_tool(
                    employee_id=employee_user_id,
                    item_id=int(item_id),
                    qty=qty,
                    operation_uuid=str(uuid.uuid4()),
                )
        elif kind.upper() == "RETURN":
            for item_id, qty in lines:
                self._auth_repo.return_tool(
                    employee_id=employee_user_id,
                    item_id=item_id,
                    qty=qty,
                    operation_uuid=str(uuid.uuid4()),
                )
        else:
            raise ValueError("Unsupported kind")
        return op_uuid

    # legacy helper (raczej już nieużywany)
    def _employee_display_name(self, emp_id: int, cur) -> Optional[str]:
        cur.execute("SELECT CONCAT(first_name,' ',last_name) AS nm FROM employees WHERE id=%s", (emp_id,))
        row = cur.fetchone()
        return row["nm"] if row and row.get("nm") else None
