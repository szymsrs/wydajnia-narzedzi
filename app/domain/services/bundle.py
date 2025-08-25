# app/domain/services/bundle.py
"""Bundle RETURN+ISSUE operations in a single transaction."""

from __future__ import annotations
from typing import Iterable, Optional
import uuid

from app.core.rfid_stub import RFIDReader
from app.infra.config import FeaturesSettings
from app.ui.rfid_modal import RFIDModal


def _confirm(reader: Optional[RFIDReader], features: Optional[FeaturesSettings]) -> bool:
    """Sprawdza, czy wymagane jest potwierdzenie RFID/PIN i uruchamia modal."""
    req = bool(getattr(features, "rfid_required", False))
    allow_pin = bool(getattr(features, "pin_fallback", True))
    if not req:
        return True
    if reader is None:
        return False
    token = RFIDModal.ask(reader, allow_pin=allow_pin)
    return bool(token)


def issue_return_bundle(
    db_conn,
    employee_id: int,
    returns: Iterable[tuple[int, int]],
    issues: Iterable[tuple[int, int]],
    *,
    rfid_confirmed: bool | None = None,
    reader: RFIDReader | None = None,
    features: FeaturesSettings | None = None,
) -> dict:
    """Perform returns then issues in a single DB transaction.

    Parameters
    ----------
    db_conn:
        Połączenie do DB (context manager).
    employee_id:
        ID pracownika.
    returns:
        Iterable[(item_id, qty)] – pozycje do zwrotu.
    issues:
        Iterable[(item_id, qty)] – pozycje do wydania.
    rfid_confirmed:
        None – wykonaj potwierdzenie wg feature-flag; True/False – użyj podanej wartości.
    reader:
        Stub/real czytnika RFID.
    features:
        Feature-flagi.

    Returns
    -------
    dict
        {"status": "success", "flagged": bool, "returns": int, "issues": int}
    """

    if rfid_confirmed is None:
        rfid_confirmed = _confirm(reader, features)
    if not rfid_confirmed:
        return {"status": "rfid_unconfirmed"}

    flagged = False
    ret_cnt = 0
    iss_cnt = 0

    with db_conn:
        cur = db_conn.cursor()

        # najpierw zwroty
        for item_id, qty in returns or []:
            op_uuid = str(uuid.uuid4())
            cur.callproc("sp_return_tool", (employee_id, item_id, str(qty), op_uuid))
            ret_cnt += 1

        # potem wydania
        for item_id, qty in issues or []:
            op_uuid = str(uuid.uuid4())
            cur.callproc("sp_issue_tool", (employee_id, item_id, str(qty), op_uuid))
            # policz saldo dla pracownika i pozycji
            cur.execute(
                "SELECT COALESCE(SUM(CASE WHEN movement_type='ISSUE' THEN quantity ELSE -quantity END),0) "
                "FROM transactions WHERE employee_id=%s AND item_id=%s",
                (employee_id, item_id),
            )
            row = cur.fetchone()
            open_qty = row[0] if row else 0
            flag = open_qty > 0
            # ustaw flagę issued_without_return
            cur.execute(
                "UPDATE transactions SET issued_without_return=%s WHERE operation_uuid=%s",
                (1 if flag else 0, op_uuid),
            )
            flagged = flagged or flag
            iss_cnt += 1

        db_conn.commit()

    return {"status": "success", "flagged": flagged, "returns": ret_cnt, "issues": iss_cnt}
