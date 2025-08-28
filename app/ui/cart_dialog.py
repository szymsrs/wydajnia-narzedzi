from __future__ import annotations

from typing import Any, List, Dict

from PySide6 import QtWidgets
from PySide6.QtCore import Qt

from sqlalchemy.engine import Engine

from app.appsvc.cart import SessionManager, CartRepository, StockRepository


class CartDialog(QtWidgets.QDialog):
    """
    Przeglądanie stanu magazynu z widoku `vw_stock_available` i modyfikacja koszyka (+/-).

    - Ładuje pozycje z widoku (JOIN z items dla nazwy/SKU/JM)
    - Dla każdej pozycji wyświetla dostępność oraz bieżącą ilość w koszyku
    - Przyciski [+] i [–] aktualizują ilość w `issue_session_lines`
    """

    def __init__(
        self,
        engine: Engine,
        *,
        station_id: str,
        operator_user_id: int,
        employee_id: int | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Magazyn / Koszyk")
        self.resize(900, 560)

        self.engine = engine
        self.session_mgr = SessionManager(engine, station_id, int(operator_user_id))
        self.cart = CartRepository(engine)
        self.stock = StockRepository(engine)

        # zapewnij sesję OPEN (zapisz employee_id jeśli podano)
        self.session = self.session_mgr.ensure_open_session(employee_id)
        self.session_id = int(self.session["id"])

        self.q = QtWidgets.QLineEdit()
        self.q.setPlaceholderText("Szukaj po nazwie lub SKU…")
        self.btnFind = QtWidgets.QPushButton("Szukaj")

        top = QtWidgets.QHBoxLayout()
        top.addWidget(self.q)
        top.addWidget(self.btnFind)

        self.table = QtWidgets.QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "SKU",
                "Nazwa",
                "JM",
                "Na stanie",
                "Zarezerw.",
                "Dostępne",
                "W koszyku",
                "–",
                "+",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        btnClose = QtWidgets.QPushButton("Zamknij")
        btnClose.clicked.connect(self.accept)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table, 1)
        lay.addWidget(btnClose, 0, Qt.AlignRight)

        self.btnFind.clicked.connect(self._reload)
        self.q.returnPressed.connect(self._reload)

        self._items: List[Dict] = []
        self._reload()

    # ---------- Dane ----------
    def _reload(self) -> None:
        try:
            self._items = self.stock.list_available(self.q.text().strip(), limit=300)
            reserved = self.cart.reserved_map(self.session_id)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Błąd", f"Nie udało się pobrać danych: {e}")
            return

        self.table.setRowCount(0)
        for it in self._items:
            r = self.table.rowCount()
            self.table.insertRow(r)

            # kolumny informacyjne
            sku = it.get("sku") or ""
            name = it.get("name") or ""
            uom = it.get("uom") or ""
            qty_on_hand = it.get("qty_on_hand") or 0
            qty_res = it.get("qty_reserved_open") or 0
            qty_av = it.get("qty_available") or 0
            in_cart = reserved.get(int(it["item_id"]), 0.0)

            c0 = QtWidgets.QTableWidgetItem(str(sku))
            c0.setData(Qt.UserRole, int(it["item_id"]))
            self.table.setItem(r, 0, c0)
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(name)))
            self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(uom)))
            self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(str(qty_on_hand)))
            self.table.setItem(r, 4, QtWidgets.QTableWidgetItem(str(qty_res)))
            self.table.setItem(r, 5, QtWidgets.QTableWidgetItem(str(qty_av)))
            self.table.setItem(r, 6, QtWidgets.QTableWidgetItem(str(in_cart)))

            # przyciski – i +
            btn_minus = QtWidgets.QPushButton("–")
            btn_plus = QtWidgets.QPushButton("+")
            btn_minus.clicked.connect(self._dec)
            btn_plus.clicked.connect(self._inc)
            self.table.setCellWidget(r, 7, btn_minus)
            self.table.setCellWidget(r, 8, btn_plus)

        self.table.resizeColumnsToContents()

    # ---------- Akcje koszyka ----------
    def _row_item(self, sender: Any) -> tuple[int | None, int | None]:
        if not isinstance(sender, QtWidgets.QPushButton):
            return None, None
        # znajdź wiersz z tym przyciskiem
        for r in range(self.table.rowCount()):
            for c in (7, 8):
                if self.table.cellWidget(r, c) is sender:
                    item = self.table.item(r, 0)
                    item_id = item.data(Qt.UserRole) if item else None
                    return int(item_id) if item_id is not None else None, r
        return None, None

    def _inc(self) -> None:
        btn = self.sender()
        item_id, row = self._row_item(btn)
        if item_id is None or row is None:
            return
        new_qty = self.cart.add(self.session_id, int(item_id), +1)
        self.table.setItem(row, 6, QtWidgets.QTableWidgetItem(str(new_qty)))

    def _dec(self) -> None:
        btn = self.sender()
        item_id, row = self._row_item(btn)
        if item_id is None or row is None:
            return
        new_qty = self.cart.add(self.session_id, int(item_id), -1)
        self.table.setItem(row, 6, QtWidgets.QTableWidgetItem(str(new_qty)))

