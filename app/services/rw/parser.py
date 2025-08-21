# app/services/rw/parser.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Callable
import re, os, logging
from datetime import datetime, date
from decimal import Decimal

# ========== LOG ==========
log = logging.getLogger(__name__)
if not log.handlers:
    h = logging.StreamHandler()
    fmt = logging.Formatter('[%(asctime)s] %(levelname)s %(name)s: %(message)s')
    h.setFormatter(fmt)
    log.addHandler(h)
    log.setLevel(logging.INFO)

# ========== PDF BACKENDS ==========
try:
    import pdfplumber
    HAS_PLUMBER = True
except Exception:
    HAS_PLUMBER = False

try:
    from PyPDF2 import PdfReader
except Exception:
    PdfReader = None  # type: ignore

# ========== REGEX – NAGŁÓWEK / META ==========
RX_RW_NO     = re.compile(r"RW\s+Nr\s+([0-9\/\-]+)", re.I)
RX_DATE      = re.compile(r"data dokumentu:\s*([0-9]{2}-[0-9]{2}-[0-9]{4})", re.I)
RX_OBJECT    = re.compile(r"obiekt:\s*(.+)", re.I)
RX_UWAGI     = re.compile(r"Uwagi\s*:\s*(.+)", re.I)

# Osoba: preferuj „J.Nazwisko”, potem „Imię Nazwisko”, pomijaj „System Magazynowy”
RX_EMP_INIT = re.compile(r"\b([A-ZŻŹĆĄŚĘŁÓŃ])\.\s*([A-ZŻŹĆĄŚĘŁÓŚŹŻ][a-ząćęłńóśźż\-]+)\b")
RX_EMP_FULL = re.compile(r"\b([A-ZŻŹĆĄŚĘŁÓŃ][a-ząćęłńóśźż\-]+)\s+([A-ZŻŹĆĄŚĘŁÓŃ][a-ząćęłńóśźż\-]+)\b")

# ========== REGEX – POZYCJE ==========
# Początek wiersza pozycji (Lp + KOD, ...)
ROW_START = re.compile(r"^\s*\d+\s+[^,]+,\s*", re.U)

# Pełny wzorzec pozycji; cena i wartość są opcjonalne (na części RW może ich nie być)
ITEM_RE = re.compile(
    r"""
    ^\s*
    (?P<lp>\d+)\s+                                 # Lp
    (?P<code>[^,]+?),\s+                           # KOD (do przecinka)
    (?P<name>.+?)\s+                               # NAZWA
    (?P<uom>SZT|szt|kg|m|para)\s+                  # JM
    (?P<qty>\d{1,3}(?:[ \u00A0]\d{3})*(?:,\d{3})|\d+,\d{3})   # Ilość (PL)
    (?:\s+\S+.*)?                                  # reszta (opc.)
    (?:\s+(?P<price>\d{1,3}(?:[ \u00A0.]?\d{3})*,\d{2})\s+(?P<value>\d{1,3}(?:[ \u00A0.]?\d{3})*,\d{2}))?
    \s*$""",
    re.X | re.U
)

NBSP = "\u00A0"

