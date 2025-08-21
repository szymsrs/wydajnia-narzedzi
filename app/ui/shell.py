# app/ui/shell.py
from __future__ import annotations
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QToolBar, QLabel,
    QWidgetAction, QPushButton, QStackedWidget, QStatusBar, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QTimer, Slot
from PySide6 import QtGui

# qdarktheme opcjonalnie
try:
    import qdarktheme
    HAS_QDARK = True
except Exception:
    HAS_QDARK = False

# ===== Uprawnienia (role -> moduły/akcje) =====
PERMISSIONS = {
    "admin": {
        "modules": {"Operacje", "Inwentaryzacja", "Raporty", "Wyjątki", "Ustawienia", "Użytkownicy"},
        "actions": {"users.manage", "inv.adjust", "reports.all"},
    },
    "kierownik": {
        "modules": {"Operacje", "Inwentaryzacja", "Raporty", "Wyjątki"},
        "actions": {"inv.adjust", "reports.team"},
    },
    "operator": {
        "modules": {"Operacje", "Raporty", "Wyjątki"},
        "actions": {"reports.self"},
    },
    "audytor": {
        "modules": {"Raporty", "Wyjątki", "Inwentaryzacja"},
        "actions": {"reports.all"},
    },
}

ORDERED_MODULES = ["Operacje", "Inwentaryzacja", "Raporty", "Wyjątki", "Ustawienia", "Użytkownicy"]


