# app/domain/services/return.py
"""Domain service for returning items using MySQL stored procedures,
z obsługą potwierdzenia RFID/PIN oraz feature‑flag.
"""

from __future__ import annotations
from typing import Set, Optional
import uuid

from app.core.rfid_stub import RFIDReader
from app.infra.config import FeaturesSettings
from app.ui.rfid_modal import RFIDModal

# keep track of processed operations to provide idempotency on the client side
_processed_ops: Set[str] = set()


def _confirm(reader: Optional[RFIDReader], features: Optional[FeaturesSettings]) -> bool:
    """Zwraca True, jeśli potwierdzenie RFID/PIN nie jest wymagane
    albo zostało uzyskane poprzez modal.
    """
    req = bool(getattr(features, "rfid_required", False))
    allow_pin = bool(getattr(features, "pin_fallback", True))
    if not req:
        return True
    if reader is None:
        return False
    token = RFIDModal.ask(reader, allow_pin=allow_pin)
    return bool(token)


def return_tool(
    db_conn,
    employee_id: int,
    item_id: int,
    qty,
    *,
    operation_uuid: str | None = None,
    rfid_confirmed: bool | None = None,
    reader: RFIDReader | None = None,
    features: FeaturesSettings | None = None,
) -> dict:
    """Return an item from an employee back to warehouse."""
    operation_uuid = operation_uuid or str(uuid.uuid4())

    # Potwierdzenie RFID/PIN (jeśli nie przekazano explicite)
    if rfid_confirmed is None:
        rfid_confirmed = _confirm(reader, features)
    if not rfid_confirmed:
        return {"status": "rfid_unconfirmed"}

    # Idempotencja po potwierdzeniu
    if operation_uuid in _processed_ops:
        return {"status": "duplicate"}

    # Wykonanie procedury w DB
    with db_conn:
        cur = db_conn.cursor()
        cur.callproc("sp_return_tool", (employee_id, item_id, str(qty), operation_uuid))
        db_conn.commit()

    _processed_ops.add(operation_uuid)
    return {"status": "success"}
