"""Domain service for returning items using MySQL stored procedures."""

from __future__ import annotations
from typing import Set
import uuid

_processed_ops: Set[str] = set()


def return_tool(
    db_conn,
    employee_id: int,
    item_id: int,
    qty,
    *,
    operation_uuid: str | None = None,
    rfid_confirmed: bool,
) -> dict:
    """Return an item from an employee back to warehouse."""
    operation_uuid = operation_uuid or str(uuid.uuid4())

    if not rfid_confirmed:
        return {"status": "rfid_unconfirmed"}
    if operation_uuid in _processed_ops:
        return {"status": "duplicate"}

    with db_conn:
        cur = db_conn.cursor()
        cur.callproc("sp_return_tool", (employee_id, item_id, str(qty), operation_uuid))
        db_conn.commit()

    _processed_ops.add(operation_uuid)
    return {"status": "success"}
