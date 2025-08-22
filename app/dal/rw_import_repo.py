# app/dal/rw_import_repo.py
from __future__ import annotations

import uuid
from typing import Optional
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import text
from sqlalchemy.engine import Engine


class RWImportRepo:
    """Zapisywanie dokumentów RW na bazie danych (przyjęcie na stan wydajni)."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self.conn = engine.connect()
        self.tx = self.conn.begin()

        # ---- rozpoznanie nazw kolumn na starcie (raz na dialog) ----
        self.items_code_col = self._detect_first_existing("items", ["sku", "code", "item_code"])
        self.items_name_col = self._detect_first_existing("items", ["name", "item_name", "title"])
        self.items_unit_col = self._detect_first_existing("items", ["unit", "uom"])

        self.doc_lines_qty_col     = self._detect_first_existing("document_lines", ["qty", "quantity"])
        self.doc_lines_price_col   = self._detect_first_existing("document_lines", ["unit_price_netto", "unit_price"])
        self.doc_lines_value_col   = self._detect_first_existing("document_lines", ["line_netto", "line_value"])
        self.doc_lines_currency_col= self._detect_first_existing("document_lines", ["currency"])
        self.doc_lines_vat_col     = self._detect_first_existing("document_lines", ["vat_proc", "vat_rate"])
        self.doc_lines_conf_col    = self._detect_first_existing("document_lines", ["parse_confidence"])

        self.stock_item_col = self._detect_first_existing("stock", ["item_id"])
        self.stock_qty_col  = self._detect_first_existing("stock", ["quantity", "qty", "amount"])

    # ---------- helpers ----------
    def _has_column(self, table: str, col: str) -> bool:
        row = self.conn.execute(text("SHOW COLUMNS FROM " + table + " LIKE :c"), {"c": col}).fetchone()
        return bool(row)

    def _detect_first_existing(self, table: str, candidates: list[str]) -> Optional[str]:
        for c in candidates:
            if self._has_column(table, c):
                return c
        return None

    def _column_not_nullable(self, table: str, col: str) -> bool:
        row = self.conn.execute(text("SHOW COLUMNS FROM " + table + " LIKE :c"), {"c": col}).fetchone()
        if not row:
            return False
        # SHOW COLUMNS: Field, Type, Null, Key, Default, Extra
        return (row[2] or "").upper() == "NO"

    # ---------- items ----------
    def upsert_item(self, sku: str, name: Optional[str] = None) -> int:
        code_col = self.items_code_col or "code"
        name_col = self.items_name_col or "name"

        row = self.conn.execute(
            text(f"SELECT id, {name_col} FROM items WHERE {code_col}=:s LIMIT 1"),
            {"s": sku}
        ).fetchone()

        if row:
            item_id = int(row[0])
            # Jeśli mamy nazwę z RW i kolumna istnieje → nadpisz, nawet jeśli w DB był SKU
            if name and self.items_name_col:
                cur_name = (row[1] or "").strip()
                if cur_name != name:
                    self.conn.execute(
                        text(f"UPDATE items SET {name_col}=:n WHERE id=:id"),
                        {"n": name, "id": item_id},
                    )
            return item_id

        # INSERT – jeśli unit jest NOT NULL, ustaw 'SZT'
        if self.items_unit_col and self._column_not_nullable("items", self.items_unit_col):
            res = self.conn.execute(
                text(f"INSERT INTO items({code_col},{name_col},{self.items_unit_col}) VALUES (:s,:n,'SZT')"),
                {"s": sku, "n": name or sku},
            )
        else:
            res = self.conn.execute(
                text(f"INSERT INTO items({code_col},{name_col}) VALUES (:s,:n)"),
                {"s": sku, "n": name or sku},
            )
        return int(getattr(res, "lastrowid", 0))

    # ---------- documents ----------
    def insert_rw_header(
        self,
        doc_no: str,
        doc_date: str,  # w PDF mamy DD-MM-YYYY
        issued_without_return: bool,
        source_file: str,
        parse_confidence: float,
    ) -> int:
        # konwersja na YYYY-MM-DD (MySQL DATE)
        dt_sql = doc_date
        try:
            dt_sql = datetime.strptime(doc_date, "%d-%m-%Y").strftime("%Y-%m-%d")
        except Exception:
            pass

        sql = """
            INSERT INTO documents(doc_type, number, doc_date, source_file, parse_confidence
                                  {extra_cols})
            VALUES (:typ, :no, :dt, :src, :conf {extra_vals})
        """

        # employee_id pomijamy; issued_without_return dotyczy wydań do prac., więc tu tylko zapisujemy jeśli kolumna istnieje
        extra_cols = ""
        extra_vals = ""
        if self._has_column("documents", "issued_without_return"):
            extra_cols += ", issued_without_return"
            extra_vals += ", :iwr"

        params = {
            "typ": "RW",
            "no": doc_no or "",
            "dt": dt_sql,
            "src": source_file or "",
            "conf": parse_confidence,
            "iwr": 1 if issued_without_return else 0,
        }
        res = self.conn.execute(text(sql.format(extra_cols=extra_cols, extra_vals=extra_vals)), params)
        return int(getattr(res, "lastrowid", 0))

    # ---------- lines + stock ----------
    def insert_rw_line(
        self, doc_id: int, item_id: int, qty: float, unit_price: float, parse_confidence: float
    ) -> None:
        # Bezpieczne zaokrąglenia (DB często ma DECIMAL(12,4) / (12,2))
        price_dec = Decimal(str(unit_price)).quantize(Decimal("0.0000"), rounding=ROUND_HALF_UP)
        qty_dec   = Decimal(str(qty)).quantize(Decimal("0.000"), rounding=ROUND_HALF_UP)

        # 1) stock: +qty (INSERT jeśli brak)
        if self.stock_item_col and self.stock_qty_col:
            existing = self.conn.execute(
                text(f"SELECT {self.stock_qty_col} FROM stock WHERE {self.stock_item_col}=:i FOR UPDATE"),
                {"i": item_id},
            ).scalar_one_or_none()
            if existing is None:
                self.conn.execute(
                    text(f"INSERT INTO stock({self.stock_item_col},{self.stock_qty_col}) VALUES (:i,:q)"),
                    {"i": item_id, "q": float(qty_dec)},
                )
            else:
                self.conn.execute(
                    text(f"UPDATE stock SET {self.stock_qty_col}={self.stock_qty_col}+ :q WHERE {self.stock_item_col}=:i"),
                    {"q": float(qty_dec), "i": item_id},
                )

        # 2) document_lines
        qty_col = self.doc_lines_qty_col or "qty"
        cols = ["document_id", "item_id", qty_col]
        vals = [":d", ":i", ":q"]
        params = {"d": doc_id, "i": item_id, "q": float(qty_dec)}

        # unit price (NOT NULL w wielu schematach → zawsze podajemy, jeśli kolumna istnieje)
        if self.doc_lines_price_col:
            cols.append(self.doc_lines_price_col)
            vals.append(":up")
            params["up"] = float(price_dec)

        # line value (opcjonalnie – policz z qty*price, 2 miejsca)
        if self.doc_lines_value_col and self.doc_lines_price_col:
            cols.append(self.doc_lines_value_col)
            vals.append(":ln")
            line_val = (qty_dec * price_dec).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            params["ln"] = float(line_val)

        # currency (stałe PLN)
        if self.doc_lines_currency_col:
            cols.append(self.doc_lines_currency_col)
            vals.append(":cur")
            params["cur"] = "PLN"

        # vat (brak VAT na RW → NULL)
        if self.doc_lines_vat_col:
            cols.append(self.doc_lines_vat_col)
            vals.append("NULL")  # jawnie NULL w INSERT

        # parse_confidence – jeśli jest kolumna (sprawdzone raz na starcie)
        if self.doc_lines_conf_col:
            cols.append(self.doc_lines_conf_col)
            vals.append(":c")
            params["c"] = parse_confidence

        sql = f"INSERT INTO document_lines({', '.join(cols)}) VALUES ({', '.join(vals)})"
        self.conn.execute(text(sql), params)

    def commit_transaction(self, operation_uuid: Optional[str] = None) -> None:
        # log transakcji
        if self._has_column("transactions", "operation_uuid") and self._has_column("transactions", "movement_type"):
            self.conn.execute(
                text(
                    "INSERT INTO transactions(operation_uuid, movement_type, created_at)"
                    " VALUES (:u,'RECEIPT',NOW())"   # Import RW to przyjęcie na stan
                ),
                {"u": operation_uuid or str(uuid.uuid4())},
            )
        self.tx.commit()
        self.conn.close()
