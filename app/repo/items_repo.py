# app/repo/items_repo.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.engine import Engine


class ItemsRepo:
    """Repository for basic items lookups."""

    def __init__(self, engine: Engine):
        self.engine = engine

    # ---------- API ----------
    def find_items(self, q: str, limit: int = 200) -> list[dict]:
        """Wyszukiwanie po SKU/kodzie lub nazwie, zgodnie ze schematem (sku/code, unit/uom).

        Zwracamy zawsze klucze: id, sku, name (sku jest aliasem na code, jeżeli brak kolumny sku).
        """
        q = q or ""
        with self.engine.connect() as conn:
            try:
                sql = text(
                    """
                    SELECT id, sku, name
                      FROM items
                     WHERE (sku LIKE CONCAT('%', :q, '%') OR name LIKE CONCAT('%', :q, '%'))
                     ORDER BY sku
                     LIMIT :lim
                    """
                )
                rows = conn.execute(sql, {"q": q, "lim": int(limit)}).mappings().all()
                return [dict(r) for r in rows]
            except OperationalError:
                # fallback na kolumny 'code' i alias do 'sku'
                sql = text(
                    """
                    SELECT id, code AS sku, name
                      FROM items
                     WHERE (code LIKE CONCAT('%', :q, '%') OR name LIKE CONCAT('%', :q, '%'))
                     ORDER BY code
                     LIMIT :lim
                    """
                )
                rows = conn.execute(sql, {"q": q, "lim": int(limit)}).mappings().all()
                return [dict(r) for r in rows]

    def get_item_id_by_sku(self, sku: str) -> int | None:
        """Zwraca ID po SKU/kodzie. Obsługuje zarówno kolumnę 'sku', jak i 'code'."""
        sku = (sku or "").strip()
        if not sku:
            return None
        with self.engine.connect() as conn:
            try:
                row = conn.execute(text("SELECT id FROM items WHERE sku = :sku LIMIT 1"), {"sku": sku}).scalar_one_or_none()
                return int(row) if row is not None else None
            except OperationalError:
                row = conn.execute(
                    text("SELECT id FROM items WHERE code = :sku LIMIT 1"), {"sku": sku}
                ).scalar_one_or_none()
                return int(row) if row is not None else None
