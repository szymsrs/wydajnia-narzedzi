"""Domain service for inventory counting using MySQL stored procedures."""

from __future__ import annotations
from typing import Set

_processed_ops: Set[str] = set()


def inventory_count(db_conn, item_id: int, counted_qty, *, operation_uuid: str, rfid_confirmed: bool) -> dict:
    """Register counted quantity of an item."""
    if not rfid_confirmed:
        return {"status": "rfid_unconfirmed"}
    if operation_uuid in _processed_ops:
        return {"status": "duplicate"}

    with db_conn:
        cur = db_conn.cursor()
        cur.callproc('sp_inventory_count', (item_id, str(counted_qty), operation_uuid))
        db_conn.commit()

    _processed_ops.add(operation_uuid)
    return {"status": "success"}
