# app/ui/exceptions_widget.py
from __future__ import annotations

from typing import TYPE_CHECKING
from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import QWidget
import csv
import logging

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.ui.shell import MainWindow
    from app.dal.exceptions_repo import ExceptionsRepo


class ExceptionsWidget(QWidget):
    """Panel wyświetlający operacje oznaczone jako issued_without_return."""

    def __init__(self, repo: ExceptionsRepo | None, parent: MainWindow):
        super().__init__(parent)
        self.repo = repo
        if not self.repo:
            lay = QtWidgets.QVBoxLayout(self)
            lbl = QtWidgets.QLabel("Brak połączenia z DB")
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            lay.addWidget(lbl)
            return
        self._build()
        self.refresh()

    def _build(self):
        tools = QtWidgets.QHBoxLayout()
        self.btn_refresh = QtWidgets.QPushButton("Odśwież")
        self.btn_export = QtWidgets.QPushButton("Eksport CSV")
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_export.clicked.connect(self.export_csv)
        tools.addWidget(self.btn_refresh)
        tools.addWidget(self.btn_export)
        tools.addStretch(1)

        self.table = QtWidgets.QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["UUID", "Pracownik", "Login", "Pozycja", "Ilość", "Data", "Ruch"]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(tools)
        layout.addWidget(self.table, 1)

    def refresh(self):
        try:
            rows = self.repo.list_exceptions() or []
        except Exception as e:
            log.exception("Błąd ładowania wyjątków")
            QtWidgets.QMessageBox.warning(self, "Błąd ładowania wyjątków", str(e))
            return
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                self.table.setItem(r, c, QtWidgets.QTableWidgetItem(str(val)))
        self.table.resizeColumnsToContents()
        log.info("Załadowano wyjątki: %s wierszy", len(rows))

    def export_csv(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Eksport CSV", filter="CSV Files (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                headers = [
                    "operation_uuid",
                    "employee",
                    "login",
                    "item",
                    "quantity",
                    "created_at",
                    "movement_type",
                ]
                writer.writerow(headers)
                for r in range(self.table.rowCount()):
                    row = [
                        self.table.item(r, c).text() if self.table.item(r, c) else ""
                        for c in range(self.table.columnCount())
                    ]
                    writer.writerow(row)
            log.info("Wyeksportowano CSV: %s (wiersze=%s)", path, self.table.rowCount())
        except Exception:
            log.exception("Błąd zapisu CSV: %s", path)
            QtWidgets.QMessageBox.critical(self, "Eksport CSV – błąd", f"Nie udało się zapisać pliku:\n{path}")
