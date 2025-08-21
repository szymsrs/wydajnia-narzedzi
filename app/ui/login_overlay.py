# app/ui/login_overlay.py
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont

class LoginOverlay(QDialog):
    authenticated = Signal(dict)   # np. {"user_id": 1, "first_name": "...", ...}

    def __init__(self, repo, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.repo = repo  # dostęp do metod verify_*

        root = QVBoxLayout(self)
        root.setContentsMargins(0,0,0,0)

        # półprzezroczyste tło
        self.bg = QLabel("", self)
        self.bg.setStyleSheet("background: rgba(0,0,0,0.45); border-radius: 0;")
        self.bg.lower()

        card = self._build_card()
        wrapper = QVBoxLayout()
        wrapper.addStretch(1)
        wrapper.addWidget(card, 0, Qt.AlignHCenter)
        wrapper.addStretch(2)
        root.addLayout(wrapper)

        self.resize(parent.size() if parent else self.size())
        QTimer.singleShot(0, self._resize_bg)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._resize_bg()

    def _resize_bg(self):
        self.bg.setGeometry(0, 0, self.width(), self.height())

    def _build_card(self):
        from PySide6.QtWidgets import QWidget
        w = QWidget(self)
        w.setStyleSheet("""
            QWidget { background: #1E1E1E; border-radius: 16px; }
            QLineEdit { padding: 10px 12px; border-radius: 10px; }
            QPushButton { padding: 10px 14px; border-radius: 12px; font-weight: 600; }
            QLabel.hint { color: #BBBBBB; }
            QLabel.error { color: #ff6b6b; }
        """)
        lay = QVBoxLayout(w); lay.setContentsMargins(24,24,24,24); lay.setSpacing(12)

        title = QLabel("Zaloguj się")
        f = QFont(); f.setPointSize(18); f.setBold(True); title.setFont(f)
        lay.addWidget(title, 0, Qt.AlignHCenter)

        self.input = QLineEdit(); self.input.setEchoMode(QLineEdit.Password)
        self.input.setPlaceholderText("Karta / PIN / login hasło")
        self.input.returnPressed.connect(self._submit)
        lay.addWidget(self.input)

        self.err = QLabel(""); self.err.setProperty("class", "error")
        lay.addWidget(self.err)

        hint = QLabel("Przyłóż kartę lub wpisz PIN. Dla hasła: „login hasło”.")
        hint.setObjectName("hint"); hint.setProperty("class", "hint")
        lay.addWidget(hint, 0, Qt.AlignLeft)

        btns = QHBoxLayout()
        ok = QPushButton("Zaloguj"); ok.clicked.connect(self._submit)
        btns.addStretch(1); btns.addWidget(ok)
        lay.addLayout(btns)
        return w

    def shake(self):
        # prosty efekt „drgania” karty przy błędzie (opcjonalnie)
        pass

    def _submit(self):
        token = self.input.text().strip()
        if not token:
            return

        # 1) RFID (HID zwykle kończy Enterem – i tak tu trafimy)
        if self._looks_like_rfid(token):
            user = self.repo.verify_rfid(token)

        # 2) PIN (same cyfry 4–10 znaków)
        elif token.isdigit() and 4 <= len(token) <= 10:
            user = self.repo.verify_pin(token)

        # 3) login + hasło (spacja)
        elif " " in token:
            login, pwd = token.split(" ", 1)
            user = self.repo.verify_password(login, pwd)

        else:
            user = None

        if user:
            self.authenticated.emit(user)
            self.accept()
        else:
            self.err.setText("Nieprawidłowe dane. Spróbuj ponownie.")
            self.input.selectAll()
            self.input.setFocus()
            self.shake()

    def _looks_like_rfid(self, s: str) -> bool:
        # Dopasuj do formatu Twojego czytnika (np. hex/decimal; często 8–14 znaków, czasem z CR/LF)
        # Tu wersja bezpieczna: alfanumeryk 6–32
        return s.isalnum() and 6 <= len(s) <= 32
