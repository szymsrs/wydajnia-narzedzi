# app/ui/ops_issue_dialog.py
from __future__ import annotations

import logging
from typing import Any

from PySide6 import QtWidgets, QtCore, QtGui

try:  # pragma: no cover - fallback if repo module is missing
    from app.repo.items_repo import ItemsRepo
except Exception:  # pragma: no cover - simple stub for tests
    class ItemsRepo:  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def get_item_id_by_sku(self, sku: str):  # type: ignore
            raise NotImplementedError

log = logging.getLogger(__name__)


class OpsIssueDialog(QtWidgets.QDialog):
    """Issue tools to employee without return (operation kind ISSUE)."""

    def __init__(
        self,
        repo: Any | None = None,
        auth_repo: Any | None = None,
        reports_repo: Any | None = None,
        station_id: str = "",
        operator_user_id: int = 0,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repo = repo or auth_repo
        self.reports_repo = reports_repo
        self.station_id = station_id
        self.operator_user_id = operator_user_id
        self.items_repo = ItemsRepo(reports_repo.engine) if reports_repo else None
        if self.repo is None:
            raise ValueError("Brak repo (AuthRepo) w IssueDialog")

        self.setWindowTitle("Wydanie narzędzi")
        self.resize(700, 400)

        # --- employee selection
        self.employee_cb = QtWidgets.QComboBox()
        for emp in self.reports_repo.employees(q="", limit=200):
            label = f"{emp.get('first_name','')} {emp.get('last_name','')}".strip()
            login = emp.get("login")
            if login:
                label = f"{label} ({login})"
            self.employee_cb.addItem(label, emp.get("id"))

        # --- SKU entry
        self.sku_edit = QtWidgets.QLineEdit()
        self.sku_edit.setPlaceholderText("SKU")
        self.add_btn = QtWidgets.QPushButton("Dodaj")
        self.add_btn.clicked.connect(self._add_line)
        self.sku_edit.returnPressed.connect(self._add_line)
        sku_lay = QtWidgets.QHBoxLayout()
        sku_lay.addWidget(self.sku_edit, 1)
        sku_lay.addWidget(self.add_btn)

        # --- table of lines
        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["SKU", "Nazwa", "Jm", "Ilość", ""])
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)

        # --- dialog buttons
        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)

        form = QtWidgets.QFormLayout()
        form.addRow("Pracownik:", self.employee_cb)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(form)
        lay.addLayout(sku_lay)
        lay.addWidget(self.table, 1)
        lay.addWidget(btn_box, 0, QtCore.Qt.AlignRight)

    # ------------------------------------------------------------------
    def _add_line(self) -> None:
        sku = self.sku_edit.text().strip()
        if not sku:
            return
        try:
            item = self.items_repo.get_item_id_by_sku(sku)
            if not item:
                raise ValueError("not found")
        except Exception:
            log.exception("Failed to resolve SKU %s", sku)
            QtWidgets.QMessageBox.warning(self, "Błąd", f"Nie znaleziono SKU: {sku}")
            return

        # item may be int or tuple/list/dict
        item_id = None
        name = ""
        uom = ""
        if isinstance(item, dict):
            item_id = item.get("id") or item.get("item_id")
            name = item.get("name") or item.get("item_name") or ""
            uom = item.get("uom") or item.get("unit") or ""
        elif isinstance(item, (list, tuple)):
            if len(item) >= 1:
                item_id = item[0]
            if len(item) >= 2:
                name = item[1]
            if len(item) >= 3:
                uom = item[2]
        else:
            item_id = int(item)
        if item_id is None:
            log.exception("ItemsRepo.get_item_id_by_sku returned invalid result for %s", sku)
            QtWidgets.QMessageBox.warning(self, "Błąd", f"Nie znaleziono SKU: {sku}")
            return

        r = self.table.rowCount()
        self.table.insertRow(r)
        sku_item = QtWidgets.QTableWidgetItem(sku)
        sku_item.setData(QtCore.Qt.UserRole, int(item_id))
        self.table.setItem(r, 0, sku_item)
        self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(name))
        self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(uom))

        qty_edit = QtWidgets.QLineEdit("1")
        qty_edit.setValidator(QtGui.QIntValidator(1, 99999, qty_edit))
        self.table.setCellWidget(r, 3, qty_edit)

        btn_rm = QtWidgets.QPushButton("Usuń")
        btn_rm.clicked.connect(self._remove_row)
        self.table.setCellWidget(r, 4, btn_rm)

        self.sku_edit.clear()
        self.sku_edit.setFocus()

    def _remove_row(self) -> None:
        btn = self.sender()
        if not isinstance(btn, QtWidgets.QPushButton):
            return
        for r in range(self.table.rowCount()):
            if self.table.cellWidget(r, 4) is btn:
                self.table.removeRow(r)
                break

    # ------------------------------------------------------------------
    def _on_accept(self) -> None:
        try:
            emp_id = self.employee_cb.currentData()
            if emp_id is None:
                QtWidgets.QMessageBox.warning(self, "Błąd", "Wybierz pracownika")
                return

            lines: list[tuple[int, int]] = []
            for r in range(self.table.rowCount()):
                sku_item = self.table.item(r, 0)
                item_id = sku_item.data(QtCore.Qt.UserRole) if sku_item else None
                qty_edit = self.table.cellWidget(r, 3)
                qty = 0
                if isinstance(qty_edit, QtWidgets.QLineEdit):
                    try:
                        qty = int(qty_edit.text())
                    except Exception:
                        qty = 0
                if not item_id or qty <= 0:
                    QtWidgets.QMessageBox.warning(
                        self, "Błąd", "Nieprawidłowa ilość w wierszu"
                    )
                    return
                lines.append((int(item_id), int(qty)))

            if not lines:
                QtWidgets.QMessageBox.warning(
                    self, "Błąd", "Dodaj przynajmniej jedną pozycję"
                )
                return

            merged: dict[int, int] = {}
            for item_id, qty in lines:
                merged[item_id] = merged.get(item_id, 0) + qty
            merged_lines = [(iid, q) for iid, q in merged.items()]

            self.repo.create_operation(
                kind="ISSUE",
                station=self.station_id,
                operator_user_id=self.operator_user_id,
                employee_user_id=int(emp_id),
                lines=merged_lines,
                issued_without_return=True,
                note="",
            )
            log.info(
                "Issued %d lines to employee %s without return", len(merged_lines), emp_id
            )
            QtWidgets.QMessageBox.information(self, "OK", "Wydanie zapisane")
            self.accept()
        except Exception as e:  # pragma: no cover - UI error path
            log.exception("OpsIssueDialog accept failed")
            QtWidgets.QMessageBox.critical(self, "Błąd", str(e))