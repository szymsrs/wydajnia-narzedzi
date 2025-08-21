# app/ui/return_dialog.py
from __future__ import annotations
from PySide6 import QtWidgets, QtCore
from decimal import Decimal
from typing import Any

class ReturnDialog(QtWidgets.QDialog):
    def __init__(self, repo: Any, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("Zwrot do magazynu (odwzorowanie alokacji)")

        self.empId = QtWidgets.QLineEdit()
        self.empName = QtWidgets.QLineEdit()

        form = QtWidgets.QFormLayout()
        form.addRow("ID pracownika:", self.empId)
        form.addRow("Imię i nazwisko:", self.empName)

        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["lot_id", "item_id", "unit_cost", "qty_held", "qty_to_return"])
        self.table.horizontalHeader().setStretchLastSection(True)

        btnLoad = QtWidgets.QPushButton("Załaduj stan pracownika")
        btnLoad.clicked.connect(self.on_load)

        btnReturn = QtWidgets.QPushButton("Zwróć zaznaczone")
        btnReturn.clicked.connect(self.on_return)

        hl = QtWidgets.QHBoxLayout()
        hl.addWidget(btnLoad)
        hl.addStretch(1)
        hl.addWidget(btnReturn)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.table)
        layout.addLayout(hl)

    def on_load(self):
        self.table.setRowCount(0)
        try:
            emp_id = int(self.empId.text().strip())
            data = self.repo.list_employee_allocations(emp_id)
            for row in data:
                r = self.table.rowCount()
                self.table.insertRow(r)
                self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(row["lot_id"])))
                self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(row["item_id"])))
                self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(row["unit_cost_netto"])))
                self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(str(row["qty_held"])))
                spin = QtWidgets.QDoubleSpinBox()
                spin.setDecimals(3)
                spin.setRange(0.000, float(row["qty_held"]))
                spin.setSingleStep(1.000)
                self.table.setCellWidget(r, 4, spin)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Błąd", str(e))

    def on_return(self):
        try:
            emp_id = int(self.empId.text().strip())
            emp_name = self.empName.text().strip() or "Pracownik"
            allocations = []
            for r in range(self.table.rowCount()):
                lot_id = int(self.table.item(r, 0).text())
                qty_held = Decimal(str(self.table.item(r, 3).text()))
                spin: QtWidgets.QDoubleSpinBox = self.table.cellWidget(r, 4)  # type: ignore
                qty_ret = Decimal(str(spin.value()))
                if qty_ret > 0:
                    if qty_ret > qty_held:
                        QtWidgets.QMessageBox.warning(self, "Błąd", f"Zwrot > stan dla LOT {lot_id}")
                        return
                    allocations.append({"lot_id": lot_id, "qty": qty_ret})
            if not allocations:
                QtWidgets.QMessageBox.information(self, "Info", "Nic nie zaznaczono do zwrotu.")
                return
            self.repo.return_from_employee(employee_id=emp_id, employee_name=emp_name, allocations=allocations)
            QtWidgets.QMessageBox.information(self, "OK", "Zwrot zapisany.")
            self.accept()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Błąd", str(e))
