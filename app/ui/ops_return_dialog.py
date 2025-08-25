# app/ui/ops_return_dialog.py
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
import uuid

from PySide6 import QtWidgets
from PySide6.QtCore import Qt


class OpsReturnDialog(QtWidgets.QDialog):
    def __init__(
        self,
        repo: Any | None = None,
        auth_repo: Any | None = None,
        reports_repo: Any | None = None,
        station_id: str = "",
        operator_user_id: int = 0,
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)

        # lokalny logger dla dialogu
        self.log = logging.getLogger(__name__)

        self.repo = repo or auth_repo
        self.reports_repo = reports_repo
        self.station_id = station_id
        self.operator_user_id = operator_user_id
        if self.repo is None:
            raise ValueError("Brak repo (AuthRepo) w ReturnDialog")

        self.log.info(
            "ReturnDialog init (station=%s, operator=%s)",
            station_id,
            operator_user_id,
        )

        self.setWindowTitle("Zwrot")

        self.station = QtWidgets.QLineEdit(station_id)
        self.operator = QtWidgets.QLineEdit(
            str(operator_user_id) if operator_user_id else ""
        )
        self.employee = QtWidgets.QLineEdit()
        self.note = QtWidgets.QLineEdit()
        self.sku = QtWidgets.QLineEdit()
        self.qty = QtWidgets.QLineEdit()
        self.qty.setPlaceholderText("np. 1 lub 3")

        form = QtWidgets.QFormLayout()
        form.addRow("Stanowisko:", self.station)
        form.addRow("ID operatora:", self.operator)
        form.addRow("ID pracownika:", self.employee)
        form.addRow("Notatka:", self.note)

        hl_item = QtWidgets.QHBoxLayout()
        hl_item.addWidget(QtWidgets.QLabel("SKU:"))
        hl_item.addWidget(self.sku)
        hl_item.addWidget(QtWidgets.QLabel("Ilość:"))
        hl_item.addWidget(self.qty)
        btnAdd = QtWidgets.QPushButton("Dodaj")
        hl_item.addWidget(btnAdd)

        self.table = QtWidgets.QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["SKU", "Ilość"])
        self.table.horizontalHeader().setStretchLastSection(True)

        btnRemove = QtWidgets.QPushButton("Usuń zaznaczone")
        btnOk = QtWidgets.QPushButton("Zwróć")
        btnCancel = QtWidgets.QPushButton("Anuluj")

        btnAdd.clicked.connect(self.on_add)
        btnRemove.clicked.connect(self.on_remove)
        btnOk.clicked.connect(self.on_ok)
        btnCancel.clicked.connect(self.reject)

        hl_actions = QtWidgets.QHBoxLayout()
        hl_actions.addWidget(btnRemove)
        hl_actions.addStretch(1)
        hl_actions.addWidget(btnOk)
        hl_actions.addWidget(btnCancel)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(hl_item)
        layout.addWidget(self.table)
        layout.addLayout(hl_actions)

    # ---------- Helpery RFID i rozwiązywania ID ----------

    def _ask_rfid_uid(self) -> str | None:
        """
        Pokazuje modal 'Przyłóż kartę' i zwraca UID.
        Jeśli modal nie jest dostępny, stosuje prosty fallback (input UID).
        """
        try:
            # Jeśli masz w projekcie app.ui.rfid_modal.RFIDModal z metodą ask(self)->str|None
            from app.ui.rfid_modal import RFIDModal  # type: ignore

            return RFIDModal.ask(self)
        except Exception:
            # Fallback – ręczne wpisanie UID (np. w trybie deweloperskim / bez czytnika)
            uid, ok = QtWidgets.QInputDialog.getText(
                self,
                "Przyłóż kartę",
                "UID karty (tryb awaryjny):",
            )
            uid = (uid or "").strip()
            return uid if ok and uid else None

    def _employee_id_from_uid(self, uid: str) -> int | None:
        """
        Próbujemy zmapować UID karty -> employee_id, korzystając z dostępnych metod repo.
        Obsługujemy różne możliwe nazwy metod, aby nie wiązać się sztywno z jedną implementacją.
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
                    # możliwe zwroty: int, None, dict z 'id' / 'employee_id'
                    if isinstance(res, dict):
                        val = res.get("id") or res.get("employee_id")
                        return int(val) if val is not None else None
                    if res is None:
                        return None
                    return int(res)
                except Exception:
                    self.log.exception("Błąd mapowania UID->employee_id (%s)", name)
                    # próbujemy następnej metody
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
                "Zwrot wymaga potwierdzenia kartą pracownika.",
            )
            return False

        mapped_emp_id = self._employee_id_from_uid(uid)
        if mapped_emp_id is None:
            QtWidgets.QMessageBox.warning(
                self,
                "Nie rozpoznano karty",
                "System nie rozpoznał tej karty. Zwrot wstrzymany.",
            )
            return False

        if int(mapped_emp_id) != int(employee_id):
            QtWidgets.QMessageBox.warning(
                self,
                "Błędna karta",
                "Karta nie należy do wskazanego pracownika. Zwrot wstrzymany.",
            )
            return False

        return True

    # ---------- Logika dialogu ----------

    def _resolve_item_id(self, sku: str) -> int | None:
        item_id = None
        if hasattr(self.repo, "get_item_id_by_sku"):
            try:
                item_id = self.repo.get_item_id_by_sku(sku)
            except Exception:
                self.log.exception("Błąd get_item_id_by_sku(%s)", sku)
                item_id = None
        if not item_id:
            try:
                item_id = int(sku)
            except Exception:
                item_id = None
        return item_id

    def on_add(self) -> None:
        try:
            sku = self.sku.text().strip()
            qty = Decimal(self.qty.text().replace(",", ".").strip() or "0")
            if not sku or qty <= 0:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Błąd",
                    "Podaj SKU i ilość > 0",
                )
                return
            item_id = self._resolve_item_id(sku)
            if not item_id:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Błąd",
                    f"Nie znaleziono SKU {sku}",
                )
                return
            r = self.table.rowCount()
            self.table.insertRow(r)
            sku_item = QtWidgets.QTableWidgetItem(sku)
            sku_item.setData(Qt.UserRole, int(item_id))
            self.table.setItem(r, 0, sku_item)
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(int(qty))))
            self.sku.clear()
            self.qty.clear()
        except Exception:
            self.log.exception("Błąd operacji RETURN (on_add)")
            QtWidgets.QMessageBox.critical(
                self,
                "Błąd",
                "Nie udało się dodać pozycji",
            )

    def on_remove(self) -> None:
        rows = {i.row() for i in self.table.selectedIndexes()}
        for r in sorted(rows, reverse=True):
            self.table.removeRow(r)

    def on_ok(self) -> None:
        try:
            station = self.station.text().strip()
            operator_id_txt = self.operator.text().strip()
            employee_id_txt = self.employee.text().strip()

            if not station:
                QtWidgets.QMessageBox.warning(
                    self, "Błąd", "Brak identyfikatora stanowiska."
                )
                return

            try:
                operator_id = int(operator_id_txt)
            except Exception:
                QtWidgets.QMessageBox.warning(
                    self, "Błąd", "Nieprawidłowy ID operatora."
                )
                return

            try:
                employee_id = int(employee_id_txt)
            except Exception:
                QtWidgets.QMessageBox.warning(
                    self, "Błąd", "Nieprawidłowy ID pracownika."
                )
                return

            note = self.note.text().strip()

            lines: list[tuple[int, int]] = []
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 0)
                if not item:
                    continue
                item_id = item.data(Qt.UserRole)
                qty_txt = self.table.item(r, 1).text().strip()
                qty = int(Decimal(qty_txt)) if qty_txt else 0
                if item_id and qty > 0:
                    lines.append((int(item_id), qty))

            if not lines:
                QtWidgets.QMessageBox.information(
                    self, "Info", "Brak pozycji do zwrotu."
                )
                return

            # === KROK 1: KARTA RFID (wymagane) ===
            # 'Założenia': koszyk → karta → zatwierdzenie; brak możliwości finalizacji bez karty.
            if not self._verify_employee_card(employee_id):
                return

            # === KROK 2: POTWIERDZENIE UŻYTKOWNIKA ===
            if (
                QtWidgets.QMessageBox.question(
                    self,
                    "Potwierdź",
                    "Czy zapisać zwrot?",
                )
                != QtWidgets.QMessageBox.Yes
            ):
                return

            # === KROK 3: ZAPIS OPERACJI ===
            for item_id, qty in lines:
                self.repo.return_tool(
                    employee_id=employee_id,
                    item_id=item_id,
                    qty=qty,
                    operation_uuid=str(uuid.uuid4()),
                )

            QtWidgets.QMessageBox.information(self, "OK", "Zwrot zapisany.")
            self.log.info("Zwrot: employee=%s lines=%s", employee_id, len(lines))
            self.accept()
        except Exception:
            self.log.exception("Błąd operacji RETURN (on_ok)")
            QtWidgets.QMessageBox.critical(
                self,
                "Błąd",
                "Nie udało się zapisać zwrotu",
            )
