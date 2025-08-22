from __future__ import annotations
from typing import List, Dict, Any
from app.services.rw.parser import parse_rw_pdf as _parse_rw_pdf

def parse_rw_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    parsed = _parse_rw_pdf(pdf_path, debug_path=None)
    doc_no = parsed.rw_no or ""
    doc_date = parsed.rw_date or ""
    employee = (parsed.employee_hint or "").strip()

    out: List[Dict[str, Any]] = []
    for ln in parsed.lines:
        out.append({
            "doc_no": doc_no,
            "doc_date": doc_date,
            "employee_name": employee or None,
            "item_sku": ln.sku_src,
            "item_name": ln.name_src,     # NEW
            "uom": ln.uom,                # NEW
            "qty": float(ln.qty),
            "notes": "",
            "parse_confidence": 1.0,
        })
    return out
