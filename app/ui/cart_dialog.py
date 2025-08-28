from __future__ import annotations

from typing import Any, List, Dict

from PySide6 import QtWidgets
from PySide6.QtCore import Qt

from sqlalchemy.engine import Engine

from app.appsvc.cart import SessionManager, CartRepository, StockRepository, CheckoutService, RfidService


class CartDialog(QtWidgets.QDialog):
    """
    PrzeglÄ…danie stanu magazynu z widoku `vw_stock_available` i modyfikacja koszyka (+/-).

    - Ĺaduje pozycje z widoku (JOIN z items dla nazwy/SKU/JM)
    - Dla kaĹĽdej pozycji wyĹ›wietla dostÄ™pnoĹ›Ä‡ oraz bieĹĽÄ…cÄ… iloĹ›Ä‡ w koszyku
    - Przyciski [+] i [â€“] aktualizujÄ… iloĹ›Ä‡ w `issue_session_lines`
    """

    def __init__(
        self,
        engine: Engine,
        *,
        station_id: str,
        operator_user_id: int,
        employee_id: int | None = None,
        repo: Any | None = None,
        reports_repo: Any | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Magazyn / Koszyk")
        self.resize(900, 560)

        self.engine = engine
        self.session_mgr = SessionManager(engine, station_id, int(operator_user_id))
        self.repo = repo
        self.reports_repo = reports_repo
        self.cart = CartRepository(engine)
        self.stock = StockRepository(engine)

        # zapewnij sesjÄ™ OPEN (zapisz employee_id jeĹ›li podano)
        self.session = self.session_mgr.ensure_open_session(employee_id)
        self.session_id = int(self.session["id"])

        # --- top: pracownik + search
        self.employee_cb = QtWidgets.QComboBox()
        if self.reports_repo:
            try:
                for emp in self.reports_repo.employees(q="", limit=200):
                    label = f"{emp.get('first_name','')} {emp.get('last_name','')}".strip()
                    login = emp.get("login")
                    if login:
                        label = f"{label} ({login})"
                    self.employee_cb.addItem(label, emp.get("id"))
            except Exception:
                pass
        if employee_id is not None:
            idx = self.employee_cb.findData(int(employee_id))
            if idx >= 0:
                self.employee_cb.setCurrentIndex(idx)

        self.q = QtWidgets.QLineEdit()
        self.q.setPlaceholderText("Szukaj po nazwie lub SKUâ€¦")
        self.btnFind = QtWidgets.QPushButton("Szukaj")

        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel("Pracownik:"))
        top.addWidget(self.employee_cb)
        top.addSpacing(12)
        top.addWidget(self.q, 1)
        top.addWidget(self.btnFind)

        self.table = QtWidgets.QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "SKU",
                "Nazwa",
                "JM",
                "Na stanie",
                "Zarezerw.",
                "DostÄ™pne",
                "W koszyku",
                "â€“",
                "+",
            ]
        )
        # Nadpisz nagłówki w neutralnym ASCII (na wypadek problemów z kodowaniem)
        self.table.setHorizontalHeaderLabels([
            "SKU", "Nazwa", "JM", "Na stanie", "Zarezerw.", "Dostepne", "W koszyku", "-", "+"
        ])
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)

        # --- bottom: koszyk + akcje
        self.cart_table = QtWidgets.QTableWidget(0, 4)
        self.cart_table.setHorizontalHeaderLabels(["SKU", "Nazwa", "JM", "IloĹ›Ä‡"])
        # Nagłówki koszyka w ASCII (bez ogonków)
        self.cart_table.setHorizontalHeaderLabels(["SKU", "Nazwa", "JM", "Ilosc"])
        self.cart_table.horizontalHeader().setStretchLastSection(True)
        self.cart_table.setSortingEnabled(True)

        btnRefreshCart = QtWidgets.QPushButton("OdĹ›wieĹĽ koszyk")
        btnCheckout = QtWidgets.QPushButton("Wydaj (RFID/PIN)")
        btnClose = QtWidgets.QPushButton("Zamknij")
        btnRefreshCart.clicked.connect(self._refresh_cart)
        btnCheckout.clicked.connect(self._checkout)
        btnClose.clicked.connect(self.accept)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table, 1)
        lay.addWidget(QtWidgets.QLabel("Koszyk:"))
        lay.addWidget(self.cart_table, 1)
        actions = QtWidgets.QHBoxLayout()
        actions.addWidget(btnRefreshCart)
        actions.addStretch(1)
        actions.addWidget(btnCheckout)
        actions.addWidget(btnClose)
        lay.addLayout(actions)

        self.btnFind.clicked.connect(self._reload)
        self.q.returnPressed.connect(self._reload)
        self.employee_cb.currentIndexChanged.connect(self._on_employee_changed)

        self._items: List[Dict] = []
        self._reload()
        self._refresh_cart()

    def _on_employee_changed(self) -> None:
        try:
            emp_id = self.employee_cb.currentData()
            self.session = self.session_mgr.ensure_open_session(int(emp_id) if emp_id is not None else None)
            self.session_id = int(self.session['id']) if self.session else self.session_id
        except Exception:
            pass


    # ---------- Dane ----------
    def _reload(self) -> None:
        try:
            self._items = self.stock.list_available(self.q.text().strip(), limit=300)
            reserved = self.cart.reserved_map(self.session_id)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "BĹ‚Ä…d", f"Nie udaĹ‚o siÄ™ pobraÄ‡ danych: {e}")
            return

        self.table.setRowCount(0)
        for it in self._items:
            r = self.table.rowCount()
            self.table.insertRow(r)

            # kolumny informacyjne
            sku = it.get("sku") or ""
            name = it.get("name") or (it.get("sku") or "")
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
            spin = QtWidgets.QSpinBox()
            spin.setRange(0, int(qty_av) if isinstance(qty_av, (int, float)) else 999999)
            spin.setValue(int(in_cart))
            spin.setProperty("item_id", int(it["item_id"]))
            spin.valueChanged.connect(self._spin_changed)
            self.table.setCellWidget(r, 6, spin)

            # przyciski â€“ i +
            btn_minus = QtWidgets.QPushButton("-")
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
        # znajdĹş wiersz z tym przyciskiem
        for r in range(self.table.rowCount()):
            for c in (7, 8):
                if self.table.cellWidget(r, c) is sender:
                    item = self.table.item(r, 0)
                    item_id = item.data(Qt.UserRole) if item else None
                    return int(item_id) if item_id is not None else None, r
        return None, None

    def _spin_changed(self, val: int) -> None:
        spin = self.sender()
        if not isinstance(spin, QtWidgets.QSpinBox):
            return
        item_id = spin.property("item_id")
        if item_id is None:
            return
        self.cart.set_qty(self.session_id, int(item_id), int(val))
        self._refresh_cart()

    def _inc(self) -> None:
        btn = self.sender()
        item_id, row = self._row_item(btn)
        if item_id is None or row is None:
            return
        new_qty = self.cart.add(self.session_id, int(item_id), +1)
        w = self.table.cellWidget(row, 6)
        if isinstance(w, QtWidgets.QSpinBox):
            w.setValue(int(new_qty))
        self._refresh_cart()

    def _dec(self) -> None:
        btn = self.sender()
        item_id, row = self._row_item(btn)
        if item_id is None or row is None:
            return
        new_qty = self.cart.add(self.session_id, int(item_id), -1)
        w = self.table.cellWidget(row, 6)
        if isinstance(w, QtWidgets.QSpinBox):
            w.setValue(int(new_qty))
        self._refresh_cart()

    # ---------- Koszyk ----------
    def _refresh_cart(self) -> None:
        try:
            lines = self.cart.list_lines(self.session_id)
        except Exception:
            lines = []
        self.cart_table.setRowCount(0)
        for ln in lines:
            r = self.cart_table.rowCount()
            self.cart_table.insertRow(r)
            self.cart_table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(ln.get("sku") or "")))
            display_name = ln.get("name") or ln.get("sku") or ""
            self.cart_table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(display_name)))
            self.cart_table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(ln.get("uom") or "")))
            self.cart_table.setItem(r, 3, QtWidgets.QTableWidgetItem(str(ln.get("qty_reserved") or 0)))

    # ---------- Finalizacja ----------
    def _checkout(self) -> None:
        emp_id = self.employee_cb.currentData()
        if emp_id is None:
            QtWidgets.QMessageBox.warning(self, "BĹ‚Ä…d", "Wybierz pracownika")
            return
        # zapisz employee_id do sesji jeĹ›li brak
        self.session = self.session_mgr.ensure_open_session(int(emp_id))
        self.session_id = int(self.session["id"])  # refresh id
        # RFID/PIN
        if not self.repo:
            QtWidgets.QMessageBox.warning(self, "Repozytorium", "Brak repo dla weryfikacji RFID/PIN.")
            return
        if not RfidService().verify_employee(self.repo, int(emp_id), self):
            return
        # Finalizuj
        res = CheckoutService(self.engine, self.repo).finalize_issue(self.session_id, int(emp_id))
        if res.get("status") == "success":
            msg = f"Wydanie zapisane (wierszy: {res.get('lines')})"
            if res.get("flagged"):
                msg += "\nDodano do WyjÄ…tki"
            QtWidgets.QMessageBox.information(self, "OK", msg)
            # rozpocznij nowÄ… pustÄ… sesjÄ™ dla dalszej pracy
            self.session = self.session_mgr.ensure_open_session(int(emp_id))
            self.session_id = int(self.session["id"]) if self.session else self.session_id
            self._reload()
            self._refresh_cart()
        elif res.get("status") == "empty":
            QtWidgets.QMessageBox.warning(self, "Koszyk pusty", "Brak pozycji do wydania.")
        else:
            QtWidgets.QMessageBox.warning(self, "BĹ‚Ä…d", f"Nie udaĹ‚o siÄ™ zapisaÄ‡: {res}")




