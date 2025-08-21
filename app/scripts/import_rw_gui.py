# app/scripts/import_rw_gui.py
from __future__ import annotations
import os, re, sys, json
from dataclasses import dataclass
from typing import List, Optional, Any, Dict
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel, QFileDialog, QPlainTextEdit,
    QSpinBox, QMessageBox, QCheckBox, QDialog, QFormLayout,
    QDialogButtonBox, QTableWidget, QTableWidgetItem, QComboBox,
    QTabWidget, QHeaderView
)
from PySide6.QtCore import Qt

# ============================
#   PDF extract (plumber→PyPDF2)
# ============================
try:
    import pdfplumber
    HAS_PLUMBER = True
except Exception:
    HAS_PLUMBER = False

try:
    from PyPDF2 import PdfReader
except Exception:
    PdfReader = None  # type: ignore

NBSP = "\u00A0"

def _clean(s: str) -> str:
    s = s.replace(NBSP, " ")
    s = re.sub(r"\t+", " ", s)
    s = re.sub(r"[ ]{2,}", " ", s)
    return s.strip()

def _pdf_lines_plumber(path: str) -> List[str]:
    # parametry pod Heliosa
    laparams = dict(char_margin=2.0, line_margin=0.3, word_margin=0.1, boxes_flow=0.3)
    out: List[str] = []
    with pdfplumber.open(path, laparams=laparams) as pdf:
        for page in pdf.pages:
            txt = page.extract_text(x_tolerance=1, y_tolerance=1) or ""
            for ln in txt.splitlines():
                ln = _clean(ln)
                if ln:
                    out.append(ln)
    # wytnij oczywiste śmieci
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

def _extract_lines(path: str, dbg: list[str]) -> List[str]:
    if HAS_PLUMBER:
        try:
            dbg.append("EXTRACTOR: pdfplumber")
            return _pdf_lines_plumber(path)
        except Exception as e:
            dbg.append(f"pdfplumber failed: {e!r}")
    dbg.append("EXTRACTOR: PyPDF2")
    return _pdf_lines_pypdf2(path)

# ============================
#   Parsowanie RW (z debugiem)
# ============================
RX_RW_NO     = re.compile(r"RW\s+Nr\s+([0-9\/\-]+)", re.I)
RX_DATE      = re.compile(r"data dokumentu:\s*([0-9]{2}-[0-9]{2}-[0-9]{4})", re.I)
RX_OBJECT    = re.compile(r"obiekt:\s*(.+)", re.I)
RX_UWAGI     = re.compile(r"Uwagi\s*:\s*(.+)", re.I)

RX_EMP_INIT = re.compile(r"\b([A-ZŻŹĆĄŚĘŁÓŃ])\.\s*([A-ZŻŹĆĄŚĘŁÓŚŹŻ][a-ząćęłńóśźż\-]+)\b")
RX_EMP_FULL = re.compile(r"\b([A-ZŻŹĆĄŚĘŁÓŃ][a-ząćęłńóśźż\-]+)\s+([A-ZŻŹĆĄŚĘŁÓŃ][a-ząćęłńóśźż\-]+)\b")

# start pozycji: "Lp  kod, nazwa"
ROW_START = re.compile(r"^\s*\d+\s+[^,]+,\s*", re.U)

# pełna pozycja po sklejeniu (bardziej tolerancyjna ilość: 1 lub 1,000)
ITEM_RE = re.compile(
    r"""
    ^\s*
    (?P<lp>\d+)\s+                                # Lp
    (?P<code>[^,]+?),\s+                          # KOD
    (?P<name>.+?)\s+                              # NAZWA
    (?P<uom>SZT|szt|kg|m|para)\s+                 # JM
    (?P<qty>(?:\d{1,3}(?:[ \u00A0]\d{3})+|\d+)(?:,\d{3})?)  # ILOŚĆ: 1 / 1 000 / 1,000 / 54 500,000
    (?:\s+\S+.*)?                                 # reszta kolumn (opc.)
    \s*$
    """,
    re.X | re.U
)

def _num_qty(s: str) -> float:
    s = (s or "").replace(NBSP, " ").strip().replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0

@dataclass
class ParsedLine:
    sku_src: str
    name_src: str
    uom: str
    qty: float

