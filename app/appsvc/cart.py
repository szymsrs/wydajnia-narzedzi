from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine


# Ta klasa odpowiada za utrzymanie sesji koszyka w tabeli issue_sessions
class SessionManager:
    def __init__(self, engine: Engine, station_id: str, operator_user_id: int) -> None:
        self.engine = engine
        self.station_id = station_id
        self.operator_user_id = int(operator_user_id)

    def ensure_open_session(self, employee_id: Optional[int] = None) -> Dict:
        """
        Zapewnia istnienie aktywnej (OPEN) sesji koszyka. JeĹĽeli brak â€“ tworzy nowÄ….
        Wykorzystuje kombinacjÄ™ (operator_user_id, station_id) aby utrzymaÄ‡ jednÄ… aktywnÄ… sesjÄ™ na stanowisku.
        """
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT id, station_id, operator_user_id, employee_id, status,
                           started_at, expires_at, confirmed_at, operation_uuid
                      FROM issue_sessions
                     WHERE status='OPEN'
                       AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP())
                       AND operator_user_id = :op
                       AND (station_id = :st OR (:st IS NULL AND station_id IS NULL))
                     ORDER BY id DESC
                     LIMIT 1
                    """
                ),
                {"op": self.operator_user_id, "st": self.station_id or None},
            ).mappings().first()
            if row:
                # jeĹĽeli mamy employee_id i w sesji jest puste â€“ dopisz
                if employee_id and not row.get("employee_id"):
                    conn.execute(
                        text("UPDATE issue_sessions SET employee_id=:emp WHERE id=:id"),
                        {"emp": int(employee_id), "id": int(row["id"])},
                    )
                    row = dict(row)
                    row["employee_id"] = int(employee_id)
                return dict(row)

            # brak â€“ utwĂłrz nowÄ… sesjÄ™ OPEN
            res = conn.execute(
                text(
                    """
                    INSERT INTO issue_sessions (station_id, operator_user_id, employee_id, status, started_at)
                    VALUES (:st, :op, :emp, 'OPEN', CURRENT_TIMESTAMP())
                    """
                ),
                {"st": self.station_id or None, "op": self.operator_user_id, "emp": employee_id},
            )
            new_id = int(res.lastrowid)
            row = conn.execute(
                text(
                    "SELECT id, station_id, operator_user_id, employee_id, status, started_at FROM issue_sessions WHERE id=:id"
                ),
                {"id": new_id},
            ).mappings().first()
            return dict(row) if row else {"id": new_id, "status": "OPEN", "employee_id": employee_id}

    def cancel_session(self, session_id: int) -> None:
        """
        Oznacza sesjÄ™ jako CANCELLED (ustawia teĹĽ expires_at). Linia w issue_session_lines
        pozostajÄ… do audytu, ale sesja nie moĹĽe byÄ‡ juĹĽ zatwierdzona.
        """
        with self.engine.begin() as conn:
            conn.execute(
                text("UPDATE issue_sessions SET status='CANCELLED', expires_at=CURRENT_TIMESTAMP() WHERE id=:id"),
                {"id": int(session_id)},
            )


# Ta klasa odpowiada za operacje na pozycjach koszyka w issue_session_lines
class CartRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def _get_current_qty(self, session_id: int, item_id: int) -> Optional[float]:
        with self.engine.connect() as conn:
            val = conn.execute(
                text(
                    "SELECT qty_reserved FROM issue_session_lines WHERE session_id=:sid AND item_id=:iid LIMIT 1"
                ),
                {"sid": int(session_id), "iid": int(item_id)},
            ).scalar()
        return float(val) if val is not None else None

    def add(self, session_id: int, item_id: int, delta: float = 1.0) -> float:
        """
        ZwiÄ™ksza rezerwacjÄ™ danej pozycji o `delta`. Zwraca nowÄ… iloĹ›Ä‡. Gdy wynik <=0 â€“ usuwa liniÄ™.
        """
        current = self._get_current_qty(session_id, item_id)
        new_qty = (current or 0.0) + float(delta)
        with self.engine.begin() as conn:
            if new_qty <= 0:
                conn.execute(
                    text("DELETE FROM issue_session_lines WHERE session_id=:sid AND item_id=:iid"),
                    {"sid": int(session_id), "iid": int(item_id)},
                )
                return 0.0
            if current is None:
                conn.execute(
                    text(
                        "INSERT INTO issue_session_lines (session_id, item_id, qty_reserved) VALUES (:sid, :iid, :q)"
                    ),
                    {"sid": int(session_id), "iid": int(item_id), "q": new_qty},
                )
            else:
                conn.execute(
                    text(
                        "UPDATE issue_session_lines SET qty_reserved=:q WHERE session_id=:sid AND item_id=:iid"
                    ),
                    {"sid": int(session_id), "iid": int(item_id), "q": new_qty},
                )
        return new_qty

    def set_qty(self, session_id: int, item_id: int, qty: float) -> float:
        """
        Ustawia dokĹ‚adnÄ… iloĹ›Ä‡ rezerwacji. WartoĹ›Ä‡ 0 usuwa liniÄ™.
        """
        with self.engine.begin() as conn:
            if qty <= 0:
                conn.execute(
                    text("DELETE FROM issue_session_lines WHERE session_id=:sid AND item_id=:iid"),
                    {"sid": int(session_id), "iid": int(item_id)},
                )
                return 0.0
            cur_id = conn.execute(
                text(
                    "SELECT id FROM issue_session_lines WHERE session_id=:sid AND item_id=:iid LIMIT 1"
                ),
                {"sid": int(session_id), "iid": int(item_id)},
            ).scalar()
            if cur_id is None:
                conn.execute(
                    text(
                        "INSERT INTO issue_session_lines (session_id, item_id, qty_reserved) VALUES (:sid, :iid, :q)"
                    ),
                    {"sid": int(session_id), "iid": int(item_id), "q": float(qty)},
                )
            else:
                conn.execute(
                    text(
                        "UPDATE issue_session_lines SET qty_reserved=:q WHERE session_id=:sid AND item_id=:iid"
                    ),
                    {"sid": int(session_id), "iid": int(item_id), "q": float(qty)},
                )
        return float(qty)

    def clear(self, session_id: int) -> None:
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM issue_session_lines WHERE session_id=:sid"), {"sid": int(session_id)})

    def list_lines(self, session_id: int) -> List[Dict]:
        with self.engine.connect() as conn:
            try:
                sql = text("""
                    SELECT l.item_id, l.qty_reserved, i.sku, i.name, i.uom
                      FROM issue_session_lines l
                      JOIN items i ON i.id = l.item_id
                     WHERE l.session_id = :sid
                     ORDER BY i.name
                    """)
                rows = conn.execute(sql, {"sid": int(session_id)}).mappings().all()
            except Exception:
                sql = text("""
                    SELECT l.item_id, l.qty_reserved, i.code AS sku, i.name, i.unit AS uom
                      FROM issue_session_lines l
                      JOIN items i ON i.id = l.item_id
                     WHERE l.session_id = :sid
                     ORDER BY i.name
                    """)
                rows = conn.execute(sql, {"sid": int(session_id)}).mappings().all()
        return [dict(r) for r in rows]
    def reserved_map(self, session_id: int) -> Dict[int, float]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT item_id, qty_reserved FROM issue_session_lines WHERE session_id=:sid"),
                {"sid": int(session_id)},
            ).all()
        return {int(r[0]): float(r[1]) for r in rows}


# Ta klasa odpowiada za pobieranie dostępności z widoków magazynowych
class StockRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def list_available(self, q: str = "", limit: int = 200) -> List[Dict]:
        """
        Ładuje listę dostępnych pozycji do wydania. Najpierw próbuje policzyć stan
        z tabeli `stock` (jeśli istnieje), a jeśli się nie uda, korzysta z widoku
        `vw_stock_available`. Zwraca kolumny: item_id, sku, name, uom,
        qty_on_hand, qty_reserved_open, qty_available.
        """
        pattern = f"%{q.strip()}%" if q else "%"
        with self.engine.connect() as conn:
            # 1) Preferuj tabelę stock (agregacja + rezerwacje koszyka)
            try:
                sql = text(
                    """
                    WITH totals AS (
                        SELECT s.item_id, COALESCE(SUM(s.quantity),0) AS qty_on_hand
                          FROM stock s
                      GROUP BY s.item_id
                    ),
                    reservations AS (
                        SELECT l.item_id, COALESCE(SUM(l.qty_reserved),0) AS qty_reserved_open
                          FROM issue_sessions s
                          JOIN issue_session_lines l ON l.session_id = s.id
                         WHERE s.status='OPEN' AND (s.expires_at IS NULL OR s.expires_at > CURRENT_TIMESTAMP())
                      GROUP BY l.item_id
                    )
                    SELECT COALESCE(i.id, t.item_id) AS item_id,
                           COALESCE(i.code, CAST(t.item_id AS CHAR)) AS sku,
                           COALESCE(i.name, '') AS name,
                           COALESCE(i.unit, 'SZT') AS uom,
                           t.qty_on_hand,
                           COALESCE(r.qty_reserved_open,0) AS qty_reserved_open,
                           t.qty_on_hand - COALESCE(r.qty_reserved_open,0) AS qty_available
                      FROM totals t
                      LEFT JOIN items i ON i.id = t.item_id
                      LEFT JOIN reservations r ON r.item_id = t.item_id
                     WHERE ((i.name LIKE :q OR i.code LIKE :q) OR (:q = '%' AND 1=1))
                     ORDER BY name
                     LIMIT :lim
                    """
                )
                rows = conn.execute(sql, {"q": pattern, "lim": int(limit)}).mappings().all()
                return [dict(r) for r in rows]
            except Exception:
                pass

            # 2) Widok dostępności + i.code/i.unit
            try:
                sql = text(
                    """
                    SELECT i.id AS item_id, i.code AS sku, i.name, i.unit AS uom,
                           v.qty_on_hand, v.qty_reserved_open, v.qty_available
                      FROM vw_stock_available v
                      JOIN items i ON i.id = v.item_id
                     WHERE (i.name LIKE :q OR i.code LIKE :q)
                     ORDER BY i.name
                     LIMIT :lim
                    """
                )
                rows = conn.execute(sql, {"q": pattern, "lim": int(limit)}).mappings().all()
                return [dict(r) for r in rows]
            except Exception:
                pass

            # 3) Widok dostępności + i.sku/i.uom
            sql = text(
                """
                SELECT i.id AS item_id, i.sku, i.name, i.uom,
                       v.qty_on_hand, v.qty_reserved_open, v.qty_available
                  FROM vw_stock_available v
                  JOIN items i ON i.id = v.item_id
                 WHERE (i.name LIKE :q OR i.sku LIKE :q)
                 ORDER BY i.name
                 LIMIT :lim
                """
            )
            rows = conn.execute(sql, {"q": pattern, "lim": int(limit)}).mappings().all()
        return [dict(r) for r in rows]

# Ta klasa odpowiada za finalizację wydania (zatwierdzenie koszyka)
class CheckoutService:
    def __init__(self, engine: Engine, auth_repo_any: Any) -> None:
        self.engine = engine
        self.auth_repo = auth_repo_any

    def finalize_issue(self, session_id: int, employee_id: int) -> Dict:
        """
        PrzeksztaĹ‚ca linie w issue_session_lines na wywoĹ‚ania domenowe issue_tool.
        Po sukcesie zamyka sesjÄ™ (status=CONFIRMED). Zwraca podsumowanie.
        """
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT item_id, qty_reserved FROM issue_session_lines WHERE session_id=:sid ORDER BY item_id"),
                {"sid": int(session_id)},
            ).all()
        lines = [{"item_id": int(r[0]), "qty": float(r[1])} for r in rows]
        if not lines:
            return {"status": "empty", "lines": 0}

        import uuid
        flagged = False
        for ln in lines:
            res = self.auth_repo.issue_tool(
                employee_id=int(employee_id),
                item_id=int(ln["item_id"]),
                qty=ln["qty"],
                operation_uuid=str(uuid.uuid4()),
            )
            if res and res.get("flagged"):
                flagged = True

        with self.engine.begin() as conn:
            conn.execute(
                text("UPDATE issue_sessions SET status='CONFIRMED', confirmed_at=CURRENT_TIMESTAMP() WHERE id=:id"),
                {"id": int(session_id)},
            )

        return {"status": "success", "lines": len(lines), "flagged": flagged}


# Ta klasa odpowiada za obsĹ‚ugÄ™ karty RFID / PIN (modal + mapowanie pracownika)
class RfidService:
    def __init__(self, reader: Any | None = None) -> None:
        self.reader = reader

    def ask_token(self, parent: Any | None = None) -> Optional[str]:
        """WyĹ›wietla modal z proĹ›bÄ… o przyĹ‚oĹĽenie karty (lub PIN)."""
        try:
            from app.ui.rfid_modal import RFIDModal  # type: ignore
            return RFIDModal.ask(self.reader, allow_pin=True, timeout=10, parent=parent)
        except Exception:
            try:
                # awaryjnie prosty input tekstowy
                from PySide6 import QtWidgets
                token, ok = QtWidgets.QInputDialog.getText(
                    parent, "PrzyĹ‚ĂłĹĽ kartÄ™", "UID karty lub PIN (tryb awaryjny):"
                )
                token = (token or "").strip()
                return token if ok and token else None
            except Exception:
                return None

    def resolve_employee_id(self, repo_any: Any, token: str) -> Optional[int]:
        """Mapuje UID/PIN do employee_id korzystajÄ…c z repo (rĂłĹĽne warianty API)."""
        for name in ("get_employee_id_by_card", "get_employee_by_card", "resolve_employee_by_uid"):
            fn = getattr(repo_any, name, None)
            if callable(fn):
                try:
                    res = fn(token)
                    if isinstance(res, dict):
                        val = res.get("id") or res.get("employee_id")
                        return int(val) if val is not None else None
                    if res is None:
                        return None
                    return int(res)
                except Exception:
                    continue
        return None

    def verify_employee(self, repo_any: Any, expected_employee_id: int, parent: Any | None = None) -> bool:
        """Weryfikuje, ĹĽe token naleĹĽy do wskazanego pracownika."""
        token = self.ask_token(parent)
        if not token:
            return False
        mapped = self.resolve_employee_id(repo_any, token)
        return (mapped is not None) and (int(mapped) == int(expected_employee_id))



