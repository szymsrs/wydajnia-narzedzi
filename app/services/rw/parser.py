# app/services/rw/parser.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
import re, logging
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path

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

# Osoba – tylko hint (nie zapisujemy do DB)
RX_EMP_INIT = re.compile(r"\b([A-ZŻŹĆĄŚĘŁÓŃ])\.\s*([A-ZŻŹĆĄŚĘŁÓŚŹŻ][a-ząćęłńóśźż\-]+)\b")
RX_EMP_FULL = re.compile(r"\b([A-ZŻŹĆĄŚĘŁÓŃ][a-ząćęłńóśźż\-]+)\s+([A-ZŻŹĆĄŚĘŁÓŃ][a-ząćęłńóśźż\-]+)\b")

# ========== REGEX – POZYCJE ==========
ROW_START = re.compile(r"^\s*\d+\s+[^,]+,\s*", re.U)

# utnij raw po pierwszej parze "cena wartość"
RAW_CUT_AFTER_PRICE_VALUE = re.compile(
    r"^(?P<head>.*?\b\d{1,3}(?:[ \u00A0.]?\d{3})*,\d{2}\s+\d{1,3}(?:[ \u00A0.]?\d{3})*,\d{2})\b.*$",
    re.U
)

# Ilość dopuszcza: 1; 1,00; 1 234; 1 234,00; 4.00 itd.
# Dodany opcjonalny MAGAZYN po ilości (np. KOŹMIN), a potem CENA i WARTOŚĆ.
ITEM_RE = re.compile(
    r"""
    ^\s*
    (?P<lp>\d+)\s+                                 # Lp
    (?P<code>[^,]+?),\s+                           # KOD (do przecinka)
    (?P<name>.+?)\s+                               # NAZWA
    (?P<uom>SZT|szt|kg|m|para)\s+                  # JM
    (?P<qty>
        \d{1,3}(?:[ \u00A0]\d{3})*(?:[.,]\d{2,3})? # 1 234,00 / 1 234 / 1,00
        |\d+(?:[.,]\d{2,3})?                       # 1 / 1,00
    )
    (?:\s+(?P<wh>[A-ZĄĆĘŁŃÓŚŹŻ][\wĄĆĘŁŃÓŚŹŻąćęłńóśźż\-]*))?   # MAGAZYN, np. KOŹMIN
    \s+(?P<price>\d{1,3}(?:[ \u00A0.]?\d{3})*,\d{2})           # CENA
    \s+(?P<value>\d{1,3}(?:[ \u00A0.]?\d{3})*,\d{2})           # WARTOŚĆ
    \s*$""",
    re.X | re.U
)

NBSP = "\u00A0"

# ========== UTILS ==========
def _clean(s: str) -> str:
    s = (s or "").replace(NBSP, " ")
    s = re.sub(r"\t+", " ", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()

def _num_qty_float_pl(s: str) -> float:
    s = (s or "").replace(NBSP, " ").strip()
    s = s.replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0

def _num_dec_pl(s: str, q: str = '0.01') -> Decimal:
    s = (s or "").replace(NBSP, " ").strip()
    s = s.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return Decimal(s).quantize(Decimal(q))
    except Exception:
        return Decimal(q).quantize(Decimal(q))

def _parse_pl_date(s: Optional[str]) -> Optional[date]:
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
    unit_price: Optional[Decimal] = None  # netto / szt. (4 miejsca)
    line_value: Optional[Decimal] = None  # wartość pozycji (2 miejsca)

@dataclass
class ParsedRW:
    rw_no: Optional[str]
    rw_date: Optional[str]            # DD-MM-YYYY
    employee_hint: Optional[str]
    object: Optional[str]
    lines: List[ParsedLine]
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
        # utnij wszystko po pierwszej parze "cena wartość" (eliminuje sumy/stopki)
        cut = RAW_CUT_AFTER_PRICE_VALUE.sub(r"\g<head>", raw) if RAW_CUT_AFTER_PRICE_VALUE.search(raw) else raw
        if cut != raw:
            dbg.append(f"[TRIM {i}] {cut}")

        m = ITEM_RE.match(cut)
        if not m:
            has_uom = bool(re.search(r"\b(SZT|szt|kg|m|para)\b", cut))
            qty_try = re.search(r"\d+(?:[ \u00A0]\d{3})*(?:[.,]\d{2,3})?|\d+(?:[.,]\d{2,3})?", cut)
            dbg.append(f"[FAIL {i}] no match; has_uom={has_uom} qty_found={bool(qty_try)} raw={cut}")
            continue

        code = _clean(m.group("code"))
        name = _clean(m.group("name"))
        uom  = m.group("uom").upper()
        qty  = _num_qty_float_pl(m.group("qty"))
        price = _num_dec_pl(m.group("price"), '0.0000')
        value = _num_dec_pl(m.group("value"), '0.01')

        parsed.append(ParsedLine(
            sku_src=code, name_src=name, uom=uom, qty=qty,
            unit_price=price, line_value=value
        ))
        dbg.append(
            f"[OK   {i}] code={code!r} name={name!r} uom={uom} qty={qty} price={price} value={value} wh={m.group('wh') or '—'}"
        )

    # Zapis debug – zawsze obok PDF, jeśli nie podano
    if not debug_path:
        debug_path = str(Path(pdf_path).with_suffix(Path(pdf_path).suffix + ".dbg.txt"))
    try:
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write("\n".join(dbg))
    except Exception:
        pass

    log.info("[RW parser] Plik: %s | linie=%d | pozycje=%d | debug=%s",
             pdf_path, len(lines), len(parsed), debug_path)

    return ParsedRW(
        rw_no=rw_no,
        rw_date=rw_date,
        employee_hint=emp,
        object=obj,
        lines=parsed,
        parsed_doc_date=_parse_pl_date(rw_date)
    )
