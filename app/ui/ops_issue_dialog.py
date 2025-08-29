from __future__ import annotations

import logging
from typing import Any, Dict, List

from PySide6 import QtWidgets
from PySide6.QtCore import Qt

from app.appsvc.cart import (
    CartRepository,
    CheckoutService,
    RfidService,
    SessionManager,
    StockRepository,
)
from app.ui.stock_picker import StockPickerDialog


class OpsIssueDialog(QtWidgets.QDialog):
    """Issue tools to employee (operation kind ISSUE) with cart support."""

    def __init__(
        self,
        repo: Any | None = None,
        auth_repo: Any | None = None,
        reports_repo: Any | None = None,
        station_id: str = "",
        operator_user_id: int = 0,
        page_size: int | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.log = logging.getLogger(__name__)
        self.repo = repo or auth_repo
        self.reports_repo = reports_repo
        self.station_id = station_id
        self.operator_user_id = operator_user_id
        if self.repo is None:
            raise ValueError("Brak repo (AuthRepo) w IssueDialog")

        self.engine = self.repo.engine
        self.session_mgr = SessionManager(
            self.engine, station_id, int(operator_user_id)
        )
        self.cart = CartRepository(self.engine)
        self.stock = StockRepository(self.engine)
        self.session = self.session_mgr.ensure_open_session(None)
        self.session_id = int(self.session["id"])

        self.setWindowTitle("Wydanie narzędzi")
        self.resize(900, 560)

        # --- employee + search ---
        self.employee_cb = QtWidgets.QComboBox()
        if self.reports_repo:
            try:
                for emp in self.reports_repo.employees(q="", limit=200):
                    first = emp.get("first_name", "")
                    last = emp.get("last_name", "")
                    label = f"{first} {last}".strip()
                    login = emp.get("login")
                    if login:
                        label = f"{label} ({login})"
                    self.employee_cb.addItem(label, emp.get("id"))
            except Exception:
                self.log.exception("Nie udało się pobrać listy pracowników")

        self.q = QtWidgets.QLineEdit()
        self.q.setPlaceholderText("Szukaj po nazwie lub SKU…")
        self.btnFind = QtWidgets.QPushButton("Szukaj")
        self.btnPickStock = QtWidgets.QPushButton("Dodaj ze stanu")
        self.btnPickStock.clicked.connect(self.on_pick_from_stock)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel("Pracownik:"))
        top.addWidget(self.employee_cb)
        top.addSpacing(12)
        top.addWidget(self.q, 1)
        top.addWidget(self.btnFind)
        top.addWidget(self.btnPick)

        # --- stock table ---
        self.table = QtWidgets.QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            [
                "SKU",
                "Nazwa",
                "JM",
                "Na stanie",
                "Zarezerw.",
                "Dostępne",
                "W koszyku",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)
        try:
            self.table.verticalHeader().setVisible(False)
        except Exception:
            pass

        # pagination controls
        self.page_size = page_size
        self.limit = page_size
        self.btnLoadMore = QtWidgets.QPushButton("Załaduj więcej")
        self.btnLoadMore.clicked.connect(self._load_more)
        if self.page_size is None:
            self.btnLoadMore.hide()

        # --- cart table ---
        self.cart_table = QtWidgets.QTableWidget(0, 4)
        self.cart_table.setHorizontalHeaderLabels(
            [
                "SKU",
                "Nazwa",
                "JM",
                "Ilość",
            ]
        )
        self.cart_table.horizontalHeader().setStretchLastSection(True)
        try:
            self.cart_table.verticalHeader().setVisible(False)
        except Exception:
            pass
        self.cart_table.setSortingEnabled(True)

        # --- global actions ---
        self.btnAddSel = QtWidgets.QPushButton("Dodaj do koszyka")
        self.btnRemoveSel = QtWidgets.QPushButton("Usuń z koszyka")
        self.btnAddSel.clicked.connect(self._add_selected)
        self.btnRemoveSel.clicked.connect(self._remove_selected)
        mid_actions = QtWidgets.QHBoxLayout()
        mid_actions.addWidget(self.btnAddSel)
        mid_actions.addWidget(self.btnRemoveSel)
        mid_actions.addStretch(1)

        # --- final actions ---
        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btn_box.button(QtWidgets.QDialogButtonBox.Ok).setText("Wydaj")
        btn_box.button(QtWidgets.QDialogButtonBox.Cancel).setText("Anuluj")
        btn_box.accepted.connect(self._checkout_safe)
        btn_box.rejected.connect(self.reject)

        # layout root
        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table, 1)
        lay.addWidget(self.btnLoadMore)
        lay.addLayout(mid_actions)
        lay.addWidget(QtWidgets.QLabel("Koszyk:"))
        lay.addWidget(self.cart_table, 1)
        lay.addWidget(btn_box, 0, Qt.AlignRight)

        self.btnFind.clicked.connect(self._reload_search)
        self.q.returnPressed.connect(self._reload_search)
        self.employee_cb.currentIndexChanged.connect(self._on_employee_changed)

        self._items: List[Dict] = []
        self._reload_search()
        self._refresh_cart()

    # ---------- helper selection ----------
    def _selected_rows(self) -> List[int]:
        try:
            sel = self.table.selectionModel().selectedRows()
            return [i.row() for i in sel] if sel else []
        except Exception:
            return []

    def _on_employee_changed(self) -> None:
        try:
            emp_id = self.employee_cb.currentData()
            self.session = self.session_mgr.ensure_open_session(
                int(emp_id) if emp_id is not None else None
            )
            self.session_id = int(self.session["id"])
        except Exception:
            pass

    # ---------- data loading ----------
    def _reload_search(self) -> None:
        self.limit = self.page_size
        self._reload()

    def _load_more(self) -> None:
        if self.page_size is None:
            return
        self.limit = (self.limit or 0) + self.page_size
        self._reload()

    def _reload(self) -> None:
        try:
            lim = self.limit if self.limit is not None else 1_000_000
            self._items = self.stock.list_available(self.q.text().strip(), limit=lim)
            reserved = self.cart.reserved_map(self.session_id)
        except Exception as e:
            self.log.exception("OpsIssueDialog._reload: błąd pobierania listy")
            QtWidgets.QMessageBox.critical(
                self, "Błąd", f"Nie udało się pobrać danych: {e}"
            )
            return

        self.table.setRowCount(0)
        for it in self._items:
            r = self.table.rowCount()
            self.table.insertRow(r)

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

        self.table.resizeColumnsToContents()
        try:
            if self.limit is not None:
                self.btnLoadMore.setEnabled(len(self._items) >= self.limit)
            else:
                self.btnLoadMore.setEnabled(False)
        except Exception:
            pass

    # ---------- cart actions ----------
    def _spin_changed(self, val: int) -> None:
        spin = self.sender()
        if not isinstance(spin, QtWidgets.QSpinBox):
            return
        item_id = spin.property("item_id")
        if item_id is None:
            return
        self.cart.set_qty(self.session_id, int(item_id), int(val))
        self._refresh_cart()

    def _add_selected(self) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        for row in rows:
            it = self.table.item(row, 0)
            item_id = it.data(Qt.UserRole) if it else None
            if item_id is None:
                continue
            new_qty = self.cart.add(self.session_id, int(item_id), +1)
            w = self.table.cellWidget(row, 6)
            if isinstance(w, QtWidgets.QSpinBox):
                w.setValue(int(new_qty))
        self._refresh_cart()

    def _remove_selected(self) -> None:
        rows = self._selected_rows()
        if rows:
            for row in rows:
                it = self.table.item(row, 0)
                item_id = it.data(Qt.UserRole) if it else None
                if item_id is None:
                    continue
                self.cart.set_qty(self.session_id, int(item_id), 0)
                w = self.table.cellWidget(row, 6)
                if isinstance(w, QtWidgets.QSpinBox):
                    w.setValue(0)
            self._refresh_cart()
            return
        try:
            sel = self.cart_table.selectionModel().selectedRows()
        except Exception:
            sel = []
        for idx in (sel or []):
            r = idx.row()
            itm = self.cart_table.item(r, 0)
            item_id = itm.data(Qt.UserRole) if itm else None
            if item_id is None:
                continue
            self.cart.set_qty(self.session_id, int(item_id), 0)
        self._refresh_cart()

    # ---------- cart table ----------
    def _refresh_cart(self) -> None:
        try:
            lines = self.cart.list_lines(self.session_id)
        except Exception:
            self.log.exception("OpsIssueDialog._refresh_cart: błąd listowania linii")
            lines = []
        self.cart_table.setRowCount(0)
        for ln in lines:
            r = self.cart_table.rowCount()
            self.cart_table.insertRow(r)
            sku_item = QtWidgets.QTableWidgetItem(str(ln.get("sku") or ""))
            try:
                sku_item.setData(Qt.UserRole, int(ln.get("item_id")))
            except Exception:
                pass
            self.cart_table.setItem(r, 0, sku_item)
            display_name = ln.get("name") or ln.get("sku") or ""
            self.cart_table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(display_name)))
            self.cart_table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(ln.get("uom") or "")))
            self.cart_table.setItem(
                r, 3, QtWidgets.QTableWidgetItem(str(ln.get("qty_reserved") or 0))
            )

    # ---------- finalize ----------
    def _checkout_safe(self) -> None:
        try:
            self._checkout()
        except Exception as e:
            self.log.exception("OpsIssueDialog._checkout_safe: nieobsłużony błąd")
            QtWidgets.QMessageBox.critical(self, "Błąd", str(e))
            try:
                self._reload()
                self._refresh_cart()
            except Exception:
                pass

    def _checkout(self) -> None:
        emp_id = self.employee_cb.currentData()
        if emp_id is None:
            QtWidgets.QMessageBox.warning(self, "Błąd", "Wybierz pracownika")
            return
        self.session = self.session_mgr.ensure_open_session(int(emp_id))
        self.session_id = int(self.session["id"])
        if not RfidService().verify_employee(self.repo, int(emp_id), self):
            return
        res = CheckoutService(self.engine, self.repo).finalize_issue(
            self.session_id, int(emp_id)
        )
        if res.get("status") == "success":
            msg = f"Wydanie zapisane (wierszy: {res.get('lines')})"
            if res.get("flagged"):
                msg += "\nDodano do Wyjątki"
            QtWidgets.QMessageBox.information(self, "OK", msg)
            self.accept()
        elif res.get("status") == "empty":
            QtWidgets.QMessageBox.warning(
                self, "Koszyk pusty", "Brak pozycji do wydania."
            )
        else:
            QtWidgets.QMessageBox.warning(
                self, "Błąd", f"Nie udało się zapisać: {res}"
            )

    # ---------- stock picker ----------
    def on_pick_from_stock(self) -> None:
        dlg = StockPickerDialog(self.repo, self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            sel = dlg.get_selected()
            if not sel:
                QtWidgets.QMessageBox.information(
                    self, "Info", "Nie wybrano pozycji lub ilości."
                )
                return
            item_id = sel.get("item_id")
            qty = int(sel.get("qty") or 0)
            if not item_id or qty <= 0:
                QtWidgets.QMessageBox.information(
                    self, "Info", "Nie wybrano pozycji lub ilości."
                )
                return
            self.cart.add(self.session_id, int(item_id), int(qty))
            self._reload()
            self._refresh_cart()