# ========== UTILS ==========
def _clean(s: str) -> str:
    s = s.replace(NBSP, " ")
    s = re.sub(r"\t+", " ", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()

def _num_qty_float_pl(s: str) -> float:
    s = (s or "").replace(NBSP, " ").strip()
    s = s.replace(" ", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0

def _num_dec_pl(s: str, q: str = '0.01') -> Decimal:
    """Konwertuj liczby PL na Decimal (kwoty)."""
    s = (s or "").replace(NBSP, " ").strip()
    s = s.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return Decimal(s).quantize(Decimal(q))
    except Exception:
        return Decimal('0.00').quantize(Decimal(q))

def _parse_pl_date(s: Optional[str]) -> Optional[date]:
    # Oczekiwany format z nagłówka: DD-MM-YYYY
    if not s:
        return None
    try:
        return datetime.strptime(s, "%d-%m-%Y").date()
    except Exception:
        return None

# ========== PDF → LINES ==========
def _pdf_lines_plumber(path: str) -> List[str]:
    laparams = dict(char_margin=2.0, line_margin=0.3, word_margin=0.1, boxes_flow=0.3)
    out: List[str] = []
    with pdfplumber.open(path, laparams=laparams) as pdf:
        for page in pdf.pages:
            txt = page.extract_text(x_tolerance=1, y_tolerance=1) or ""
            for ln in txt.splitlines():
                ln = _clean(ln)
                if ln:
                    out.append(ln)
    BL = (":: System Magazynowy ::", "strona :", "Wystawił", "Zatwierdził", "Pobrał")
    return [ln for ln in out if not any(b in ln for b in BL)]

def _pdf_lines_pypdf2(path: str) -> List[str]:
    if PdfReader is None:
        return []
    r = PdfReader(path)
    out: List[str] = []
    for p in r.pages:
        t = p.extract_text() or ""
        for ln in t.splitlines():
            ln = _clean(ln)
            if ln:
                out.append(ln)
    BL = (":: System Magazynowy ::", "strona :", "Wystawił", "Zatwierdził", "Pobrał")
    return [ln for ln in out if not any(b in ln for b in BL)]

def _pdf_to_lines(path: str, dbg: list[str]) -> List[str]:
    if HAS_PLUMBER:
        try:
            dbg.append("EXTRACTOR: pdfplumber")
            return _pdf_lines_plumber(path)
        except Exception as e:
            dbg.append(f"pdfplumber failed: {e!r}")
    dbg.append("EXTRACTOR: PyPDF2")
    return _pdf_lines_pypdf2(path)

def _group_item_rows(lines: List[str]) -> List[str]:
    items: List[str] = []
    buf: list[str] = []
    for ln in lines:
        if ROW_START.match(ln):
            if buf:
                items.append(_clean(" ".join(buf)))
                buf = []
            buf.append(ln)
        else:
            if buf:
                buf.append(ln)
    if buf:
        items.append(_clean(" ".join(buf)))
    return items

def _employee_hint(txt_all: str) -> Optional[str]:
    for m in RX_UWAGI.finditer(txt_all):
        line = m.group(1)
        mi = RX_EMP_INIT.search(line)
        if mi:
            return f"{mi.group(1)}.{mi.group(2)}"
    mi = RX_EMP_INIT.search(txt_all)
    if mi:
        return f"{mi.group(1)}.{mi.group(2)}"
    for m in RX_UWAGI.finditer(txt_all):
        line = m.group(1)
        mf = RX_EMP_FULL.search(line)
        if mf and not (mf.group(1) == "System" and mf.group(2) == "Magazynowy"):
            return f"{mf.group(1)} {mf.group(2)}"
    mf = RX_EMP_FULL.search(txt_all)
    if mf and not (mf.group(1) == "System" and mf.group(2) == "Magazynowy"):
        return f"{mf.group(1)} {mf.group(2)}"
    return None

# ========== TYPY ==========
@dataclass
class ParsedLine:
    sku_src: str
    name_src: str
    uom: str
    qty: float
    unit_price: Optional[Decimal] = None  # netto / szt. jeśli jest w PDF
    line_value: Optional[Decimal] = None  # wartość netto linii (jeśli jest)

@dataclass
class ParsedRW:
    rw_no: Optional[str]
    rw_date: Optional[str]            # DD-MM-YYYY (z PDF)
    employee_hint: Optional[str]
    object: Optional[str]
    lines: List[ParsedLine]
    # Uzupełniane podczas importu:
    parsed_doc_date: Optional[date] = None

# ========== PARSER GŁÓWNY ==========
def parse_rw_pdf(pdf_path: str, *, debug_path: str | None = None) -> ParsedRW:
    dbg: list[str] = []
    dbg.append(f"FILE: {pdf_path}")
    dbg.append(f"TIME: {datetime.now().isoformat(timespec='seconds')}")

    lines = _pdf_to_lines(pdf_path, dbg)
    dbg.append(f"LINES ({len(lines)}):")
    for i, ln in enumerate(lines, 1):
        dbg.append(f"{i:03d}: {ln}")

    full_text = "\n".join(lines)

    rw_no   = (RX_RW_NO.search(full_text)   or [None, None])[1]
    rw_date = (RX_DATE.search(full_text)    or [None, None])[1]
    obj     = (RX_OBJECT.search(full_text)  or [None, None])[1]
    emp     = _employee_hint(full_text)

    dbg.append(f"HEADER: rw_no={rw_no!r} rw_date={rw_date!r} object={obj!r} employee_hint={emp!r}")

    # odetnij do pierwszej pozycji (Lp 1)
    start_idx = 0
    for i, ln in enumerate(lines):
        if ln.strip().startswith("1 "):
            start_idx = i
            break
    body = lines[start_idx:]

    raw_items = _group_item_rows(body)
    dbg.append(f"RAW ITEMS ({len(raw_items)}):")
    for i, raw in enumerate(raw_items, 1):
        dbg.append(f"[RAW {i}] {raw}")

    parsed: List[ParsedLine] = []
    dbg.append("PARSE RESULTS:")
    for i, raw in enumerate(raw_items, 1):
        m = ITEM_RE.match(raw)
        if not m:
            # diagnostyka: czy wiersz ma JM / ilość?
            has_uom = bool(re.search(r"\b(SZT|szt|kg|m|para)\b", raw))
            qty_try = re.search(r"\d{1,3}(?:[ \u00A0]\d{3})*(?:,\d{3})|\d+,\d{3}", raw)
            dbg.append(f"[FAIL {i}] no match; has_uom={has_uom} qty_found={bool(qty_try)} raw={raw}")
            continue
        code = _clean(m.group("code"))
        name = _clean(m.group("name"))
        uom  = m.group("uom").upper()
        qty  = _num_qty_float_pl(m.group("qty"))
        # Ceny opcjonalne
        price = _num_dec_pl(m.group("price")) if m.group("price") else None
        value = _num_dec_pl(m.group("value")) if m.group("value") else None

        parsed.append(ParsedLine(
            sku_src=code, name_src=name, uom=uom, qty=qty,
            unit_price=price, line_value=value
        ))
        dbg.append(f"[OK   {i}] code={code!r} name={name!r} uom={uom} qty={qty} price={price} value={value}")

    if debug_path:
        try:
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write("\n".join(dbg))
        except Exception:
            pass  # nie blokuj parsowania na logu

    return ParsedRW(
        rw_no=rw_no,
        rw_date=rw_date,
        employee_hint=emp,
        object=obj,
        lines=parsed,
        parsed_doc_date=_parse_pl_date(rw_date)
    )

# ========== IMPORT DO DB (PyMySQL + SP) ==========
"""
Wymagania w DB:
- tabele: documents, document_lines, lots, movements, movement_allocations
- procedura: sp_receipt_from_line(document_id, item_id, qty, unit_price, line_netto, vat_proc, currency)

Sposób użycia z aplikacji:

    import pymysql
    from app.services.rw.parser import import_rw_pdf

    conn = pymysql.connect(host=..., user=..., password=..., database=..., autocommit=False)

    def map_sku_to_item_id(sku: str, name: str, uom: str) -> int:
        # TODO: Twoja logika (SELECT z items po sku; ewentualnie create-if-missing)
        ...

    with conn:
        imported = import_rw_pdf(
            pdf_path="C:/sciezka/do/plik.pdf",
            db_conn=conn,
            item_mapper=map_sku_to_item_id,
            default_currency="PLN"
        )
        # imported: dict z podsumowaniem, np. {"document_id": 123, "lines": 5, "rw_no": "..."}
"""

def _create_document(cursor, doc_type: str, number: str, doc_date: date, currency: str,
                     suma_netto: Optional[Decimal] = None,
                     suma_vat: Optional[Decimal] = None,
                     suma_brutto: Optional[Decimal] = None) -> int:
    cursor.execute("""
        INSERT INTO documents(doc_type, number, doc_date, currency, suma_netto, suma_vat, suma_brutto)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
    """, (doc_type, number, doc_date, currency, suma_netto, suma_vat, suma_brutto))
    return cursor.lastrowid

def import_rw_pdf(
    pdf_path: str,
    db_conn,
    item_mapper: Callable[[str, str, str], int],
    *,
    doc_type: str = "PRZYJECIE",
    doc_number: Optional[str] = None,
    doc_date_override: Optional[date] = None,
    default_currency: str = "PLN",
) -> dict:
    """
    - Parsuje PDF RW i zapisuje:
        documents -> document_lines + lots + movements (RECEIPT) + allocations
      przez procedurę sp_receipt_from_line.
    - item_mapper: funkcja mapująca (sku_src, name_src, uom) -> item_id (BIGINT w DB).
    - doc_number: jeśli None, weź z RW (rw_no); jeśli i tam nie ma, wygeneruj RW/<data>.
    - doc_date_override: jeśli podane, nadpisze datę z PDF.
    """
    parsed = parse_rw_pdf(pdf_path, debug_path=None)
    if not parsed.lines:
        raise ValueError("Parser nie znalazł żadnych pozycji w PDF.")

    # numer dokumentu
    number = (doc_number or parsed.rw_no or f"RW/{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    # data dokumentu
    ddate = doc_date_override or parsed.parsed_doc_date or date.today()

    created_id = None
    saved_lines = 0

    with db_conn:  # context manager transakcji
        cur = db_conn.cursor()

        # 1) nagłówek dokumentu
        created_id = _create_document(cur, doc_type=doc_type, number=number,
                                      doc_date=ddate, currency=default_currency,
                                      suma_netto=None, suma_vat=None, suma_brutto=None)

        # 2) wstaw każdą pozycję jako przyjęcie → partia (FIFO)
        for p in parsed.lines:
            qty = Decimal(str(p.qty)).quantize(Decimal('0.001'))
            if qty <= 0:
                continue

            # Mapowanie SKU -> item_id
            item_id = item_mapper(p.sku_src, p.name_src, p.uom)
            if not item_id or item_id <= 0:
                raise ValueError(f"Brak mapowania SKU '{p.sku_src}' → item_id")

            # Cena jednostkowa netto: z PDF jeśli jest, w przeciwnym razie 0.0000
            unit_price = (p.unit_price if p.unit_price is not None else Decimal('0.00')).quantize(Decimal('0.0001'))
            # Wartość linii netto: z PDF jeśli jest, w przeciwnym razie qty * unit_price
            line_netto = (p.line_value if p.line_value is not None else (qty * unit_price)).quantize(Decimal('0.01'))

            # VAT (opcjonalnie) – RW często nie ma, przekaż NULL
            vat_proc = None
            currency = default_currency

            # CALL sp_receipt_from_line(document_id, item_id, qty, unit_price, line_netto, vat_proc, currency)
            cur.callproc('sp_receipt_from_line', (
                int(created_id),
                int(item_id),
                str(qty),           # PyMySQL sobie poradzi ze stringiem liczby
                str(unit_price),
                str(line_netto),
                vat_proc,
                currency
            ))
            saved_lines += 1

        db_conn.commit()

    return {
        "document_id": created_id,
        "lines": saved_lines,
        "rw_no": parsed.rw_no,
        "doc_number": number,
        "doc_date": ddate.isoformat(),
        "employee_hint": parsed.employee_hint,
        "object": parsed.object
    }
