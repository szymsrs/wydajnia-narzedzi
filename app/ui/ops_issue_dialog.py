# app/ui/ops_issue_dialog.py
from __future__ import annotations
from app.ui.stock_picker import StockPickerDialog

from app.appsvc.cart import SessionManager, CartRepository, CheckoutService, RfidService
import uuid
import logging
from typing import Any

from PySide6 import QtWidgets, QtCore, QtGui


try:  # pragma: no cover - fallback if repo module is missing
    from app.repo.items_repo import ItemsRepo
except Exception:  # pragma: no cover - simple stub for tests
    class ItemsRepo:  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def get_item_by_sku(self, sku: str):  # type: ignore
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

        # lokalny logger dla dialogu
        self.log = logging.getLogger(__name__)
        self.log.warning("OPS_ISSUE_DIALOG LOADED %s", __file__)

        super().__init__(parent)
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

        # --- SKU entry + przycisk "Dodaj ze stanu"
        self.sku_edit = QtWidgets.QLineEdit()
        self.sku_edit.setPlaceholderText("SKU")
        self.add_btn = QtWidgets.QPushButton("Dodaj")
        self.add_btn.clicked.connect(self._add_line)
        self.sku_edit.returnPressed.connect(self._add_line)

        self.btnPick = QtWidgets.QPushButton("Dodaj ze stanu")
        self.btnPick.clicked.connect(self.on_pick_from_stock)

        sku_lay = QtWidgets.QHBoxLayout()
        sku_lay.addWidget(self.sku_edit, 1)
        sku_lay.addWidget(self.add_btn)
        sku_lay.addWidget(self.btnPick)

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
        btn_box.accepted.connect(self._on_accept_cart)
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



    # ===================== „Dodaj ze stanu” =====================

    def on_pick_from_stock(self):
        dlg = StockPickerDialog(self.repo, self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            sel = dlg.get_selected()
            if not sel:
                QtWidgets.QMessageBox.information(self, "Info", "Nie wybrano pozycji lub ilości.")
                return
            item_id = sel.get("item_id")
            qty = int(sel.get("qty") or 0)
            if not item_id or qty <= 0:
                QtWidgets.QMessageBox.information(self, "Info", "Nie wybrano pozycji lub ilości.")
                return

            sku = sel.get("sku") or str(item_id)
            name = sel.get("name") or ""
            uom = sel.get("uom") or ""           

            r = self.table.rowCount()
            self.table.insertRow(r)

            # Kol. 0: SKU + UserRole=item_id
            sku_item = QtWidgets.QTableWidgetItem(sku)
            sku_item.setData(QtCore.Qt.UserRole, int(item_id))
            self.table.setItem(r, 0, sku_item)

            # Kol. 1 i 2: nazwa/JM
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(name))
            self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(uom))

            # Kol. 3: ilość (edytowalne pole z walidatorem) – ustaw z wyboru
            qty_edit = QtWidgets.QLineEdit(str(int(qty)))
            qty_edit.setValidator(QtGui.QIntValidator(1, 99999, qty_edit))
            self.table.setCellWidget(r, 3, qty_edit)

            # Kol. 4: przycisk usuń
            btn_rm = QtWidgets.QPushButton("Usuń")
            btn_rm.clicked.connect(self._remove_row)
            self.table.setCellWidget(r, 4, btn_rm)

    # ===================== Finalizacja (wersja koszyk) =====================

    def _on_accept_cart(self) -> None:
        try:
            emp_id = self.employee_cb.currentData()
            if emp_id is None:
                QtWidgets.QMessageBox.warning(self, "Błąd", "Wybierz pracownika")
                return

            # Zbierz linie z tabeli i dodaj do koszyka
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
                if item_id and qty > 0:
                    lines.append((int(item_id), int(qty)))

            # scal identyczne pozycje
            merged: dict[int, int] = {}
            for item_id, qty in lines:
                merged[item_id] = merged.get(item_id, 0) + qty

            # utwórz/uzupełnij sesję OPEN
            sess_mgr = SessionManager(self.repo.engine, self.station_id, int(self.operator_user_id or 0))
            session = sess_mgr.ensure_open_session(int(emp_id))
            session_id = int(session["id"]) if session else 0

            cart = CartRepository(self.repo.engine)
            for item_id, qty in merged.items():
                cart.add(session_id, int(item_id), int(qty))

            # wymagaj karty/pinu pracownika
            if not RfidService().verify_employee(self.repo, int(emp_id), self):
                return

            # potwierdzenie
            num_lines = len(cart.list_lines(session_id))
            if (
                QtWidgets.QMessageBox.question(
                    self,
                    "Potwierdź",
                    f"Czy wydać pozycje z koszyka? (wierszy: {num_lines})",
                )
                != QtWidgets.QMessageBox.Yes
            ):
                return

            # finalizacja
            res = CheckoutService(self.repo.engine, self.repo).finalize_issue(session_id, int(emp_id))
            if res.get("status") == "success":
                msg = f"Wydanie zapisane (wierszy: {res.get('lines')})"
                if res.get("flagged"):
                    msg += "\nDodano do Wyjątki"
                QtWidgets.QMessageBox.information(self, "OK", msg)
                self.accept()
            elif res.get("status") == "empty":
                QtWidgets.QMessageBox.warning(self, "Koszyk pusty", "Brak pozycji do wydania.")
            else:
                QtWidgets.QMessageBox.warning(self, "Błąd", f"Nie udało się zapisać: {res}")
        except Exception as e:  # pragma: no cover - UI error path
            self.log.exception("Błąd operacji ISSUE (_on_accept_cart)")
            QtWidgets.QMessageBox.critical(self, "Błąd", str(e))

    # ===================== Logika linii (ręczne dodawanie po SKU) =====================

    def _add_line(self) -> None:
        sku = self.sku_edit.text().strip()
        if not sku:
            return

        # --- resolve item from repo ---
        try:
            item = self.items_repo.get_item_by_sku(sku) if self.items_repo else None
            if not item:
                raise ValueError("not found")
        except Exception:
            self.log.exception("Błąd operacji ISSUE (resolve SKU)")
            QtWidgets.QMessageBox.warning(self, "Błąd", f"Nie znaleziono SKU: {sku}")
            return
        
        item_id = item.get("id")
        sku = item.get("sku") or sku
        name = item.get("name") or ""
        uom = item.get("uom") or ""

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
            # Nowa ścieżka: wywołania domenowe per-linia (AuthRepo.issue_tool),
            # z poprawnym flagowaniem issued_without_return.
            flagged = False
            open_qty = 0
            try:
                # pomocniczo – czy pracownik ma otwarte sztuki
                if hasattr(self.repo, "get_employee_open_qty"):
                    open_qty = int(self.repo.get_employee_open_qty(int(emp_id)))
            except Exception:
                self.log.exception("Nie udało się pobrać salda pracownika")

            if open_qty > 0:
                # zapytaj o natychmiastowy zwrot -> bundle
                if (
                    QtWidgets.QMessageBox.question(
                        self,
                        "Potwierdź",
                        "Pracownik ma otwarte sztuki. Zwrot teraz?",
                    )
                    == QtWidgets.QMessageBox.Yes
                ):
                    if hasattr(self.repo, "issue_return_bundle"):
                        res = self.repo.issue_return_bundle(
                            employee_id=int(emp_id),
                            returns=merged_lines,
                            issues=merged_lines,
                        )
                        flagged = flagged or bool(res.get("flagged"))
                    else:
                        # fallback – zwykłe ISSUE, jeśli brak bundle w repo
                        for item_id, qty in merged_lines:
                            res = self.repo.issue_tool(
                                employee_id=int(emp_id),
                                item_id=item_id,
                                qty=qty,
                                operation_uuid=str(uuid.uuid4()),
                            )
                            flagged = flagged or bool(res.get("flagged"))
                else:
                    for item_id, qty in merged_lines:
                        res = self.repo.issue_tool(
                            employee_id=int(emp_id),
                            item_id=item_id,
                            qty=qty,
                            operation_uuid=str(uuid.uuid4()),
                        )
                        flagged = flagged or bool(res.get("flagged"))
            else:
                for item_id, qty in merged_lines:
                    res = self.repo.issue_tool(
                        employee_id=int(emp_id),
                        item_id=item_id,
                        qty=qty,
                        operation_uuid=str(uuid.uuid4()),
                    )
                    flagged = flagged or bool(res.get("flagged"))

            self.log.info(
                "Issued %d lines to employee %s (RFID verified)",
                len(merged_lines),
                emp_id,
            )
            msg = "Wydanie zapisane"
            if flagged:
                msg += "\nDodano do Wyjątki"
            QtWidgets.QMessageBox.information(self, "OK", msg)
            self.accept()
        except Exception as e:  # pragma: no cover - UI error path
            self.log.exception("Błąd operacji ISSUE (_on_accept)")
            QtWidgets.QMessageBox.critical(self, "Błąd", str(e))
