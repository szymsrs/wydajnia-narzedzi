# app/ui/movements_tab.py
from __future__ import annotations
from PySide6 import QtWidgets
from app.services.movements import MovementsService


class MovementsTab(QtWidgets.QWidget):
    def __init__(self, service: MovementsService, parent=None):
        super().__init__(parent)
        self.service = service

        self.limit = QtWidgets.QSpinBox()
        self.limit.setRange(1, 1000)
        self.limit.setValue(200)

        btnLoad = QtWidgets.QPushButton("Odśwież")
        btnLoad.clicked.connect(self.on_load)

        hl = QtWidgets.QHBoxLayout()
        hl.addWidget(QtWidgets.QLabel("Limit:"))
        hl.addWidget(self.limit)
        hl.addStretch(1)
        hl.addWidget(btnLoad)

        self.table = QtWidgets.QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "id", "ts", "movement_type", "item_id", "qty", "from_location", "to_location"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(hl)
        layout.addWidget(self.table)

    def on_load(self):
        self.table.setRowCount(0)
        data = self.service.list_recent(int(self.limit.value()))
        for row in data:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(row.get("id", ""))))
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(row.get("ts", ""))))
            self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(row.get("movement_type", ""))))
            self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(str(row.get("item_id", ""))))
            self.table.setItem(r, 4, QtWidgets.QTableWidgetItem(str(row.get("qty", ""))))
            self.table.setItem(r, 5, QtWidgets.QTableWidgetItem(str(row.get("from_location_id", ""))))
            self.table.setItem(r, 6, QtWidgets.QTableWidgetItem(str(row.get("to_location_id", ""))))
