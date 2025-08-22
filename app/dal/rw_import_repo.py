# app/dal/rw_import_repo.py
from __future__ import annotations

import uuid
from typing import Optional
from sqlalchemy import text
from sqlalchemy.engine import Engine


class RWImportRepo:
    """Zapisywanie dokumentów RW na bazie danych."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self.conn = engine.connect()
        self.tx = self.conn.begin()

    def upsert_employee(self, name: str) -> int:
        first, *rest = (name or "").strip().split(" ", 1)
        last = rest[0] if rest else ""
        row = self.conn.execute(
            text(
                "SELECT id FROM employees WHERE first_name=:f AND last_name=:l LIMIT 1"
            ),
            {"f": first, "l": last},
        ).fetchone()
        if row:
            return int(row[0])
        res = self.conn.execute(
            text("INSERT INTO employees(first_name,last_name) VALUES (:f,:l)"),
            {"f": first, "l": last},
        )
        return int(res.lastrowid)  # type: ignore[attr-defined]

    def upsert_item(self, sku: str, name: Optional[str] = None) -> int:
        row = self.conn.execute(
            text("SELECT id FROM items WHERE sku=:s LIMIT 1"), {"s": sku}
        ).fetchone()
        if row:
            return int(row[0])
        res = self.conn.execute(
            text("INSERT INTO items(sku,name) VALUES (:s,:n)"),
            {"s": sku, "n": name or sku},
        )
        return int(res.lastrowid)  # type: ignore[attr-defined]

    def insert_rw_header(
        self,
        doc_no: str,
        doc_date: str,
        employee_id: int,
        issued_without_return: bool,
        source_file: str,
        parse_confidence: float,
    ) -> int:
        res = self.conn.execute(
            text(
                """
                INSERT INTO documents(doc_type, number, doc_date, employee_id,
                                      issued_without_return, source_file, parse_confidence)
                VALUES ('RW', :no, :dt, :emp, :iwr, :src, :conf)
                """
            ),
            {
                "no": doc_no,
                "dt": doc_date,
                "emp": employee_id,
                "iwr": 1 if issued_without_return else 0,
                "src": source_file,
                "conf": parse_confidence,
            },
        )
        return int(res.lastrowid)  # type: ignore[attr-defined]

    def insert_rw_line(
        self, doc_id: int, item_id: int, qty: float, parse_confidence: float
    ) -> None:
        stock = self.conn.execute(
            text("SELECT quantity FROM stock WHERE item_id=:i FOR UPDATE"),
            {"i": item_id},
        ).scalar_one_or_none()
        if stock is not None and stock - qty < 0:
            raise RuntimeError("negative stock")
        self.conn.execute(
            text("UPDATE stock SET quantity=quantity-:q WHERE item_id=:i"),
            {"q": qty, "i": item_id},
        )
        self.conn.execute(
            text(
                "INSERT INTO document_lines(document_id,item_id,quantity,parse_confidence)"
                " VALUES (:d,:i,:q,:c)"
            ),
            {"d": doc_id, "i": item_id, "q": qty, "c": parse_confidence},
        )

    def commit_transaction(self, operation_uuid: Optional[str] = None) -> None:
        self.conn.execute(
            text(
                "INSERT INTO transactions(operation_uuid, movement_type, created_at)"
                " VALUES (:u,'ISSUE',NOW())"
            ),
            {"u": operation_uuid or str(uuid.uuid4())},
        )
        self.tx.commit()
        self.conn.close()
