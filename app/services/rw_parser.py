# app/services/rw_parser.py
from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any

# korzystamy z Twojego istniejącego parsera:
# app/services/rw/parser.py -> funkcja parse_rw_pdf(pdf_path: str, debug_path: str | None = None) -> ParsedRW
from app.services.rw.parser import parse_rw_pdf as _parse_rw_pdf


def parse_rw_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Adapter: wywołuje Twój rozbudowany parser i zamienia wynik na listę prostych rekordów,
    jakich oczekuje reszta patcha (repo + UI dialog).
    """
    parsed = _parse_rw_pdf(pdf_path, debug_path=None)

    doc_no = parsed.rw_no or ""
    # parsed.rw_date w Twoim parserze to 'DD-MM-YYYY' (string) lub None
    doc_date = parsed.rw_date or ""

    # U Ciebie podpowiedź pracownika to parsed.employee_hint (np. "J.Kowalski" / "Jan Kowalski")
    employee = (parsed.employee_hint or "").strip()

    out: List[Dict[str, Any]] = []
    for ln in parsed.lines:
        out.append(
            {
                "doc_no": doc_no,
                "doc_date": doc_date,
                "employee_name": employee or None,
                "item_sku": ln.sku_src,
                "qty": float(ln.qty),
                "notes": "",
                "parse_confidence": 1.0,
            }
        )
    return out
