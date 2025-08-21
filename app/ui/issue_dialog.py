# app/ui/issue_dialog.py
from __future__ import annotations
from PySide6 import QtWidgets, QtCore
from decimal import Decimal
from typing import Any

class IssueDialog(QtWidgets.QDialog):
    def __init__(self, repo: Any, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("Wydanie do pracownika")

        self.empId = QtWidgets.QLineEdit()
        self.empName = QtWidgets.QLineEdit()
        self.itemId = QtWidgets.QLineEdit()
        self.qty = QtWidgets.QLineEdit()
        self.qty.setPlaceholderText("np. 1 lub 3.000")

        form = QtWidgets.QFormLayout()
        form.addRow("ID pracownika:", self.empId)
        form.addRow("Imię i nazwisko:", self.empName)
        form.addRow("ID pozycji (item_id):", self.itemId)
        form.addRow("Ilość:", self.qty)

        btnOk = QtWidgets.QPushButton("Wydaj")
        btnCancel = QtWidgets.QPushButton("Anuluj")
        btnOk.clicked.connect(self.on_ok)
        btnCancel.clicked.connect(self.reject)

        hl = QtWidgets.QHBoxLayout()
        hl.addStretch(1)
        hl.addWidget(btnOk)
        hl.addWidget(btnCancel)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(hl)

    def on_ok(self):
        try:
            emp_id = int(self.empId.text().strip())
            emp_name = self.empName.text().strip() or "Pracownik"
            item_id = int(self.itemId.text().strip())
            qty = Decimal(self.qty.text().replace(",", ".").strip() or "0")
            if qty <= 0:
                QtWidgets.QMessageBox.warning(self, "Błąd", "Ilość musi być > 0")
                return
            self.repo.issue_to_employee(employee_id=emp_id, employee_name=emp_name, item_id=item_id, qty=qty)
            QtWidgets.QMessageBox.information(self, "OK", "Wydanie zapisane.")
            self.accept()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Błąd", str(e))