class MainWindow(QMainWindow):
    request_logout = Signal()

    def __init__(self, app_name: str, *, db_ok: bool = True,
                 db_error: str | None = None, session: dict | None = None,
                 repo=None):
        super().__init__()
        self.db_ok = db_ok
        self.db_error = db_error
        self.session = session or {}
        self.repo = repo
        self.widgets: dict[str, QWidget] = {}

        user_info = (
            f"{self.session.get('first_name','')} {self.session.get('last_name','')} "
            f"({self.session.get('role','')})"
            if self.session else app_name
        )
        self.setWindowTitle(f"{app_name} – {user_info}")
        self.resize(1280, 800)

        # Główny toolbar (tytuł + użytkownik + wyloguj)
        self._build_topbar(app_name)

        # Pasek modułów i centralny stos widżetów
        self._build_modulebar()
        self.stack = QStackedWidget()
        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(8, 0, 8, 8)
        lay.addWidget(self.stack)
        self.setCentralWidget(container)

        # Stopka (status bar)
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.lbl_db  = QLabel("DB: ✅ połączona" if self.db_ok else "DB: ❌ offline")
        self.lbl_ws  = QLabel(f"Stanowisko: {self.session.get('station','—')}")
        self.lbl_user= QLabel(f"Zalogowany: {self.session.get('name','—')}")
        for w in (self.lbl_db, self.lbl_ws, self.lbl_user):
            w.setStyleSheet("padding:0 8px;")
            sb.addPermanentWidget(w)

        # Zbuduj moduły zgodnie z rolą
        self._rebuild_modules()

        # === Privacy cover (pełna zasłona) ===
        self._cover = QWidget(self)
        self._cover.setObjectName("privacyCover")
        self._cover.setStyleSheet("""
#privacyCover { background: #0A0A0A; }
#coverText { color: white; font-size: 22px; font-weight: 600; }
""")
        self._cover.setVisible(False)
        cov_lay = QVBoxLayout(self._cover)
        cov_lay.setContentsMargins(24, 24, 24, 24)
        cov_lay.addStretch(1)
        self._cover_label = QLabel("🔒 Wylogowano — zaloguj się ponownie")
        self._cover_label.setObjectName("coverText")
        self._cover_label.setAlignment(Qt.AlignCenter)
        cov_lay.addWidget(self._cover_label, 0, Qt.AlignCenter)
        cov_lay.addStretch(2)

    # ---------- Role/Uprawnienia ----------
    def _effective_role(self) -> str:
        if self.session.get("is_admin"):
            return "admin"
        return (self.session.get("role") or "operator").lower()

    def _allowed_modules(self) -> list[str]:
        role = self._effective_role()
        mods = PERMISSIONS.get(role, PERMISSIONS["operator"])["modules"]
        return [m for m in ORDERED_MODULES if m in mods]

    def _can(self, action: str) -> bool:
        role = self._effective_role()
        acts = PERMISSIONS.get(role, PERMISSIONS["operator"])["actions"]
        return bool(self.session.get("is_admin")) or action in acts

    # ---------- UI helpers ----------
    def _build_topbar(self, app_name: str):
        tb = QToolBar("Główne")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(Qt.TopToolBarArea, tb)
        self.topbar = tb  # referencja, żeby ukrywać/pokazywać

        title = QLabel(app_name)
        title.setStyleSheet("font-weight:600; padding:4px 10px;")
        act_title = QWidgetAction(self); act_title.setDefaultWidget(title)
        tb.addAction(act_title); tb.addSeparator()

        spacer = QWidget(); spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        act_sp = QWidgetAction(self); act_sp.setDefaultWidget(spacer)
        tb.addAction(act_sp)

        user_txt = (
            f"{self.session.get('first_name','')} {self.session.get('last_name','')} • {self.session.get('role','')}"
            if self.session else "Niezalogowany"
        )
        self.user_label = QLabel(user_txt); self.user_label.setStyleSheet("padding:4px 10px;")
        act_user = QWidgetAction(self); act_user.setDefaultWidget(self.user_label)
        tb.addAction(act_user)

        btn_logout = QPushButton("Wyloguj")
        btn_logout.clicked.connect(self.request_logout.emit)  # main spina to do handle_logout
        act_out = QWidgetAction(self); act_out.setDefaultWidget(btn_logout)
        tb.addAction(act_out)

    def _build_modulebar(self):
        self.modbar = QToolBar("Moduły")
        self.modbar.setMovable(False)
        self.modbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(Qt.TopToolBarArea, self.modbar)
        self._mod_group = QtGui.QActionGroup(self)
        self._mod_group.setExclusive(True)
        self._mod_group.triggered.connect(lambda a: self._open_module(a.text()))

    def _add_module_action(self, name: str):
        act = self.modbar.addAction(name)
        act.setCheckable(True)
        self._mod_group.addAction(act)

    # --- NOWE: bezpieczna podmiana widżetu modułu ---
    def _replace_widget(self, name: str, new_widget: QWidget):
        """Podmień (jeśli był) istniejący widget modułu zarówno w dict, jak i w QStackedWidget."""
        old = self.widgets.get(name)
        if old is new_widget:
            return
        if old is not None:
            idx = self.stack.indexOf(old)
            if idx != -1:
                self.stack.removeWidget(old)
            old.deleteLater()
        self.widgets[name] = new_widget
        # Upewnij się, że jest w stacku
        if self.stack.indexOf(new_widget) == -1:
            self.stack.addWidget(new_widget)

    def _ensure_placeholder(self, name: str, details: str | None = None):
        # Placeholder z opcjonalnym opisem błędu
        w = QLabel(f"{name} – ekran w przygotowaniu" + (f"\n\n{details}" if details else ""))
        w.setAlignment(Qt.AlignCenter)
        self._replace_widget(name, w)

    def _clear_modulebar(self):
        # Usuń wszystkie akcje
        for a in list(self._mod_group.actions()):
            self.modbar.removeAction(a)
            self._mod_group.removeAction(a)

    def _rebuild_modules(self):
        """Buduje listę modułów i widżetów zgodnie z obecną sesją/rolą."""
        # 1) Wyczyść pasek modułów
        self._clear_modulebar()

        # 2) Utwórz widżety tylko dla dozwolonych modułów
        allowed = self._allowed_modules()
        for name in allowed:
            if name == "Użytkownicy":
                # Widżet dostępny tylko dla admina – ostrożnie z importem
                try:
                    from app.ui.users_widget import UsersWidget
                    # Podmień placeholder (lub brak) na realny widget
                    self._replace_widget("Użytkownicy", UsersWidget(self.repo, self))
                except Exception as e:
                    import traceback
                    tb = traceback.format_exc(limit=3)
                    self._ensure_placeholder("Użytkownicy", details=f"Błąd ładowania:\n{e}\n\n{tb}")
            else:
                # dla pozostałych modułów na razie placeholder (podmiana gdy będą gotowe)
                self._ensure_placeholder(name)

            self._add_module_action(name)

        # 3) Ustaw moduł domyślny
        default_module = allowed[0] if allowed else "Operacje"
        self._open_module(default_module)

    def _open_module(self, name: str):
        # twardy guard na wypadek prób „na skróty”
        if name not in self._allowed_modules():
            return
        # zaznacz akcję
        for a in self._mod_group.actions():
            if a.text() == name:
                a.setChecked(True)
        # wczytaj widget (placeholder jeśli brak)
        w = self.widgets.get(name)
        if w is None:
            self._ensure_placeholder(name)
            w = self.widgets[name]
        if self.stack.indexOf(w) == -1:
            self.stack.addWidget(w)
        self.stack.setCurrentWidget(w)

    # ---------- Status/tytuł ----------
    def _update_statusbar(self):
        self.lbl_ws.setText(f"Stanowisko: {self.session.get('station','—')}")
        self.lbl_user.setText(f"Zalogowany: {self.session.get('name','—')}")
        base = self.windowTitle().split(" – ")[0]
        self.setWindowTitle(
            f"{base} – "
            f"{self.session.get('first_name','')} {self.session.get('last_name','')} "
            f"({self.session.get('role','')})"
        )
        self.user_label.setText(
            f"{self.session.get('first_name','')} {self.session.get('last_name','')} • {self.session.get('role','')}"
            if self.session else "Niezalogowany"
        )

    def set_session(self, session: dict | None):
        self.session = session or {}
        self._update_statusbar()
        # Po zmianie sesji/roli – przebuduj moduły
        self._rebuild_modules()

    # ---------- Privacy cover ----------
    def _resize_cover(self):
        self._cover.setGeometry(self.rect())

    def _toggle_chrome(self, visible: bool):
        # Ukryj/pokaż paski i centralny widok
        self.topbar.setVisible(visible)
        self.modbar.setVisible(visible)
        if self.statusBar():
            self.statusBar().setVisible(visible)
        self.stack.setVisible(visible)

    def show_privacy_cover(self, text: str = "🔒 Wylogowano — zaloguj się ponownie"):
        # Najpierw ukryj całe UI, potem pokaż czarną zasłonę
        self._toggle_chrome(False)
        self._cover_label.setText(text)
        self._resize_cover()
        self._cover.raise_()
        self._cover.show()
        self._cover.repaint()

    def hide_privacy_cover(self):
        self._cover.hide()
        self._toggle_chrome(True)

    # ---------- Lifecycle ----------
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._resize_cover()

    def showEvent(self, e):
        super().showEvent(e)
        # Jeśli okno startuje bez sesji (logowanie nad oknem)
        if not self.session and self.repo:
            self.show_privacy_cover("🔒 Zablokowano — zaloguj się")
            QTimer.singleShot(0, self._require_login)

    # ---------- Logowanie/wylogowanie ----------
    def _require_login(self):
        from app.ui.login_dialog import LoginDialog
        station = (self.session or {}).get("station", "UNKNOWN")
        dlg = LoginDialog(repo=self.repo, station_id=station, parent=self)
        dlg.authenticated.connect(self._on_login_ok)
        dlg.resize(self.size())
        dlg.move(self.frameGeometry().topLeft())
        if dlg.exec() == LoginDialog.Accepted:
            # _on_login_ok ustawi sesję, teraz odsłoń UI
            self.hide_privacy_cover()
        else:
            from PySide6.QtWidgets import QApplication
            QApplication.instance().quit()

    @Slot()
    def handle_logout(self):
        # 1) Natychmiast zasłoń i wyczyść sesję
        station = (self.session or {}).get("station", "UNKNOWN")
        self.session = {}
        if self.statusBar():
            self.statusBar().showMessage("Wylogowano – zaloguj się ponownie.")
        self.show_privacy_cover("🔒 Wylogowano — zaloguj się ponownie")

        # 2) Login overlay nad TYM samym oknem
        from app.ui.login_dialog import LoginDialog
        dlg = LoginDialog(repo=self.repo, station_id=station, parent=self)
        dlg.authenticated.connect(self._on_login_ok)
        dlg.resize(self.size())
        dlg.move(self.frameGeometry().topLeft())
        if dlg.exec() == LoginDialog.Accepted:
            self.hide_privacy_cover()
        else:
            from PySide6.QtWidgets import QApplication
            QApplication.instance().quit()

    def _on_login_ok(self, session: dict):
        # Ustaw sesję i przebuduj UI pod nową rolę
        self.set_session(session or {})


def apply_theme(theme: str = "dark"):
    if 'qdarktheme' in globals() and HAS_QDARK:
        qdarktheme.setup_theme("dark" if theme == "dark" else "light")
