from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from PySide6 import QtWidgets
from PySide6.QtCore import Qt

log = logging.getLogger(__name__)


class OpsReturnDialog(QtWidgets.QDialog):
    def __init__(self, repo: Any, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("Zwrot")

        self.station = QtWidgets.QLineEdit()
        self.operator = QtWidgets.QLineEdit()
        self.employee = QtWidgets.QLineEdit()
        self.note = QtWidgets.QLineEdit()
        self.sku = QtWidgets.QLineEdit()
        self.qty = QtWidgets.QLineEdit()
        self.qty.setPlaceholderText("np. 1 lub 3")

        form = QtWidgets.QFormLayout()
        form.addRow("Stanowisko:", self.station)
        form.addRow("ID operatora:", self.operator)
        form.addRow("ID pracownika:", self.employee)
        form.addRow("Notatka:", self.note)

        hl_item = QtWidgets.QHBoxLayout()
        hl_item.addWidget(QtWidgets.QLabel("SKU:"))
        hl_item.addWidget(self.sku)
        hl_item.addWidget(QtWidgets.QLabel("Ilość:"))
        hl_item.addWidget(self.qty)
        btnAdd = QtWidgets.QPushButton("Dodaj")
        hl_item.addWidget(btnAdd)

        self.table = QtWidgets.QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["SKU", "Ilość"])
        self.table.horizontalHeader().setStretchLastSection(True)

        btnRemove = QtWidgets.QPushButton("Usuń zaznaczone")
        btnOk = QtWidgets.QPushButton("Zwróć")
        btnCancel = QtWidgets.QPushButton("Anuluj")

        btnAdd.clicked.connect(self.on_add)
        btnRemove.clicked.connect(self.on_remove)
        btnOk.clicked.connect(self.on_ok)
        btnCancel.clicked.connect(self.reject)

        hl_actions = QtWidgets.QHBoxLayout()
        hl_actions.addWidget(btnRemove)
        hl_actions.addStretch(1)
        hl_actions.addWidget(btnOk)
        hl_actions.addWidget(btnCancel)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(hl_item)
        layout.addWidget(self.table)
        layout.addLayout(hl_actions)

    def _resolve_item_id(self, sku: str) -> int | None:
        item_id = None
        if hasattr(self.repo, "get_item_id_by_sku"):
            item_id = self.repo.get_item_id_by_sku(sku)
        if not item_id:
            try:
                item_id = int(sku)
            except Exception:
                item_id = None
        return item_id

    def on_add(self) -> None:
        try:
            sku = self.sku.text().strip()
            qty = Decimal(self.qty.text().replace(",", ".").strip() or "0")
            if not sku or qty <= 0:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Błąd",
                    "Podaj SKU i ilość > 0",
                )
                return
            item_id = self._resolve_item_id(sku)
            if not item_id:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Błąd",
                    f"Nie znaleziono SKU {sku}",
                )
                return
            r = self.table.rowCount()
            self.table.insertRow(r)
            sku_item = QtWidgets.QTableWidgetItem(sku)
            sku_item.setData(Qt.UserRole, int(item_id))
            self.table.setItem(r, 0, sku_item)
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(int(qty))))
            self.sku.clear()
            self.qty.clear()
        except Exception:
            log.exception("Błąd dodawania SKU")
            QtWidgets.QMessageBox.critical(
                self,
                "Błąd",
                "Nie udało się dodać pozycji",
            )

    def on_remove(self) -> None:
        rows = {i.row() for i in self.table.selectedIndexes()}
        for r in sorted(rows, reverse=True):
            self.table.removeRow(r)

    def on_ok(self) -> None:
        try:
            station = self.station.text().strip()
            operator_id = int(self.operator.text().strip())
            employee_id = int(self.employee.text().strip())
            note = self.note.text().strip()

            lines: list[tuple[int, int]] = []
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 0)
                if not item:
                    continue
                item_id = item.data(Qt.UserRole)
                qty_txt = self.table.item(r, 1).text().strip()
                qty = int(Decimal(qty_txt)) if qty_txt else 0
                if item_id and qty > 0:
                    lines.append((int(item_id), qty))

            if not lines:
                QtWidgets.QMessageBox.information(
                    self, "Info", "Brak pozycji do zwrotu."
                )
                return

            if (
                QtWidgets.QMessageBox.question(
                    self,
                    "Potwierdź",
                    "Czy zapisać zwrot?",
                )
                != QtWidgets.QMessageBox.Yes
            ):
                return

            self.repo.create_operation(
                kind="RETURN",
                station=station,
                operator_user_id=operator_id,
                employee_user_id=employee_id,
                lines=lines,
                issued_without_return=False,
                note=note,
            )

            QtWidgets.QMessageBox.information(self, "OK", "Zwrot zapisany.")
            log.info("Zwrot: employee=%s lines=%s", employee_id, len(lines))
            self.accept()
        except Exception:
            log.exception("Błąd zapisu zwrotu")
            QtWidgets.QMessageBox.critical(
                self,
                "Błąd",
                "Nie udało się zapisać zwrotu",
            )