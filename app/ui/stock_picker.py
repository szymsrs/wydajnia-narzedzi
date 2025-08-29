from __future__ import annotations
from typing import Any
from PySide6 import QtWidgets
from PySide6.QtCore import Qt

class StockPickerDialog(QtWidgets.QDialog):
    def __init__(self, repo: Any, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("Wybierz ze stanu")
        self.resize(700, 500)

        self.q = QtWidgets.QLineEdit()
        self.q.setPlaceholderText("Szukaj po nazwie lub SKU (np. 'wiertło')")
        self.btnFind = QtWidgets.QPushButton("Szukaj")
        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ID", "SKU", "Nazwa", "JM", "Dostępne"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        self.qty = QtWidgets.QLineEdit()
        self.qty.setPlaceholderText("Ilość do wydania")
        self.btnOk = QtWidgets.QPushButton("Dodaj")
        self.btnCancel = QtWidgets.QPushButton("Anuluj")

        top = QtWidgets.QHBoxLayout()
        top.addWidget(self.q)
        top.addWidget(self.btnFind)
        bottom = QtWidgets.QHBoxLayout()
        bottom.addWidget(QtWidgets.QLabel("Ilość:"))
        bottom.addWidget(self.qty)
        bottom.addStretch(1)
        bottom.addWidget(self.btnOk)
        bottom.addWidget(self.btnCancel)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table)
        lay.addLayout(bottom)

        self.btnFind.clicked.connect(self._search)
        self.table.doubleClicked.connect(self._row_to_qty)
        self.btnOk.clicked.connect(self.accept)
        self.btnCancel.clicked.connect(self.reject)

        self._items: list[dict] = []
        self._search()
        
    def _search(self, limit: int = 1000):
        try:
            self._items = self.repo.search_stock(self.q.text().strip(), limit=limit)  # AuthRepo.search_stock
        except Exception:
            QtWidgets.QMessageBox.critical(self, "Błąd", "Nie udało się pobrać stanów.")
            return
        self.table.setRowCount(0)
        for it in self._items:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(it["item_id"])))
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(it.get("sku") or ""))
            self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(it.get("name") or ""))
            self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(it.get("uom") or ""))
            self.table.setItem(r, 4, QtWidgets.QTableWidgetItem(str(it.get("qty_available") or 0)))
        self.table.resizeColumnsToContents()

    def _row_to_qty(self):
        # wstaw identyfikatory do pola ilości (ułatwienie double-click)
        self.qty.setFocus()

    def get_selected(self) -> dict[str, Any] | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        r = rows[0].row()
        try:
            item = dict(self._items[r])
            qty = int(self.qty.text().strip() or "0")
            if qty <= 0:
                return None
            item["qty"] = qty
            return item
        except Exception:
            return None
