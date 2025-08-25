# app/ui/users_widget.py
from __future__ import annotations

from typing import TYPE_CHECKING
from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt
import re
import logging

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.ui.shell import MainWindow


class UsersWidget(QWidget):
    def __init__(self, repo, parent: 'MainWindow'):
        super().__init__(parent)
        self.repo = repo
        self.parent = parent

        # Guard – tylko admin
        if not (parent.session.get("is_admin") or (parent.session.get("role", "").lower() == "admin")):
            from PySide6.QtWidgets import QLabel, QVBoxLayout
            lay = QVBoxLayout(self)
            lab = QLabel("Brak uprawnień do modułu Użytkownicy.")
            lab.setAlignment(Qt.AlignCenter)
            lay.addWidget(lab)
            self.setEnabled(False)
            return

        self._build()
        self.refresh()

    # ---------- UI ----------
    def _build(self):
        # pasek narzędzi nad tabelą
        self.search = QtWidgets.QLineEdit(placeholderText="Szukaj: imię / nazwisko / login…")
        self.btn_refresh = QtWidgets.QToolButton(text="Odśwież")
        self.btn_refresh.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        self.btn_add = QtWidgets.QToolButton(text="Dodaj")
        self.btn_save = QtWidgets.QToolButton(text="Zapisz")
        self.btn_reset_pw = QtWidgets.QToolButton(text="Reset hasła…")
        self.btn_reset_pin = QtWidgets.QToolButton(text="Ustaw PIN…")
        self.btn_clear_pin = QtWidgets.QToolButton(text="Wyczyść PIN")
        self.btn_assign_card = QtWidgets.QToolButton(text="Przypisz kartę…")
        self.btn_toggle_active = QtWidgets.QToolButton(text="Dezaktywuj")
        self.btn_toggle_details = QtWidgets.QToolButton(text="Panel szczegółów (F4)")
        self.btn_toggle_details.setCheckable(True)
        self.btn_toggle_details.setChecked(True)

        # NOWE: przełącznik pokazywania PIN-u w tabeli
        self.chk_show_pin = QtWidgets.QCheckBox("Pokaż PIN w tabeli")
        self.chk_show_pin.setChecked(False)

        tools = QtWidgets.QHBoxLayout()
        tools.addWidget(self.search, 1)
        tools.addWidget(self.chk_show_pin)  # <--- NOWE
        for b in (
            self.btn_refresh, self.btn_add, self.btn_save, self.btn_reset_pw,
            self.btn_reset_pin, self.btn_clear_pin, self.btn_assign_card,
            self.btn_toggle_active, self.btn_toggle_details
        ):
            tools.addWidget(b)

        # tabela
        self.table = QtWidgets.QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(["ID", "Login", "Imię", "Nazwisko", "Rola", "Admin", "Aktywne", "Hasło", "PIN"])
        hh = self.table.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)  # ID
        hh.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)  # login
        hh.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)  # imię
        hh.setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)           # nazwisko (rozciąga)
        for col in (4, 5, 6, 7, 8):
            hh.setSectionResizeMode(col, QtWidgets.QHeaderView.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        # formularz (panel szczegółów)
        self.le_id = QtWidgets.QLineEdit(); self.le_id.setReadOnly(True)
        self.le_login = QtWidgets.QLineEdit()
        self.le_fn = QtWidgets.QLineEdit()
        self.le_ln = QtWidgets.QLineEdit()
        self.cb_role = QtWidgets.QComboBox(); self.cb_role.addItems(["operator", "kierownik", "audytor", "admin"])
        self.cb_admin = QtWidgets.QCheckBox("Administrator (is_admin)")
        self.cb_active = QtWidgets.QCheckBox("Aktywne konto")
        self.le_card = QtWidgets.QLineEdit(); self.le_card.setPlaceholderText("UID karty (opcjonalnie)")
        self.le_pin_plain = QtWidgets.QLineEdit(); self.le_pin_plain.setReadOnly(True)

        form = QtWidgets.QFormLayout()
        form.addRow("ID:", self.le_id)
        form.addRow("Login:", self.le_login)
        form.addRow("Imię:", self.le_fn)
        form.addRow("Nazwisko:", self.le_ln)
        form.addRow("Rola:", self.cb_role)
        form.addRow("", self.cb_admin)
        form.addRow("", self.cb_active)
        form.addRow("Karta (UID):", self.le_card)
        form.addRow("PIN (jawny):", self.le_pin_plain)

        details = QtWidgets.QWidget()
        details.setLayout(form)

        # Splitter: tabela | szczegóły
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(self.table)
        splitter.addWidget(details)
        splitter.setStretchFactor(0, 4)  # tabela większa
        splitter.setStretchFactor(1, 3)

        # całość
        main = QtWidgets.QVBoxLayout(self)
        main.addLayout(tools)
        main.addWidget(splitter, 1)

        # sygnały
        self.btn_refresh.clicked.connect(self.refresh)
        self.search.returnPressed.connect(self.refresh)
        self.chk_show_pin.toggled.connect(self.refresh)  # <--- NOWE
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        self.btn_add.clicked.connect(self._add)
        self.btn_save.clicked.connect(self._save)
        self.btn_reset_pw.clicked.connect(self._reset_password)
        self.btn_reset_pin.clicked.connect(self._reset_pin)
        self.btn_clear_pin.clicked.connect(self._clear_pin)
        self.btn_assign_card.clicked.connect(self._assign_card)
        self.btn_toggle_active.clicked.connect(self._toggle_active)
        self.btn_toggle_details.toggled.connect(lambda on: details.setVisible(on))

        self._details = details  # referencja

    # ---------- Helpers uprawnień ----------
    def _current_user_id(self) -> int | None:
        try:
            return int(self.parent.session.get("user_id"))
        except Exception:
            return None

    def _is_last_active_admin(self, editing_emp_id: int, new_is_admin: bool, new_active: bool) -> bool:
        """
        Zabezpieczenie: nie wolno zdezaktywować ostatniego aktywnego admina
        ani odebrać admina ostatniemu aktywnemu adminowi.
        repo powinno udostępniać count_active_admins() i is_active_admin(emp_id).
        """
        try:
            total_admins = self.repo.count_active_admins()  # liczba aktywnych adminów
        except Exception:
            return False  # brak danych – nie blokujmy na siłę (opcjonalnie: True dla ultra-bezpieczeństwa)

        try:
            before_is_admin, before_active = self.repo.is_active_admin(editing_emp_id)  # (bool,bool)
        except Exception:
            before_is_admin, before_active = (None, None)

        losing_admin = (before_is_admin is True and before_active is True) and (new_is_admin is False or new_active is False)
        if losing_admin and total_admins <= 1:
            return True
        return False

    # ---------- Dane ----------
    def refresh(self):
        q = self.search.text().strip() or None
        try:
            rows = self.repo.list_employees(q)
        except Exception as e:
            log.exception("Błąd ładowania użytkowników q=%r lim=%s", q, None)
            QtWidgets.QMessageBox.warning(self, "Błąd ładowania użytkowników", str(e))
            return    
        self.table.setRowCount(len(rows))
        for r, u in enumerate(rows):
            # PIN w tabeli: jawny tylko jeśli zaznaczono checkbox; w przeciwnym razie status
            if self.chk_show_pin.isChecked():
                pin_cell = (u.get("pin_plain") or "—")
            else:
                pin_cell = "ustawiony" if (u.get("has_pin") or u.get("pin_plain")) else "—"

            vals = [
                u["id"], u["login"], u["first_name"], u["last_name"], u["role"],
                "tak" if u.get("is_admin") else "nie",
                "tak" if u.get("active") else "nie",
                "tak" if u.get("has_password") else "brak",
                pin_cell,
            ]
            for c, v in enumerate(vals):
                it = QtWidgets.QTableWidgetItem(str(v))
                if c == 0:
                    it.setData(Qt.ItemDataRole.UserRole, u["id"])
                self.table.setItem(r, c, it)
        if rows:
            self.table.selectRow(0)
        else:
            self._clear_form()

    def _on_row_selected(self):
        items = self.table.selectedItems()
        if not items:
            self._clear_form(); return
        row = items[0].row()
        it_id = self.table.item(row, 0)
        emp_id = it_id.data(Qt.ItemDataRole.UserRole) or int(it_id.text())
        try:
            u = self.repo.get_employee(emp_id)
        except Exception as e:
            log.exception("Błąd ładowania użytkownika id=%s", emp_id)
            QtWidgets.QMessageBox.warning(self, "Błąd ładowania użytkownika", str(e))
            self._clear_form()
            return
        if not u:
            self._clear_form(); return

        self.le_id.setText(str(u["id"]))
        self.le_login.setText(u.get("login") or "")
        self.le_fn.setText(u.get("first_name") or "")
        self.le_ln.setText(u.get("last_name") or "")
        self.cb_role.setCurrentText(u.get("role") or "operator")
        self.cb_admin.setChecked(bool(u.get("is_admin")))
        self.cb_active.setChecked(bool(u.get("active")))
        self.le_card.setText(u.get("rfid_uid") or "")

        # Pokaż jawny PIN w panelu szczegółów (jeśli repo go zwraca)
        self.le_pin_plain.setText(u.get("pin_plain") or "")

        self.btn_toggle_active.setText("Dezaktywuj" if u.get("active") else "Aktywuj")

    def _clear_form(self):
        for w in (self.le_id, self.le_login, self.le_fn, self.le_ln, self.le_card, self.le_pin_plain):
            w.setText("")
        self.cb_role.setCurrentText("operator")
        self.cb_admin.setChecked(False)
        self.cb_active.setChecked(True)
        self.btn_toggle_active.setText("Dezaktywuj")

    # ---------- Akcje ----------
    def _add(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Nowy użytkownik")
        f = QtWidgets.QFormLayout(dlg)
        le_login = QtWidgets.QLineEdit()
        le_fn = QtWidgets.QLineEdit()
        le_ln = QtWidgets.QLineEdit()
        cb_role = QtWidgets.QComboBox(); cb_role.addItems(["operator", "kierownik", "audytor", "admin"])
        cb_admin = QtWidgets.QCheckBox("Administrator")
        le_pw = QtWidgets.QLineEdit(); le_pw.setEchoMode(QtWidgets.QLineEdit.Password)
        le_pin = QtWidgets.QLineEdit(); le_pin.setEchoMode(QtWidgets.QLineEdit.Password); le_pin.setInputMask("")  # pozwól wklejać
        le_card = QtWidgets.QLineEdit()
        f.addRow("Login*", le_login)
        f.addRow("Imię*", le_fn)
        f.addRow("Nazwisko*", le_ln)
        f.addRow("Rola", cb_role)
        f.addRow(cb_admin)
        f.addRow("Hasło (opcjonalne)", le_pw)
        f.addRow("PIN (opcjonalny)", le_pin)
        f.addRow("Karta UID (opcjonalnie)", le_card)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        f.addRow(btns)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        if not dlg.exec(): return

        login = le_login.text().strip()
        if not login or not re.fullmatch(r"[A-Za-z0-9_.-]{3,50}", login):
            QtWidgets.QMessageBox.warning(self, "Błąd", "Nieprawidłowy login (3–50 znaków, A–z/0–9/_.-)."); return
        fn = le_fn.text().strip(); ln = le_ln.text().strip()
        if not fn or not ln:
            QtWidgets.QMessageBox.warning(self, "Błąd", "Imię i nazwisko są wymagane."); return
        role = cb_role.currentText()
        is_admin = cb_admin.isChecked()

        pw = le_pw.text().strip() or None
        if pw and len(pw) < 8:
            QtWidgets.QMessageBox.warning(self, "Błąd", "Hasło musi mieć min. 8 znaków."); return

        pin = le_pin.text().strip() or None
        if pin and not re.fullmatch(r"\d{4,8}", pin):
            QtWidgets.QMessageBox.warning(self, "Błąd", "PIN musi mieć 4–8 cyfr."); return

        card = le_card.text().strip() or None

        emp, err = self.repo.create_employee(login, fn, ln, role, is_admin, pw, pin, card, True)
        if err:
            QtWidgets.QMessageBox.warning(self, "Błąd", err); return

        self.refresh()
        QtWidgets.QMessageBox.information(self, "OK", f"Utworzono użytkownika {login}.")

    def _save(self):
        if not self.le_id.text(): return
        emp_id = int(self.le_id.text())

        new_login = self.le_login.text().strip()
        if not new_login or not re.fullmatch(r"[A-Za-z0-9_.-]{3,50}", new_login):
            QtWidgets.QMessageBox.warning(self, "Błąd", "Nieprawidłowy login (3–50 znaków, A–z/0–9/_.-)."); return

        new_first = self.le_fn.text().strip()
        new_last = self.le_ln.text().strip()
        if not new_first or not new_last:
            QtWidgets.QMessageBox.warning(self, "Błąd", "Imię i nazwisko są wymagane."); return

        new_role = self.cb_role.currentText()
        new_is_admin = self.cb_admin.isChecked()
        new_active = self.cb_active.isChecked()

        # Blokady: sam sobie nie odbierze admina ani nie zdezaktywuje konta
        if self._current_user_id() == emp_id:
            if not new_is_admin:
                QtWidgets.QMessageBox.warning(self, "Błąd", "Nie możesz odebrać sobie uprawnień administratora."); return
            if not new_active:
                QtWidgets.QMessageBox.warning(self, "Błąd", "Nie możesz zdezaktywować własnego konta."); return

        # Blokada ostatniego aktywnego admina
        if self._is_last_active_admin(emp_id, new_is_admin, new_active):
            QtWidgets.QMessageBox.warning(self, "Błąd", "Nie można zdezaktywować / odebrać uprawnień ostatniemu aktywnemu administratorowi."); return

        err = self.repo.update_employee_basic(
            emp_id,
            login=new_login,
            first_name=new_first,
            last_name=new_last,
            role=new_role,
            is_admin=new_is_admin,
            active=new_active
        )
        if err:
            QtWidgets.QMessageBox.warning(self, "Błąd", err); return

        card_err = self.repo.assign_card(emp_id, self.le_card.text().strip() or None)
        if card_err:
            QtWidgets.QMessageBox.warning(self, "Karta", card_err)

        self.refresh()
        QtWidgets.QMessageBox.information(self, "Zapisano", "Dane użytkownika zaktualizowane.")

    def _reset_password(self):
        if not self.le_id.text(): return
        emp_id = int(self.le_id.text())
        pw, ok = QtWidgets.QInputDialog.getText(self, "Reset hasła", "Nowe hasło (min. 8 znaków):", echo=QtWidgets.QLineEdit.Password)
        if not ok or not pw: return
        pw = pw.strip()
        if len(pw) < 8:
            QtWidgets.QMessageBox.warning(self, "Błąd", "Hasło musi mieć min. 8 znaków."); return
        err = self.repo.reset_password(emp_id, pw)
        if err:
            QtWidgets.QMessageBox.warning(self, "Błąd", err); return
        row = self.table.currentRow()
        if row >= 0:
            self.table.setItem(row, 7, QtWidgets.QTableWidgetItem("tak"))
        QtWidgets.QMessageBox.information(self, "OK", "Hasło zostało ustawione.")

    def _reset_pin(self):
        if not self.le_id.text(): return
        emp_id = int(self.le_id.text())
        pin, ok = QtWidgets.QInputDialog.getText(self, "Ustaw PIN", "Nowy PIN (4–8 cyfr):", echo=QtWidgets.QLineEdit.Password)
        if not ok or not pin: return
        pin = pin.strip()
        if not re.fullmatch(r"\d{4,8}", pin):
            QtWidgets.QMessageBox.warning(self, "Błąd", "PIN musi mieć 4–8 cyfr."); return
        err = self.repo.reset_pin(emp_id, pin)
        if err:
            QtWidgets.QMessageBox.warning(self, "Błąd", err); return

        # pokaż w panelu i odśwież tabelę
        self.le_pin_plain.setText(pin)
        row = self.table.currentRow()
        if row >= 0:
            # jeśli checkbox jest włączony, po refreshie i tak wskoczy jawna wartość
            self.table.setItem(row, 8, QtWidgets.QTableWidgetItem("ustawiony" if not self.chk_show_pin.isChecked() else pin))
        self.refresh()
        QtWidgets.QMessageBox.information(self, "OK", "PIN został ustawiony.")

    def _clear_pin(self):
        if not self.le_id.text(): return
        if QtWidgets.QMessageBox.question(self, "Wyczyść PIN", "Na pewno usunąć PIN?") != QtWidgets.QMessageBox.Yes:
            return
        self.repo.clear_pin(int(self.le_id.text()))
        self.le_pin_plain.clear()
        row = self.table.currentRow()
        if row >= 0:
            self.table.setItem(row, 8, QtWidgets.QTableWidgetItem("—"))
        QtWidgets.QMessageBox.information(self, "OK", "PIN usunięty.")

    def _assign_card(self):
        if not self.le_id.text(): return
        uid, ok = QtWidgets.QInputDialog.getText(self, "Przypisz kartę", "UID karty (puste = usuń):")
        if not ok:
            return
        err = self.repo.assign_card(int(self.le_id.text()), (uid or "").strip() or None)
        if err:
            QtWidgets.QMessageBox.warning(self, "Karta", err); return
        self.refresh()
        QtWidgets.QMessageBox.information(self, "OK", "Karta zaktualizowana.")

    def _toggle_active(self):
        if not self.le_id.text():
            return
        # przełącz
        self.cb_active.setChecked(not self.cb_active.isChecked())
        self._save()
