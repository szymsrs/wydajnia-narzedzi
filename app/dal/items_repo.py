# app/dal/items_repo.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.engine import Engine


class ItemsRepo:
    """Access layer for basic items lookup operations."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def find_items(self, q: str, limit: int = 50) -> list[dict]:
        """Wyszukiwanie po SKU/kodzie lub nazwie. Zwraca id, sku, name (sku aliasuje code)."""
        q = q or ""
        pattern = f"%{q}%"
        with self.engine.connect() as conn:
            try:
                sql = text(
                    """
                    SELECT id, sku, name
                      FROM items
                     WHERE (:q = '' OR sku LIKE :q OR name LIKE :q)
                     ORDER BY name, sku
                     LIMIT :lim
                    """
                )
                rows = conn.execute(sql, {"q": pattern if q else "", "lim": int(limit)}).mappings().all()
                return [dict(r) for r in rows]
            except OperationalError:
                sql = text(
                    """
                    SELECT id, code AS sku, NULLIF(TRIM(name),'') AS name
                      FROM items
                     WHERE (:q = '' OR code LIKE :q OR name LIKE :q)
                     ORDER BY name, code
                     LIMIT :lim
                    """
                )
                rows = conn.execute(sql, {"q": pattern if q else "", "lim": int(limit)}).mappings().all()
                return [dict(r) for r in rows]

    def get_item_id_by_sku(self, sku: str) -> int | None:
        """Zwraca ID po SKU/kodzie (obsługuje 'sku' i 'code')."""
        v = (sku or "").strip()
        if not v:
            return None
        with self.engine.connect() as conn:
            try:
                row = conn.execute(text("SELECT id FROM items WHERE sku = :v LIMIT 1"), {"v": v}).scalar_one_or_none()
            except OperationalError:
                row = None
            if row is None:
                row = conn.execute(text("SELECT id FROM items WHERE code = :v LIMIT 1"), {"v": v}).scalar_one_or_none()
        return int(row) if row is not None else None
