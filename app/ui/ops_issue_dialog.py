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


class OpsIssueDialog(QtWidgets.QDialog):
    """Issue tools to employee (operation kind ISSUE) — z wymuszeniem karty RFID."""

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

        # lokalny logger dla dialogu
        self.log = logging.getLogger(__name__)

        self.repo = repo or auth_repo
        self.reports_repo = reports_repo
        self.station_id = station_id
        self.operator_user_id = operator_user_id
        self.items_repo = ItemsRepo(reports_repo.engine) if reports_repo else None
        if self.repo is None:
            raise ValueError("Brak repo (AuthRepo) w IssueDialog")

        self.log.info(
            "IssueDialog init (station=%s, operator=%s)",
            station_id,
            operator_user_id,
        )

        self.setWindowTitle("Wydanie narzędzi")
        self.resize(700, 420)

        # --- employee selection
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
                self.log.exception("Nie udało się pobrać listy pracowników")

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
        btn_box.button(QtWidgets.QDialogButtonBox.Ok).setText("Wydaj")
        btn_box.button(QtWidgets.QDialogButtonBox.Cancel).setText("Anuluj")
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)

        # --- layout
        form = QtWidgets.QFormLayout()
        form.addRow("Pracownik:", self.employee_cb)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(form)
        lay.addLayout(sku_lay)
        lay.addWidget(self.table, 1)
        lay.addWidget(btn_box, 0, QtCore.Qt.AlignRight)

    # ===================== Helpery RFID =====================

    def _ask_rfid_uid(self) -> str | None:
        """
        Pokazuje modal 'Przyłóż kartę' i zwraca UID.
        Jeśli modal nie jest dostępny, stosuje prosty fallback (input UID).
        """
        try:
            from app.ui.rfid_modal import RFIDModal  # type: ignore
            return RFIDModal.ask(self)
        except Exception:
            uid, ok = QtWidgets.QInputDialog.getText(
                self,
                "Przyłóż kartę",
                "UID karty (tryb awaryjny):",
            )
            uid = (uid or "").strip()
            return uid if ok and uid else None

    def _employee_id_from_uid(self, uid: str) -> int | None:
        """
        Mapa UID karty -> employee_id przez repo (obsługujemy różne potencjalne API).
        """
        candidates = (
            "get_employee_id_by_card",
            "get_employee_by_card",
            "resolve_employee_by_uid",
        )
        for name in candidates:
            fn = getattr(self.repo, name, None)
            if callable(fn):
                try:
                    res = fn(uid)
                    if isinstance(res, dict):
                        val = res.get("id") or res.get("employee_id")
                        return int(val) if val is not None else None
                    if res is None:
                        return None
                    return int(res)
                except Exception:
                    self.log.exception("Błąd mapowania UID->employee_id (%s)", name)
        return None

    def _verify_employee_card(self, employee_id: int) -> bool:
        """
        Wymusza przyłożenie karty i weryfikuje, że karta należy do wskazanego pracownika.
        Zwraca True tylko gdy autoryzacja jest poprawna.
        """
        uid = self._ask_rfid_uid()
        if not uid:
            QtWidgets.QMessageBox.warning(
                self,
                "Brak autoryzacji",
                "Wydanie wymaga potwierdzenia kartą pracownika.",
            )
            return False

        mapped_emp_id = self._employee_id_from_uid(uid)
        if mapped_emp_id is None:
            QtWidgets.QMessageBox.warning(
                self,
                "Nie rozpoznano karty",
                "System nie rozpoznał tej karty. Wydanie wstrzymane.",
            )
            return False

        if int(mapped_emp_id) != int(employee_id):
            QtWidgets.QMessageBox.warning(
                self,
                "Błędna karta",
                "Karta nie należy do wskazanego pracownika. Wydanie wstrzymane.",
            )
            return False

        return True

    # ===================== Logika linii =====================

    def _add_line(self) -> None:
        sku = self.sku_edit.text().strip()
        if not sku:
            return
        try:
            item = self.items_repo.get_item_id_by_sku(sku) if self.items_repo else None
            if not item:
                raise ValueError("not found")
        except Exception:
            self.log.exception("Błąd operacji ISSUE (resolve SKU)")
            QtWidgets.QMessageBox.warning(self, "Błąd", f"Nie znaleziono SKU: {sku}")
            return

        # item może być intem, krotką/listą lub dict-em
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
            self.log.error("Brak item_id dla SKU %s", sku)
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

    # ===================== Finalizacja (RFID + zapis) =====================

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

            # scal identyczne pozycje
            merged: dict[int, int] = {}
            for item_id, qty in lines:
                merged[item_id] = merged.get(item_id, 0) + qty
            merged_lines = [(iid, q) for iid, q in merged.items()]

            # === KROK 1: KARTA RFID (wymagane) ===
            # Zgodnie z Założeniami: koszyk → karta → zatwierdzenie; bez karty nie wolno zatwierdzić.
            if not self._verify_employee_card(int(emp_id)):
                return

            # === KROK 2: POTWIERDZENIE UŻYTKOWNIKA ===
            if (
                QtWidgets.QMessageBox.question(
                    self,
                    "Potwierdź",
                    f"Czy wydać {len(merged_lines)} pozycji pracownikowi?",
                )
                != QtWidgets.QMessageBox.Yes
            ):
                return

            # === KROK 3: ZAPIS OPERACJI ===
            # UWAGA: flaga issued_without_return=True (zgodnie z wymaganiem oznaczania takich przypadków).
            self.repo.create_operation(
                kind="ISSUE",
                station=self.station_id,
                operator_user_id=self.operator_user_id,
                employee_user_id=int(emp_id),
                lines=merged_lines,
                issued_without_return=True,
                note="",
            )

            self.log.info(
                "Issued %d lines to employee %s (RFID verified)",
                len(merged_lines),
                emp_id,
            )
            QtWidgets.QMessageBox.information(self, "OK", "Wydanie zapisane")
            self.accept()
        except Exception as e:  # pragma: no cover - UI error path
            self.log.exception("Błąd operacji ISSUE (_on_accept)")
            QtWidgets.QMessageBox.critical(self, "Błąd", str(e))