@dataclass
class ParsedRW:
    rw_no: Optional[str]
    rw_date: Optional[str]
    employee_hint: Optional[str]
    object: Optional[str]
    lines: List[ParsedLine]
    raw_items: List[str]           # NOWE: sklejone pozycje dla podglądu
    raw_lines: List[str]           # NOWE: wszystkie linie z PDF

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

def _employee_hint(full_text: str) -> Optional[str]:
    # 1) Uwagi → inicjał+nazwisko
    for m in RX_UWAGI.finditer(full_text):
        line = m.group(1)
        mi = RX_EMP_INIT.search(line)
        if mi: return f"{mi.group(1)}.{mi.group(2)}"
    # 2) gdziekolwiek
    mi = RX_EMP_INIT.search(full_text)
    if mi: return f"{mi.group(1)}.{mi.group(2)}"
    # 3) Uwagi → Imię Nazwisko (pomijaj „System Magazynowy”)
    for m in RX_UWAGI.finditer(full_text):
        line = m.group(1)
        mf = RX_EMP_FULL.search(line)
        if mf and not (mf.group(1) == "System" and mf.group(2) == "Magazynowy"):
            return f"{mf.group(1)} {mf.group(2)}"
    mf = RX_EMP_FULL.search(full_text)
    if mf and not (mf.group(1) == "System" and mf.group(2) == "Magazynowy"):
        return f"{mf.group(1)} {mf.group(2)}"
    return None

def parse_rw_pdf(pdf_path: str, *, debug_path: str | None = None) -> ParsedRW:
    dbg: list[str] = []
    dbg.append(f"FILE: {pdf_path}")
    dbg.append(f"TIME: {datetime.now().isoformat(timespec='seconds')}")

    lines = _extract_lines(pdf_path, dbg)
    dbg.append(f"LINES ({len(lines)}):")
    for i, ln in enumerate(lines, 1):
        dbg.append(f"{i:03d}: {ln}")
    full_text = "\n".join(lines)

    rw_no   = (RX_RW_NO.search(full_text)   or [None, None])[1]
    rw_date = (RX_DATE.search(full_text)    or [None, None])[1]
    obj     = (RX_OBJECT.search(full_text)  or [None, None])[1]
    emp     = _employee_hint(full_text)

    dbg.append(f"HEADER: rw_no={rw_no!r} rw_date={rw_date!r} object={obj!r} employee_hint={emp!r}")

    # ciało od pierwszej pozycji (Lp 1)
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
            has_uom = bool(re.search(r"\b(SZT|szt|kg|m|para)\b", raw))
            qty_try = re.search(r"(?:\d{1,3}(?:[ \u00A0]\d{3})+|\d+)(?:,\d{3})?", raw)
            dbg.append(f"[FAIL {i}] has_uom={has_uom} qty_found={bool(qty_try)} raw={raw}")
            continue
        code = _clean(m.group("code"))
        name = _clean(m.group("name"))
        uom  = m.group("uom").upper()
        qty  = _num_qty(m.group("qty"))
        parsed.append(ParsedLine(sku_src=code, name_src=name, uom=uom, qty=qty))
        dbg.append(f"[OK {i}] code={code!r} name={name!r} uom={uom} qty={qty}")

    if debug_path:
        try:
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write("\n".join(dbg))
        except Exception:
            pass

    return ParsedRW(
        rw_no=rw_no,
        rw_date=rw_date,
        employee_hint=emp,
        object=obj,
        lines=parsed,
        raw_items=raw_items,
        raw_lines=lines
    )

# ============================
#   Mapowanie i importer (test)
# ============================
def resolve_employee_dummy(hint: str | None) -> tuple[int | None, list[dict]]:
    # tylko demo: „J.Rychlik” → id=2
    if hint and hint.replace(" ", "").startswith("J.Rychlik"):
        return 2, [{"id": 2, "first_name": "Jan", "last_name": "Rychlik", "login": "jr"}]
    return None, []

def map_lines_to_items(repo: Any, parsed_lines: list[ParsedLine]) -> tuple[list[tuple[int, int]], list[dict]]:
    mapped: list[tuple[int, int]] = []
    unresolved: list[dict] = []
    for l in parsed_lines:
        item_id = None
        if hasattr(repo, "get_item_id_by_sku"):
            item_id = repo.get_item_id_by_sku(l.sku_src)
        if not item_id and hasattr(repo, "find_item_by_name"):
            item_id = repo.find_item_by_name(l.name_src)
        if item_id:
            mapped.append((int(item_id), int(round(l.qty or 0))))
        else:
            unresolved.append({"sku_src": l.sku_src, "name_src": l.name_src, "uom": l.uom, "qty": l.qty})
    return mapped, unresolved

