# app/ui/rw_import_dialog.py
from __future__ import annotations

import uuid
from typing import List, Dict, Any
from PySide6 import QtWidgets, QtCore

from app.services.rw_parser import parse_rw_pdf
from app.dal.rw_import_repo import RWImportRepo


class RWImportDialog(QtWidgets.QDialog):
    """Import dokumentów RW z pliku PDF."""

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import RW (PDF)")
        self.resize(800, 600)
        self.repo = RWImportRepo(engine)
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

        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["RW", "Data", "Pracownik", "SKU", "Ilość"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeToContents
        )
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
        self.records = parse_rw_pdf(path)
        self.table.setRowCount(len(self.records))
        for r, rec in enumerate(self.records):
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(rec["doc_no"]))
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(rec["doc_date"]))
            self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(rec["employee_name"] or ""))
            self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(rec["item_sku"]))
            self.table.setItem(r, 4, QtWidgets.QTableWidgetItem(str(rec["qty"])))

    def _save(self):
        if not self.records:
            return
        headers: Dict[str, int] = {}
        for rec in self.records:
            emp_id = self.repo.upsert_employee(rec.get("employee_name") or "")
            item_id = self.repo.upsert_item(rec["item_sku"])
            key = rec["doc_no"]
            if key not in headers:
                headers[key] = self.repo.insert_rw_header(
                    rec["doc_no"],
                    rec["doc_date"],
                    emp_id,
                    self.chk_iwr.isChecked(),
                    self.file_edit.text(),
                    rec["parse_confidence"],
                )
            self.repo.insert_rw_line(
                headers[key], item_id, rec["qty"], rec["parse_confidence"]
            )
        self.repo.commit_transaction(str(uuid.uuid4()))
        QtWidgets.QMessageBox.information(
            self, "RW", f"Zapisano {len(self.records)} linii."
        )
        self.accept()
