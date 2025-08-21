# app/ui/holdings_tab.py
from __future__ import annotations
from PySide6 import QtWidgets
from app.dal.repo_mysql import RepoMySQL

class HoldingsTab(QtWidgets.QWidget):
    def __init__(self, repo: RepoMySQL, parent=None):
        super().__init__(parent)
        self.repo = repo

        self.empLoc = QtWidgets.QLineEdit()
        self.empLoc.setPlaceholderText("opcjonalnie: ID lokacji pracownika")

        btnLoad = QtWidgets.QPushButton("Odśwież")
        btnLoad.clicked.connect(self.on_load)

        hl = QtWidgets.QHBoxLayout()
        hl.addWidget(QtWidgets.QLabel("Emp loc id:"))
        hl.addWidget(self.empLoc)
        hl.addStretch(1)
        hl.addWidget(btnLoad)

        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["emp_loc", "item_id", "qty_now", "value_now"])
        self.table.horizontalHeader().setStretchLastSection(True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(hl)
        layout.addWidget(self.table)

    def on_load(self):
        self.table.setRowCount(0)
        loc_id = self.empLoc.text().strip()
        loc = int(loc_id) if loc_id else None
        data = self.repo.list_v_employee_holdings(loc)
        for row in data:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(row["emp_loc"])))
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(row["item_id"])))
            self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(row["qty_now"])))
            self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(str(row["value_now"])))
