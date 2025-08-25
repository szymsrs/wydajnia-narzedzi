# app/dal/items_repo.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


class ItemsRepo:
    """Access layer for basic items lookup operations."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def find_items(self, q: str, limit: int = 50) -> list[dict]:
        """Search items by SKU or name using a simple LIKE filter."""

        sql = text(
            """
            SELECT id, sku, name
            FROM items
            WHERE (
                :q = ''
                OR sku  LIKE CONCAT('%', :q, '%')
                OR name LIKE CONCAT('%', :q, '%')
            )
            ORDER BY name, sku
            LIMIT :lim
            """
        )
        params = {"q": q or "", "lim": int(limit)}
        with self.engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
        return [dict(r) for r in rows]

    def get_item_id_by_sku(self, sku: str) -> int | None:
        """Return item ID for the given SKU or ``None`` if missing."""

        sql = text("SELECT id FROM items WHERE sku = :sku LIMIT 1")
        with self.engine.connect() as conn:
            row = conn.execute(sql, {"sku": sku.strip()}).scalar_one_or_none()
        return int(row) if row is not None else None
