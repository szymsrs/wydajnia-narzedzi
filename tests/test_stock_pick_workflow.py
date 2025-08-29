import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

if "PySide6" in sys.modules:
    del sys.modules["PySide6"]
    sys.modules.pop("PySide6.QtWidgets", None)
    sys.modules.pop("PySide6.QtCore", None)

QtCore = pytest.importorskip("PySide6.QtCore")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from app.ui.stock_picker import StockPickerDialog
from app.ui import ops_issue_dialog
from app.ui.ops_issue_dialog import OpsIssueDialog


class DummyRepo:
    def search_stock(self, q: str, limit: int = 200):
        return [
            {
                "item_id": 1,
                "sku": "SKU1",
                "name": "Item 1",
                "uom": "szt",
                "qty_available": 10,
            }
        ]


def ensure_app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


def test_stock_picker_get_selected_returns_dict_with_qty():
    ensure_app()
    repo = DummyRepo()
    dlg = StockPickerDialog(repo)
    dlg.q.setText("SKU1")
    dlg._search()
    dlg.table.selectRow(0)
    dlg.qty.setText("3")
    selected = dlg.get_selected()
    assert selected is not None
    assert selected["item_id"] == 1
    assert selected["sku"] == "SKU1"
    assert selected["name"] == "Item 1"
    assert selected["uom"] == "szt"
    assert selected["qty"] == 3


def test_on_pick_from_stock_populates_table(monkeypatch):
    ensure_app()
    selection = {
        "item_id": 2,
        "sku": "SKU2",
        "name": "Item 2",
        "uom": "kg",
        "qty": 5,
    }

    class DummyPicker:
        def __init__(self, repo, parent):
            pass

        def exec(self):
            return QtWidgets.QDialog.Accepted

        def get_selected(self):
            return selection

    monkeypatch.setattr(ops_issue_dialog, "StockPickerDialog", DummyPicker)

    dlg = OpsIssueDialog(repo=DummyRepo())
    dlg.on_pick_from_stock()

    assert dlg.table.rowCount() == 1
    sku_item = dlg.table.item(0, 0)
    assert sku_item.text() == selection["sku"]
    assert sku_item.data(QtCore.Qt.UserRole) == selection["item_id"]
    assert dlg.table.item(0, 1).text() == selection["name"]
    assert dlg.table.item(0, 2).text() == selection["uom"]
    qty_edit = dlg.table.cellWidget(0, 3)
    assert isinstance(qty_edit, QtWidgets.QLineEdit)
    assert qty_edit.text() == str(selection["qty"])