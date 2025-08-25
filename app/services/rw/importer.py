# app/services/rw/importer.py
from __future__ import annotations
from typing import Any, Dict, Iterable, List, Tuple
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
import logging

from .parser import parse_rw_pdf
from .mapping import resolve_employee, map_lines_to_items

log = logging.getLogger(__name__)

# ───────────────────────────────────────────────────────────────────────────────
# Pomocnicze
# ───────────────────────────────────────────────────────────────────────────────

def _q_dec(val: float | str | Decimal, q: str = "0.001") -> Decimal:
    """
    Kwantyzacja do Decimal z zaokrągleniem HALF_UP.
    Domyślnie 3 miejsca dla ilości.
    """
    if isinstance(val, Decimal):
        d = val
    else:
        d = Decimal(str(val))
    return d.quantize(Decimal(q), rounding=ROUND_HALF_UP)

def _qty_to_int(qty: float | Decimal) -> int:
    """
    Twoje RW ma ilości w sztukach (u Ciebie w kodzie były castowane do int).
    Jeśli kiedyś pojawią się kg/metry, rozważ osobne ścieżki.
    """
    return int(_q_dec(qty, "0.000").to_integral_value(rounding=ROUND_HALF_UP))

def _build_lines_payload(mapped: Iterable[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """
    Normalizacja listy pozycji (item_id, qty_int) – łącz takie same item_id.
    """
    acc: Dict[int, int] = {}
    for item_id, qty in mapped:
        if qty <= 0:
            continue
        acc[item_id] = acc.get(item_id, 0) + int(qty)
    return [(it, q) for it, q in acc.items() if q > 0]

# ───────────────────────────────────────────────────────────────────────────────
# Główna funkcja importu RW → ISSUE
# ───────────────────────────────────────────────────────────────────────────────

def import_rw_pdf(
    repo: Any,
    pdf_path: str,
    *,
    operator_user_id: int,
    station: str,
    commit: bool = True,
    item_mapping: dict[str, int] | None = None,
    allow_create_missing: bool = False,
    debug_path: str | None = None,
) -> dict:
    """
    Importuje dokument RW (PDF) i tworzy wydanie (ISSUE) do pracownika.

    Parametry:
      - repo: obiekt repozytorium z metodami:
          • resolve_employee(...) – dostarczasz z .mapping
          • ensure_item(sku, name, uom)  [opcjonalnie, gdy allow_create_missing=True]
          • create_operation(kind, station, operator_user_id, employee_user_id,
                             lines, issued_without_return, note) -> op_uuid
      - pdf_path: ścieżka do pliku RW (PDF)
      - operator_user_id: id użytkownika (operatora) wykonującego import
      - station: identyfikator stanowiska (np. 'STAN-01')
      - commit: False = dry-run (zwróci podgląd bez tworzenia operacji)
      - item_mapping: ręczne dopięcie mapowania brakujących SKU → item_id
      - allow_create_missing: jeśli True i repo posiada ensure_item, brakujące SKU zostaną utworzone
      - debug_path: jeśli podasz, parser zapisze log z przebiegu

    Zwraca:
      dict z polami:
        - ok: bool
        - op_uuid: uuid operacji (gdy ok i commit=True)
        - preview: podgląd (gdy commit=False)
        - need: sekcja braków (employee/items), jeśli coś do uzupełnienia
        - rw: metadane RW (nr, data, obiekt)
        - debug_path: ścieżka logu parsowania (jeśli ustawiona)
    """
    log.info("Start importu RW: %s", pdf_path)
    try:
        # 1) Parsowanie PDF
        data = parse_rw_pdf(pdf_path, debug_path=debug_path)

        # 2) Rozpoznanie pracownika (po wskazówce z RW)
        emp_id, candidates = resolve_employee(repo, data.employee_hint)

        # 3) Automatyczne mapowanie linii RW → items (wg katalogu repo)
        mapped_lines, unresolved_items = map_lines_to_items(repo, data.lines)
        # mapped_lines: List[Tuple[item_id:int, qty:int]] (używamy int dla qty)

        # 4) Ręczne dociągnięcie mapowania (z parametru item_mapping)
        if item_mapping:
            still_unresolved: list[dict] = []
            for u in unresolved_items:
                sku = (u.get("sku_src") or "").strip()
                if sku and sku in item_mapping and item_mapping[sku]:
                    mapped_lines.append((int(item_mapping[sku]), _qty_to_int(u.get("qty") or 0)))
                else:
                    still_unresolved.append(u)
            unresolved_items = still_unresolved

        # 5) Opcjonalne auto-tworzenie brakujących pozycji
        if allow_create_missing and unresolved_items and hasattr(repo, "ensure_item"):
            created_now: list[str] = []
            for u in unresolved_items:
                sku = (u.get("sku_src") or "").strip()
                name = (u.get("name_src") or "").strip()
                uom = (u.get("uom") or "SZT").strip() or "SZT"
                if not sku:
                    continue
                new_id = repo.ensure_item(sku, name, uom)
                mapped_lines.append((int(new_id), _qty_to_int(u.get("qty") or 0)))
                created_now.append(sku)
            # odfiltruj te, które właśnie utworzyliśmy
            unresolved_items = [u for u in unresolved_items if (u.get("sku_src") or "").strip() not in created_now]

        # 6) Zbierz „need” jeśli czegoś brakuje
        need: dict = {}
        if emp_id is None:
            need["employee"] = {"hint": data.employee_hint, "candidates": candidates}
        if unresolved_items:
            # uprość strukturę na czytelny output
            simplified = []
            for u in unresolved_items:
                simplified.append({
                    "sku_src": u.get("sku_src"),
                    "name_src": u.get("name_src"),
                    "uom": u.get("uom"),
                    "qty": int(round(u.get("qty") or 0))
                })
            need["items"] = simplified

        if need:
            reason = "Potrzebne uzupełnienia (pracownik i/lub SKU)."
            log.warning("Import RW przerwany: %s", reason)
            return {
                "ok": False,
                "reason": reason,
                "rw": {"no": data.rw_no, "date": data.rw_date, "object": data.object},
                "need": need,
                "debug_path": debug_path,
            }

        # 7) Dry-run (bez tworzenia operacji)
        if not commit:
            # Połącz duplikaty itemów
            lines_payload = _build_lines_payload(mapped_lines)
            log.info("Import RW zakończony: %s", data.rw_no or "-")
            return {
                "ok": True,
                "dry_run": True,
                "preview": {
                    "employee_id": emp_id,
                    "lines": lines_payload,
                    "rw": {"no": data.rw_no, "date": data.rw_date, "object": data.object},
                },
                "debug_path": debug_path,
            }

        # 8) Commit – faktyczna operacja ISSUE
        #    Połącz duplikaty itemów (gdy kilka wierszy RW wskazało ten sam item_id)
        lines_payload = _build_lines_payload(mapped_lines)

        # Bezpieczeństwo: brak linii → nic nie rób
        if not lines_payload:
            reason = "Brak pozycji do wydania po mapowaniu."
            log.warning("Import RW przerwany: %s", reason)
            return {
                "ok": False,
                "reason": reason,
                "rw": {"no": data.rw_no, "date": data.rw_date, "object": data.object},
                "debug_path": debug_path,
            }

        # Opis notatki – do logów/raportów
        note = f"Źródło: RW {data.rw_no or ''} z {data.rw_date or ''}".strip()

        # create_operation: repo powinno:
        #  - zweryfikować kartę RFID na etapie UI (tutaj import RW zakładamy „wydania bez zwrotu”)
        #  - zapisać operację ISSUE + pozycje (FIFO na magazynie wykona kod repo/db)
        #  - ustawić issued_without_return=True (zgodnie z założeniami)
        op_uuid = repo.create_operation(
            kind="ISSUE",
            station=station,
            operator_user_id=operator_user_id,
            employee_user_id=emp_id,
            lines=lines_payload,                  # [(item_id:int, qty:int), ...]
            issued_without_return=True,
            note=note
        )

        log.info("Import RW zakończony: %s", data.rw_no or "-")
        return {
            "ok": True,
            "op_uuid": op_uuid,
            "rw": {"no": data.rw_no, "date": data.rw_date, "object": data.object},
            "debug_path": debug_path,
        }
    except Exception:
        log.exception("Import RW – błąd")
        raise
