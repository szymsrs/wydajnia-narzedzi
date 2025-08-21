from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout


class RFIDPrompt(QDialog):
    """Modal z komunikatem 'Przyłóż kartę/PIN'."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle("Przyłóż kartę/PIN")
        layout = QVBoxLayout(self)
        lbl = QLabel("Przyłóż kartę lub wpisz PIN")
        lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl)

