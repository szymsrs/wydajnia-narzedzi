"""Domain service for issuing items using MySQL stored procedures."""

from __future__ import annotations
from typing import Set

# keep track of processed operations to provide idempotency on the client side
_processed_ops: Set[str] = set()


def issue_tool(db_conn, employee_id: int, item_id: int, qty, *, operation_uuid: str, rfid_confirmed: bool) -> dict:
    """Issue an item to an employee.

    Parameters
    ----------
    db_conn:
        MySQL connection object providing ``cursor`` and ``commit``.
    employee_id:
        Identifier of the employee receiving the item.
    item_id:
        Identifier of the item being issued.
    qty:
        Quantity to issue. Converted to string before passing to MySQL.
    operation_uuid:
        Unique identifier of the operation. Reused UUIDs are ignored.
    rfid_confirmed:
        Whether the employee confirmed the operation with RFID.

    Returns
    -------
    dict
        ``{"status": "success"}`` when the procedure executes,
        ``{"status": "rfid_unconfirmed"}`` when RFID was not confirmed,
        ``{"status": "duplicate"}`` when the same ``operation_uuid`` is used again.
    """
    if not rfid_confirmed:
        return {"status": "rfid_unconfirmed"}
    if operation_uuid in _processed_ops:
        return {"status": "duplicate"}

    with db_conn:
        cur = db_conn.cursor()
        # sp_issue_tool is expected to handle the business logic in the DB
        cur.callproc('sp_issue_tool', (employee_id, item_id, str(qty), operation_uuid))
        db_conn.commit()

    _processed_ops.add(operation_uuid)
    return {"status": "success"}
