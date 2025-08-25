# app/repo/items_repo.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


class ItemsRepo:
    """Repository for basic items lookups."""

    def __init__(self, engine: Engine):
        self.engine = engine

    # ---------- API ----------
    def find_items(self, q: str, limit: int = 200) -> list[dict]:
        """Search items by SKU or name using LIKE filters."""
        sql = text(
            """
            SELECT id, sku, name
            FROM items
            WHERE (
                sku  LIKE CONCAT('%', :q, '%')
                OR name LIKE CONCAT('%', :q, '%')
            )
            ORDER BY sku
            LIMIT :lim
            """
        )
        with self.engine.connect() as conn:
            rows = (
                conn.execute(sql, {"q": q, "lim": int(limit)})
                .mappings()
                .all()
            )
        return [dict(r) for r in rows]

    def get_item_id_by_sku(self, sku: str) -> int | None:
        sql = text("SELECT id FROM items WHERE sku = :sku")
        with self.engine.connect() as conn:
            row = conn.execute(sql, {"sku": sku}).scalar_one_or_none()
        return int(row) if row is not None else None