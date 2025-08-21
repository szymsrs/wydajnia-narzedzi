# app/services/rw/mapping.py
from __future__ import annotations
from typing import Any, Dict, List, Tuple
import re
from .parser import ParsedRW, ParsedLine

def _initial_and_surname(hint: str | None) -> tuple[str | None, str | None]:
    if not hint:
        return None, None
    s = hint.strip().replace(" ", "")
    # "J.Rychlik"
    m = re.match(r"^([A-ZŻŹĆĄŚĘŁÓŃ])\.([A-ZŻŹĆĄŚĘŁÓŃ][a-ząćęłńóśźż\-]+)$", s)
    if m:
        return m.group(1).upper(), m.group(2)
    # "Jan Rychlik"
    m = re.match(r"^([A-ZŻŹĆĄŚĘŁÓŃ][a-ząćęłńóśźż\-]+)\s+([A-ZŻŹĆĄŚĘŁÓŃ][a-ząćęłńóśźż\-]+)$", hint.strip())
    if m:
        return m.group(1)[0].upper(), m.group(2)
    return None, None

def resolve_employee(repo: Any, hint: str | None) -> tuple[int | None, list[dict]]:
    """
    Zwraca (employee_id, candidates). Jeśli employee_id=None i candidates != [],
    UI powinno poprosić o wybór.
    """
    init, surname = _initial_and_surname(hint)
    if not init or not surname:
        return None, []

    # Jeśli repo ma dedykowaną metodę – użyj:
    if hasattr(repo, "find_employees_by_initial_and_surname"):
        rows = repo.find_employees_by_initial_and_surname(hint) or []
        if len(rows) == 1:
            return rows[0]["id"], rows
        return None, rows

    # Fallback: przefiltruj wyniki list_employees(surname)
    rows = repo.list_employees(surname) or []
    cands: list[dict] = []
    for r in rows:
        if not r.get("active"):
            continue
        fn = (r.get("first_name") or "")
        ln = (r.get("last_name") or "")
        if ln.strip().lower() == surname.strip().lower() and fn[:1].upper() == init:
            cands.append({"id": r["id"], "first_name": fn, "last_name": ln, "login": r.get("login")})
    if len(cands) == 1:
        return cands[0]["id"], cands
    return None, cands

def map_lines_to_items(repo: Any, parsed_lines: list[ParsedLine]) -> tuple[list[tuple[int, int]], list[dict]]:
    """
    Zwraca (mapped_lines, unresolved_items).
    mapped_lines: [(item_id, qty_int), ...]
    unresolved_items: [{sku_src, name_src, uom, qty}, ...] – do ręcznego zmapowania w UI.
    """
    mapped: list[tuple[int, int]] = []
    unresolved: list[dict] = []
    for l in parsed_lines:
        item_id = None
        if hasattr(repo, "get_item_id_by_sku"):
            item_id = repo.get_item_id_by_sku(l.sku_src)
        if not item_id and hasattr(repo, "find_item_by_name"):
            item_id = repo.find_item_by_name(l.name_src)
        if item_id:
            mapped.append((item_id, int(round(l.qty or 0))))
        else:
            unresolved.append({"sku_src": l.sku_src, "name_src": l.name_src, "uom": l.uom, "qty": l.qty})
    return mapped, unresolved
