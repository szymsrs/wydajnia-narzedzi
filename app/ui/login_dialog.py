from __future__ import annotations
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout, QWidget
from PySide6.QtCore import Qt, Signal, QTimer, QEasingCurve, QPropertyAnimation, QRect
from PySide6.QtGui import QFont


class LoginDialog(QDialog):
    authenticated = Signal(dict)  # ← DODAJ TO
    def __init__(self, repo, station_id: str, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.station_id = station_id
        self.session = None


        # Overlay look & feel
        self.setModal(True)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.bg = QLabel("", self)
        self.bg.setStyleSheet("background: rgba(0,0,0,0.45);")
        self.bg.lower()

        card = self._build_card()
        wrapper = QVBoxLayout()
        wrapper.addStretch(1)
        wrapper.addWidget(card, 0, Qt.AlignHCenter)
        wrapper.addStretch(2)
        root.addLayout(wrapper)

        if parent:
            self.resize(parent.size())
        QTimer.singleShot(0, self._resize_bg)

    def _resize_bg(self):
        self.bg.setGeometry(0, 0, self.width(), self.height())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._resize_bg()

    def _build_card(self) -> QWidget:
        w = QWidget(self)
        w.setStyleSheet("""
            QWidget { background: #1e1e1e; border-radius: 16px; }
            QLineEdit { padding: 10px 12px; border-radius: 10px; }
            QPushButton { padding: 10px 14px; border-radius: 12px; font-weight: 600; }
            QLabel.hint { color: #BBBBBB; }
            QLabel.error { color: #ff6b6b; min-height: 18px; }
            QLabel.ok { color: #79d279; }
        """)
        lay = QVBoxLayout(w); lay.setContentsMargins(24,24,24,24); lay.setSpacing(12)

        title = QLabel("Zaloguj się")
        f = QFont(); f.setPointSize(18); f.setBold(True)
        title.setFont(f)
        lay.addWidget(title, 0, Qt.AlignHCenter)

        self.input = QLineEdit()
        self.input.setEchoMode(QLineEdit.Password)
        self.input.setPlaceholderText("Karta / PIN / login hasło")
        self.input.textChanged.connect(self._on_typing)
        self.input.returnPressed.connect(self._submit)
        lay.addWidget(self.input)

        self.msg = QLabel(""); self.msg.setProperty("class", "error")
        lay.addWidget(self.msg)

        hint = QLabel("Przyłóż kartę lub wpisz PIN. Dla hasła wpisz: „login hasło”.")
        hint.setObjectName("hint"); hint.setProperty("class", "hint")
        lay.addWidget(hint)

        row = QHBoxLayout()
        self.btn = QPushButton("Zaloguj")
        self.btn.clicked.connect(self._submit)
        row.addStretch(1); row.addWidget(self.btn)
        lay.addLayout(row)
        return w

    # UX: lekki „shake” karty przy błędzie
    def _shake(self):
        anim = QPropertyAnimation(self, b"geometry", self)
        g = self.geometry()
        seq = [QRect(g.x()-8,g.y(),g.width(),g.height()),
               QRect(g.x()+8,g.y(),g.width(),g.height()),
               QRect(g.x()-4,g.y(),g.width(),g.height()),
               QRect(g.x()+4,g.y(),g.width(),g.height()),
               g]
        anim.setDuration(220); anim.setEasingCurve(QEasingCurve.OutQuad)
        for i, r in enumerate(seq):
            anim.setKeyValueAt(i/float(len(seq)-1), r)
        anim.start(QPropertyAnimation.DeleteWhenStopped)

    def _on_typing(self, s: str):
        s = s.strip()
        if not s:
            self.msg.setText("")
            return
        # Podpowiedź dynamiczna
        if " " in s:
            self.msg.setText("Wykryto tryb: login + hasło")
        elif s.isdigit():
            self.msg.setText("Wykryto tryb: PIN")
        elif s.isalnum() and 6 <= len(s) <= 32:
            self.msg.setText("Wykryto tryb: karta/UID")
        else:
            self.msg.setText("")

    def _submit(self):
        token = (self.input.text() or "").strip()
        if not token:
            return
        # korzystamy z login_auto z app/core/auth.py
        sess, err = self.repo.login_auto(token, station_id=self.station_id)
        if sess:
            self.session = sess
            self.msg.setText("")
            self.authenticated.emit(sess)
            self.accept()
            return
        self.msg.setText(err or "Nieprawidłowe dane. Spróbuj ponownie.")
        self.input.selectAll(); self.input.setFocus()
        self._shake()
