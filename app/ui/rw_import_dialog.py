# app/ui/rw_import_dialog.py
from __future__ import annotations

import uuid
from typing import List, Dict, Any
from PySide6 import QtWidgets, QtCore
from pathlib import Path

from app.services.rw.parser import parse_rw_pdf
from app.dal.rw_import_repo import RWImportRepo


class RWImportDialog(QtWidgets.QDialog):
    """Import dokumentów RW z pliku PDF (przyjęcie na stan wydajni)."""

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import RW (PDF)")
        self.resize(800, 600)

        # --- sesja / station z okna głównego (jeśli dostępne)
        session = {}
        station = None
        try:
            if parent and hasattr(parent, "session"):
                session = getattr(parent, "session", {}) or {}
            # próbujemy też wyciągnąć station, jeśli jest przechowywana w parent/settings
            if parent and hasattr(parent, "station"):
                station = getattr(parent, "station")
            elif parent and hasattr(parent, "settings"):
                st = getattr(parent, "settings", None)
                if isinstance(st, dict):
                    station = st.get("station")
                else:
                    # obiekt z atrybutem station
                    station = getattr(st, "station", None)
        except Exception:
            pass

        # repo ma teraz dostęp do session (user_id do audytu) i opcjonalnie station
        self.repo = RWImportRepo(engine, session=session, station=station)

        self.records: List[Dict[str, Any]] = []

        self.file_edit = QtWidgets.QLineEdit()
        btn_browse = QtWidgets.QPushButton("Wybierz PDF")
        btn_browse.clicked.connect(self._choose_file)
        btn_parse = QtWidgets.QPushButton("Parsuj")
        btn_parse.clicked.connect(self._parse)
        top = QtWidgets.QHBoxLayout()
        top.addWidget(self.file_edit, 1)
        top.addWidget(btn_browse)
        top.addWidget(btn_parse)

        # --- Tabela: 6 kolumn, w tym nowa "Cena netto"
        self.table = QtWidgets.QTableWidget(0, 6)  # było 5
        self.table.setHorizontalHeaderLabels(
            ["RW", "Data", "Nazwa", "SKU", "Ilość", "Cena netto"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeToContents
        )
        # rozciągamy kolumnę "Nazwa"
        self.table.horizontalHeader().setSectionResizeMode(
            2, QtWidgets.QHeaderView.Stretch
        )

        self.chk_iwr = QtWidgets.QCheckBox("oznacz jako issued_without_return")
        self.chk_iwr.setChecked(True)

        btn_save = QtWidgets.QPushButton("Zapisz do DB")
        btn_save.clicked.connect(self._save)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table, 1)
        lay.addWidget(self.chk_iwr)
        lay.addWidget(btn_save, 0, QtCore.Qt.AlignRight)

    def _choose_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Wybierz plik PDF", "", "PDF Files (*.pdf)"
        )
        if path:
            self.file_edit.setText(path)

    def _parse(self):
        path = self.file_edit.text().strip()
        if not path:
            return
        dbg_path = str(Path(path).with_suffix(Path(path).suffix + ".dbg.txt"))
        pr = parse_rw_pdf(path, debug_path=dbg_path)
        # spłaszczamy na rekordy do UI/DB, zachowując unit_price
        self.records = []
        for p in pr.lines:
            self.records.append({
                "doc_no": pr.rw_no or "",
                "doc_date": pr.rw_date or "",
                "item_name": p.name_src,
                "item_sku": p.sku_src,
                "qty": float(p.qty),
                "unit_price": float(p.unit_price or 0.0),   # <-- potrzebne do DB i UI
                "parse_confidence": 1.0,
                "source_file": path,
            })

        # UI
        self.table.setRowCount(len(self.records))
        for r, rec in enumerate(self.records):
            price = float(rec.get("unit_price") or 0.0)
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(rec["doc_no"]))
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(rec["doc_date"]))
            self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(rec["item_name"]))
            self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(rec["item_sku"]))
            self.table.setItem(r, 4, QtWidgets.QTableWidgetItem(str(rec["qty"])))
            self.table.setItem(r, 5, QtWidgets.QTableWidgetItem(f"{price:.2f}"))  # NOWE

    def _save(self):
        if not self.records:
            return

        headers: Dict[str, int] = {}
        for rec in self.records:
            # pozycja (utworzy jeśli trzeba)
            item_id = self.repo.upsert_item(
                rec["item_sku"],
                rec.get("item_name")
            )
            key = rec["doc_no"] or "RW/NO-NUM"
            if key not in headers:
                headers[key] = self.repo.insert_rw_header(
                    rec["doc_no"],
                    rec["doc_date"],
                    self.chk_iwr.isChecked(),
                    rec.get("source_file", self.file_edit.text()),
                    rec["parse_confidence"],
                )
            # linia: qty + unit_price (NOT NULL w DB → fallback 0.0 już zapewniony)
            self.repo.insert_rw_line(
                headers[key],
                item_id,
                rec["qty"],
                rec.get("unit_price", 0.0),
                rec["parse_confidence"],
            )

        # --- employee_id do audytu (z sesji okna głównego)
        emp_id = None
        try:
            mw = self.parent()
            if mw and hasattr(mw, "session"):
                emp_id = mw.session.get("user_id")
        except Exception:
            pass

        # commit z operation_uuid i operator-em
        self.repo.commit_transaction(str(uuid.uuid4()), employee_id=emp_id)

        QtWidgets.QMessageBox.information(
            self, "RW", f"Zapisano {len(self.records)} linii."
        )
        self.accept()
