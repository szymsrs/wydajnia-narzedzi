# app/ui/rfid_modal.py
from __future__ import annotations
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QVBoxLayout,
    QPushButton,
    QLineEdit,
    QHBoxLayout,
)

from app.core.rfid_stub import RFIDReader


class RFIDModal(QDialog):
    """Modal oczekujący na kartę RFID lub PIN."""

    def __init__(
        self,
        reader: RFIDReader,
        *,
        allow_pin: bool = True,
        timeout: int = 10,
        parent=None,
    ):
        super().__init__(parent)
        self.reader = reader
        self.allow_pin = allow_pin
        self.timeout = timeout
        self.token: str | None = None

        self.setModal(True)
        self.setWindowTitle("Potwierdzenie kartą/PIN")

        layout = QVBoxLayout(self)
        lbl = QLabel("Przyłóż kartę lub wpisz PIN")
        lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl)

        self.pin_edit = QLineEdit()
        self.pin_edit.setEchoMode(QLineEdit.Password)
        if allow_pin:
            layout.addWidget(self.pin_edit)

        btns = QHBoxLayout()
        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self._accept_pin)
        btn_cancel = QPushButton("Anuluj")
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(btn_ok)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._elapsed = 0.0
        self._timer.start(500)

        if allow_pin:
            # drobna ergonomia: fokus w polu PIN
            self.pin_edit.setFocus()

    def _poll(self):
        token = self.reader.read_token(allow_pin=self.allow_pin)
        if token:
            self.token = token
            self.accept()
            return
        self._elapsed += 0.5
        if self._elapsed >= self.timeout:
            self.reject()

    def _accept_pin(self):
        if self.allow_pin:
            pin = self.pin_edit.text().strip()
            if pin:
                self.token = pin
        self.accept()

    @classmethod
    def ask(
        cls,
        reader: RFIDReader,
        *,
        allow_pin: bool = True,
        timeout: int = 10,
        parent=None,
    ) -> str | None:
        dlg = cls(reader, allow_pin=allow_pin, timeout=timeout, parent=parent)
        return dlg.token if dlg.exec() == QDialog.Accepted else None