def import_rw_pdf(
    repo: Any,
    pdf_path: str,
    *,
    operator_user_id: int,
    station: str,
    commit: bool = True,
    item_mapping: dict[str, int] | None = None,
    debug_path: str | None = None,
) -> dict:
    data = parse_rw_pdf(pdf_path, debug_path=debug_path)

    emp_id, candidates = resolve_employee_dummy(data.employee_hint)
    mapped_lines, unresolved_items = map_lines_to_items(repo, data.lines)

    if item_mapping:
        rest = []
        for u in unresolved_items:
            sku = u["sku_src"]
            if sku in item_mapping and item_mapping[sku]:
                mapped_lines.append((int(item_mapping[sku]), int(round(u.get("qty") or 0))))
            else:
                rest.append(u)
        unresolved_items = rest

    need: dict = {}
    if emp_id is None:
        need["employee"] = {"hint": data.employee_hint, "candidates": candidates}
    if unresolved_items:
        need["items"] = unresolved_items

    if need:
        return {
            "ok": False,
            "reason": "Potrzebne uzupełnienia (pracownik i/lub SKU).",
            "rw": {"no": data.rw_no, "date": data.rw_date, "object": data.object},
            "need": need,
            "debug_path": debug_path,
            "parsed": data,  # zwracamy ParsedRW do podglądu
        }

    if not commit:
        return {
            "ok": True,
            "dry_run": True,
            "preview": {
                "employee_id": emp_id,
                "lines": mapped_lines,
                "rw": {"no": data.rw_no, "date": data.rw_date},
            },
            "debug_path": debug_path,
            "parsed": data,
        }

    op_uuid = repo.create_operation(
        kind="ISSUE",
        station=station,
        operator_user_id=operator_user_id,
        employee_user_id=emp_id,
        lines=mapped_lines,
        issued_without_return=True,
        note=f"Źródło: RW {data.rw_no} z {data.rw_date}",
    )
    return {"ok": True, "op_uuid": op_uuid, "debug_path": debug_path, "parsed": data}

# ============================
#   Dialog mapowania braków
# ============================
class _NewItemDialog(QDialog):
    def __init__(self, parent=None, *, sku: str = "", name: str = "", uom: str = "SZT"):
        super().__init__(parent)
        self.setWindowTitle("Nowy towar")
        self._sku = QLineEdit(sku); self._name = QLineEdit(name); self._uom = QLineEdit(uom or "SZT")
        frm = QFormLayout()
        frm.addRow("SKU:", self._sku)
        frm.addRow("Nazwa:", self._name)
        frm.addRow("JM:", self._uom)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        lay = QVBoxLayout(self); lay.addLayout(frm); lay.addWidget(btns)
    def data(self):
        return self._sku.text().strip(), self._name.text().strip(), self._uom.text().strip() or "SZT"

