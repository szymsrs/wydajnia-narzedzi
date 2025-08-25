from __future__ import annotations
from PySide6.QtCore import QAbstractTableModel, Qt, QModelIndex

class SimpleTableModel(QAbstractTableModel):
    def __init__(self, rows: list[dict] | None = None):
        super().__init__()
        self._rows = rows or []
        self._cols = list(self._rows[0].keys()) if self._rows else []

    def set_rows(self, rows: list[dict]):
        self.beginResetModel()
        self._rows = rows or []
        self._cols = list(self._rows[0].keys()) if self._rows else []
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()): return len(self._rows)
    def columnCount(self, parent=QModelIndex()): return len(self._cols)
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole: return None
        return self._cols[section] if orientation == Qt.Horizontal else section + 1
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.ToolTipRole): return None
        row = self._rows[index.row()]
        return row.get(self._cols[index.column()], "")
