"""Domain service for registering RW receipts using MySQL stored procedures."""

from __future__ import annotations
from typing import Set

_processed_ops: Set[str] = set()


def record_rw_receipt(db_conn, document_id: int, item_id: int, qty, *, operation_uuid: str, rfid_confirmed: bool) -> dict:
    """Record a receipt document (RW)."""
    if not rfid_confirmed:
        return {"status": "rfid_unconfirmed"}
    if operation_uuid in _processed_ops:
        return {"status": "duplicate"}

    with db_conn:
        cur = db_conn.cursor()
        cur.callproc('sp_rw_receipt', (document_id, item_id, str(qty), operation_uuid))
        db_conn.commit()

    _processed_ops.add(operation_uuid)
    return {"status": "success"}