class RWMapDialog(QDialog):
    """Po accept(): mapping -> dict[sku_src -> item_id]"""
    def __init__(self, repo: Any, unresolved_items: List[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mapowanie pozycji RW → magazyn")
        self.repo = repo
        self.unresolved = unresolved_items
        self.mapping: Dict[str, int] = {}

        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Filtr listy towarów:"))
        self.ed_filter = QLineEdit()
        self.ed_filter.textChanged.connect(self._refill_combos)
        top.addWidget(self.ed_filter, 1)
        lay.addLayout(top)

        self.table = QTableWidget(len(unresolved_items), 6)
        self.table.setHorizontalHeaderLabels(["SKU (RW)", "Nazwa (RW)", "JM", "Ilość", "Mapa SKU", ""])
        self.table.setColumnWidth(0, 180); self.table.setColumnWidth(2, 60)
        self.table.setColumnWidth(3, 70);  self.table.setColumnWidth(4, 320)
        self.table.setColumnWidth(5, 120)

        self._all_items = self._load_items("")
        self._combo_widgets: List[QComboBox] = []

        for r, it in enumerate(unresolved_items):
            self.table.setItem(r, 0, QTableWidgetItem(str(it.get("sku_src",""))))
            self.table.setItem(r, 1, QTableWidgetItem(str(it.get("name_src",""))))
            self.table.setItem(r, 2, QTableWidgetItem(str(it.get("uom",""))))
            self.table.setItem(r, 3, QTableWidgetItem(str(it.get("qty",""))))

            combo = QComboBox(); combo.setEditable(False)
            self._combo_widgets.append(combo)
            self.table.setCellWidget(r, 4, combo)

            btn_new = QPushButton("Nowy towar…")
            btn_new.clicked.connect(lambda _=False, row=r: self._create_item_for_row(row))
            self.table.setCellWidget(r, 5, btn_new)

        lay.addWidget(self.table, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_ok); btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        self._refill_combos()

    def _load_items(self, q: str) -> List[dict]:
        if hasattr(self.repo, "search_items"):
            return self.repo.search_items(q) or []
        if hasattr(self.repo, "list_all_items"):
            return self.repo.list_all_items() or []
        return []

    def _refill_combos(self):
        flt = (self.ed_filter.text() or "").strip().lower()
        items = self._all_items
        if flt:
            items = [x for x in items if flt in (x.get("sku","") + " " + x.get("name","")).lower()]
        for combo in self._combo_widgets:
            cur = combo.currentData() if combo.count() else None
            combo.blockSignals(True); combo.clear()
            combo.addItem("— wybierz —", None)
            for x in items:
                combo.addItem(f"{x.get('sku','')} — {x.get('name','')}", x.get("id"))
            if cur is not None:
                ix = combo.findData(cur)
                combo.setCurrentIndex(ix if ix >= 0 else 0)
            combo.blockSignals(False)

    def _create_item_for_row(self, row: int):
        sku = self.table.item(row, 0).text(); name = self.table.item(row, 1).text()
        uom = self.table.item(row, 2).text() or "SZT"
        dlg = _NewItemDialog(self, sku=sku, name=name, uom=uom)
        if dlg.exec() != QDialog.Accepted: return
        sku_n, name_n, uom_n = dlg.data()
        if not sku_n or not name_n:
            QMessageBox.warning(self, "Błąd", "Wymagane: SKU i Nazwa."); return
        if not hasattr(self.repo, "create_item"):
            QMessageBox.critical(self, "Repozytorium", "Brak metody repo.create_item(sku, name, uom)."); return
        try:
            new_id = self.repo.create_item(sku_n, name_n, uom_n)
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie udało się utworzyć towaru:\n{e}"); return
        self._all_items = self._load_items("")
        self._refill_combos()
        combo = self._combo_widgets[row]
        ix = combo.findData(new_id)
        if ix >= 0: combo.setCurrentIndex(ix)

    def _on_ok(self):
        mapping: Dict[str, int] = {}
        for r, combo in enumerate(self._combo_widgets):
            item_id = combo.currentData()
            if not item_id:
                sku = self.table.item(r, 0).text()
                QMessageBox.warning(self, "Brak mapowania", f"Wiersz {r+1}: wybierz towar dla SKU {sku}.")
                return
            sku_src = self.table.item(r, 0).text()
            mapping[sku_src] = int(item_id)
        self.mapping = mapping
        self.accept()

# ============================
#   DummyRepo (testowy)
# ============================
class DummyRepo:
    def __init__(self):
        # minimalny „magazyn”
        self._items = {
            "0 641 210 023 0O": 101,  # WIERTŁO FI 2,5 NWKa [ZAPAS]
            # Możesz dodać kolejne znane SKU -> id
        }
        self._search_cache = [
            {"id": 101, "sku": "0 641 210 023 0O", "name": "WIERTŁO FI 2,5 NWKa [ZAPAS]", "uom":"SZT"},
        ]
    def get_item_id_by_sku(self, sku):
        return self._items.get(sku)
    def find_item_by_name(self, name):
        return None
    def search_items(self, q):
        q = (q or "").lower()
        return [x for x in self._search_cache if q in (x["sku"] + " " + x["name"]).lower()]
    def create_item(self, sku, name, uom):
        new_id = max([x["id"] for x in self._search_cache] + [1000]) + 1
        self._search_cache.append({"id": new_id, "sku": sku, "name": name, "uom": uom})
        self._items[sku] = new_id
        return new_id
    def create_operation(self, **kwargs):
        # tu normalnie zapis do DB
        return "uuid-demo-1234"

# ============================
#   Główne okno testera
# ============================
class ImportRWWindow(QMainWindow):
    def __init__(self, repo):
        super().__init__()
        self.repo = repo
        self.setWindowTitle("Import RW (PDF) – tester")
        self.resize(1100, 700)

        cw = QWidget(); self.setCentralWidget(cw)
        v = QVBoxLayout(cw)

        # Wybór pliku
        row1 = QHBoxLayout()
        self.ed_path = QLineEdit(); self.ed_path.setPlaceholderText("Ścieżka do pliku RW (PDF)")
        btn_browse = QPushButton("Wybierz plik…"); btn_browse.clicked.connect(self._browse)
        row1.addWidget(QLabel("Plik PDF:")); row1.addWidget(self.ed_path, 1); row1.addWidget(btn_browse)
        v.addLayout(row1)

        # Parametry + debug
        row2 = QHBoxLayout()
        self.spin_operator = QSpinBox(); self.spin_operator.setRange(1, 1_000_000); self.spin_operator.setValue(1)
        self.ed_station = QLineEdit(); self.ed_station.setText("ST-01")
        self.chk_debug = QCheckBox("Zapisz log debug obok PDF"); self.chk_debug.setChecked(True)
        row2.addWidget(QLabel("Operator (user_id):")); row2.addWidget(self.spin_operator)
        row2.addSpacing(16)
        row2.addWidget(QLabel("Stanowisko:")); row2.addWidget(self.ed_station, 1)
        row2.addWidget(self.chk_debug)
        v.addLayout(row2)

        # Akcje
        row3 = QHBoxLayout()
        btn_dry = QPushButton("Parsuj / Dry-run"); btn_dry.clicked.connect(lambda: self._run(commit=False))
        btn_run = QPushButton("Importuj (zapisz)"); btn_run.clicked.connect(lambda: self._run(commit=True))
        row3.addStretch(1); row3.addWidget(btn_dry); row3.addWidget(btn_run); v.addLayout(row3)

        # Zakładki: Wszystkie pozycje + RAW
        self.tabs = QTabWidget()
        # Tab 1: Wszystkie pozycje
        tab_all = QWidget(); la = QVBoxLayout(tab_all)
        self.tbl_all = QTableWidget(0, 5)
        self.tbl_all.setHorizontalHeaderLabels(["SKU", "Nazwa", "JM", "Ilość", "Status"])
        self.tbl_all.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        la.addWidget(self.tbl_all, 1)
        self.tabs.addTab(tab_all, "Pozycje (wszystkie)")

        # Tab 2: RAW (sklejone pozycje)
        tab_raw = QWidget(); lr = QVBoxLayout(tab_raw)
        self.tbl_raw = QTableWidget(0, 2)
        self.tbl_raw.setHorizontalHeaderLabels(["#", "Sklejona pozycja (RAW)"])
        self.tbl_raw.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl_raw.setColumnWidth(0, 60)
        lr.addWidget(self.tbl_raw, 1)
        self.tabs.addTab(tab_raw, "RAW (sklejone pozycje)")

        v.addWidget(self.tabs, 1)

        # Log
        self.out = QPlainTextEdit(); self.out.setReadOnly(True)
        v.addWidget(self.out, 1)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Wybierz RW (PDF)", "", "PDF (*.pdf)")
        if path:
            self.ed_path.setText(path)

    def _debug_path_for(self, pdf_path: str) -> str | None:
        if not self.chk_debug.isChecked(): return None
        base, _ = os.path.splitext(pdf_path)
        return base + "_debug.txt"

    # === helpers do podglądu ===
    def _fill_all_items(self, parsed_lines: List[ParsedLine], unresolved: List[dict]):
        self.tbl_all.setRowCount(len(parsed_lines))
        # status liczymy po SKU + qty (dla pewności przy duplikatach)
        unresolved_keyset = {(u["sku_src"], float(u["qty"])) for u in unresolved}
        for r, l in enumerate(parsed_lines):
            status = "NEEDS_MAP" if (l.sku_src, float(l.qty)) in unresolved_keyset else "MAPPED"
            self.tbl_all.setItem(r, 0, QTableWidgetItem(l.sku_src))
            self.tbl_all.setItem(r, 1, QTableWidgetItem(l.name_src))
            self.tbl_all.setItem(r, 2, QTableWidgetItem(l.uom))
            self.tbl_all.setItem(r, 3, QTableWidgetItem(str(l.qty)))
            st_it = QTableWidgetItem(status)
            if status == "NEEDS_MAP":
                st_it.setForeground(Qt.red)
            else:
                st_it.setForeground(Qt.darkGreen)
            self.tbl_all.setItem(r, 4, st_it)

    def _fill_raw_items(self, raw_items: List[str]):
        self.tbl_raw.setRowCount(len(raw_items))
        for i, raw in enumerate(raw_items, 1):
            self.tbl_raw.setItem(i-1, 0, QTableWidgetItem(str(i)))
            self.tbl_raw.setItem(i-1, 1, QTableWidgetItem(raw))

    # === główne uruchomienie ===
    def _run(self, commit: bool):
        pdf_path = self.ed_path.text().strip()
        if not pdf_path:
            QMessageBox.warning(self, "Brak pliku", "Wybierz plik RW (PDF)."); return
        if not os.path.exists(pdf_path):
            QMessageBox.warning(self, "Błąd", "Podany plik nie istnieje."); return

        operator_id = int(self.spin_operator.value())
        station = self.ed_station.text().strip() or "ST-01"
        debug_path = self._debug_path_for(pdf_path)

        # 1) Dry-run (zwraca także parsed/raw do podglądu)
        try:
            res = import_rw_pdf(self.repo, pdf_path, operator_user_id=operator_id, station=station, commit=False, debug_path=debug_path)
        except Exception as e:
            QMessageBox.critical(self, "Błąd importu", str(e)); return

        # Podgląd WSZYSTKICH pozycji + RAW
        parsed = res.get("parsed")
        if parsed:
            # zbuduj listę parsed_lines i unresolved (na statusy)
            parsed_lines = parsed.lines
            _, unresolved = map_lines_to_items(self.repo, parsed_lines)
            self._fill_all_items(parsed_lines, unresolved)
            self._fill_raw_items(parsed.raw_items)

        self.out.clear()
        if res.get("ok") and res.get("dry_run"):
            if debug_path and os.path.exists(debug_path):
                self.out.appendPlainText(f"[DEBUG] Zapisano log: {debug_path}\n")
            self.out.appendPlainText("DRY-RUN – podgląd danych do zapisu:\n")
            self.out.appendPlainText(json.dumps(res["preview"], ensure_ascii=False, indent=2))
            if not commit: return  # użytkownik chciał tylko podgląd

        # 2) Potrzebne uzupełnienia → mapowanie
        if not res.get("ok"):
            need = res.get("need", {})
            if debug_path and os.path.exists(debug_path):
                self.out.appendPlainText(f"[DEBUG] Zapisano log: {debug_path}\n")

            item_mapping = {}
            if "items" in need and need["items"]:
                dlg = RWMapDialog(self.repo, need["items"], self)
                if dlg.exec() != dlg.Accepted:
                    self.out.appendPlainText("Anulowano mapowanie."); return
                item_mapping = dlg.mapping

            try:
                res2 = import_rw_pdf(
                    self.repo, pdf_path,
                    operator_user_id=operator_id, station=station,
                    commit=True, item_mapping=item_mapping, debug_path=debug_path
                )
            except Exception as e:
                QMessageBox.critical(self, "Błąd importu (commit)", str(e)); return

            if res2.get("ok"):
                self.out.appendPlainText(f"OK, utworzono operację: {res2.get('op_uuid')}")
                if debug_path and os.path.exists(debug_path):
                    self.out.appendPlainText(f"[DEBUG] Zapisano log: {debug_path}")
                QMessageBox.information(self, "Sukces", f"Utworzono operację: {res2.get('op_uuid')}")
            else:
                self.out.appendPlainText("Nadal potrzebne uzupełnienia:\n" + json.dumps(res2.get("need", {}), ensure_ascii=False, indent=2))
            return

        # 3) Dry-run był kompletny → commit
        if commit:
            try:
                res3 = import_rw_pdf(self.repo, pdf_path, operator_user_id=operator_id, station=station, commit=True, debug_path=debug_path)
            except Exception as e:
                QMessageBox.critical(self, "Błąd importu (commit)", str(e)); return
            if res3.get("ok"):
                self.out.appendPlainText(f"OK, utworzono operację: {res3.get('op_uuid')}")
                if debug_path and os.path.exists(debug_path):
                    self.out.appendPlainText(f"[DEBUG] Zapisano log: {debug_path}")
                QMessageBox.information(self, "Sukces", f"Utworzono operację: {res3.get('op_uuid')}")

# ============================
#   main
# ============================
def main():
    app = QApplication(sys.argv)
    repo = DummyRepo()  # testowy magazyn w pamięci
    w = ImportRWWindow(repo)
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
