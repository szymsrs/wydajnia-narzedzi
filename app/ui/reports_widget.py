# app/ui/reports_widget.py
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QHBoxLayout, QDateEdit, QLabel,
    QPushButton, QComboBox, QLineEdit, QTableView, QMessageBox
)
from PySide6.QtCore import QDate
import logging

log = logging.getLogger(__name__)

from .table_model import SimpleTableModel


class ReportsWidget(QWidget):
    """
    Widżet raportów korzystający z ReportsRepo:
      - rw_summary(date_from, date_to, limit)
      - exceptions(date_from, date_to, employee_id?, item_id?, limit)
      - employees(q?, limit)
      - employee_card(employee_id, date_from, date_to)
    """
    def __init__(self, reports_repo, parent=None):
        super().__init__(parent)
        self.repo = reports_repo  # ReportsRepo

        self.tabs = QTabWidget(self)
        self._init_rw_tab()
        self._init_exceptions_tab()
        self._init_card_tab()

        lay = QVBoxLayout(self)
        lay.addWidget(self.tabs)

    # ---------- RW summary ----------
    def _init_rw_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)

        fl = QHBoxLayout()
        fl.addWidget(QLabel("Od:"))
        self.df = QDateEdit(QDate.currentDate().addMonths(-1))
        self.df.setCalendarPopup(True)
        fl.addWidget(self.df)

        fl.addWidget(QLabel("Do:"))
        self.dt = QDateEdit(QDate.currentDate().addDays(1))
        self.dt.setCalendarPopup(True)
        fl.addWidget(self.dt)

        btn = QPushButton("Odśwież")
        btn.clicked.connect(self._load_rw)
        fl.addWidget(btn)
        fl.addStretch()

        v.addLayout(fl)

        self.tbl_rw = QTableView()
        self.m_rw = SimpleTableModel()
        self.tbl_rw.setModel(self.m_rw)
        v.addWidget(self.tbl_rw)

        self.tabs.addTab(w, "Konsumpcja RW")
        self._load_rw()

    def _load_rw(self):
        d_from = self.df.date().toPython()
        d_to = self.dt.date().toPython()
        try:
            rows = self.repo.rw_summary(date_from=d_from, date_to=d_to, limit=500) or []
            self.m_rw.set_rows(rows)
        except Exception as e:
            log.exception("Błąd ładowania raportu RW df=%s dt=%s lim=%s", d_from, d_to, 500)
            QMessageBox.warning(self, "Błąd ładowania raportu RW", str(e))

    # ---------- Wyjątki ----------
    def _init_exceptions_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)

        fl = QHBoxLayout()
        fl.addWidget(QLabel("Od:"))
        self.df_exc = QDateEdit(QDate.currentDate().addMonths(-1))
        self.df_exc.setCalendarPopup(True)
        fl.addWidget(self.df_exc)

        fl.addWidget(QLabel("Do:"))
        self.dt_exc = QDateEdit(QDate.currentDate().addDays(1))
        self.dt_exc.setCalendarPopup(True)
        fl.addWidget(self.dt_exc)

        self.e_emp = QLineEdit()
        self.e_emp.setPlaceholderText("employee_id (opcjonalnie)")
        self.e_item = QLineEdit()
        self.e_item.setPlaceholderText("item_id (opcjonalnie)")

        btn = QPushButton("Odśwież")
        btn.clicked.connect(self._load_exc)

        for wid in (self.e_emp, self.e_item, btn):
            fl.addWidget(wid)
        fl.addStretch()
        v.addLayout(fl)

        self.tbl_exc = QTableView()
        self.m_exc = SimpleTableModel()
        self.tbl_exc.setModel(self.m_exc)
        v.addWidget(self.tbl_exc)

        self.tabs.addTab(w, "Wyjątki")
        self._load_exc()

    def _load_exc(self):
        d_from = self.df_exc.date().toPython()
        d_to = self.dt_exc.date().toPython()
        eid = int(self.e_emp.text()) if self.e_emp.text().strip().isdigit() else None
        iid = int(self.e_item.text()) if self.e_item.text().strip().isdigit() else None
        try:
            rows = self.repo.exceptions(
                date_from=d_from,
                date_to=d_to,
                employee_id=eid,
                item_id=iid,
                limit=500,
            ) or []
            desired_cols = (
                "operation_uuid",
                "employee_id",
                "item_id",
                "quantity",
                "created_at",
                "movement_type",
                "reason",
            )
            rows = [
                {col: row.get(col) for col in desired_cols}
                for row in rows
            ]
            self.m_exc.set_rows(rows)
        except Exception as e:
            log.exception(
                "Błąd ładowania wyjątków df=%s dt=%s emp=%s itm=%s lim=%s",
                d_from, d_to, eid, iid, 500,
            )
            QMessageBox.warning(self, "Błąd ładowania wyjątków", str(e))

    # ---------- Karta pracownika ----------
    def _init_card_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)

        top = QHBoxLayout()
        self.cb_emp = QComboBox()

        q = ""
        limit = 200
        try:
            emps = self.repo.employees(q=q, limit=limit) or []
        except Exception as e:
            log.exception("Błąd ładowania pracowników q=%r lim=%s", q, limit)
            emps = []
            QMessageBox.warning(self, "Błąd ładowania pracowników", str(e))

        self.cb_emp.addItems([
            f"{e.get('last_name','')} {e.get('first_name','')} (id={e.get('id','?')})"
            for e in emps
        ])
        self._emp_ids = [e.get("id") for e in emps]

        fl_dates = QHBoxLayout()
        fl_dates.addWidget(QLabel("Od:"))
        self.df_card = QDateEdit(QDate.currentDate().addMonths(-1))
        self.df_card.setCalendarPopup(True)
        fl_dates.addWidget(self.df_card)

        fl_dates.addWidget(QLabel("Do:"))
        self.dt_card = QDateEdit(QDate.currentDate().addDays(1))
        self.dt_card.setCalendarPopup(True)
        fl_dates.addWidget(self.dt_card)

        btn = QPushButton("Pokaż")
        btn.clicked.connect(self._load_card)

        top.addWidget(QLabel("Pracownik:"))
        top.addWidget(self.cb_emp)
        top.addWidget(btn)
        top.addStretch()

        v.addLayout(top)
        v.addLayout(fl_dates)

        self.tbl_card = QTableView()
        self.m_card = SimpleTableModel()
        self.tbl_card.setModel(self.m_card)
        v.addWidget(self.tbl_card)

        self.tabs.addTab(w, "Karta pracownika")
        if emps:
            self._load_card()

    def _load_card(self):
        idx = self.cb_emp.currentIndex()
        if idx < 0 or idx >= len(self._emp_ids):
            return
        emp_id = self._emp_ids[idx]
        d_from = self.df_card.date().toPython()
        d_to = self.dt_card.date().toPython()
        try:
            rows = self.repo.employee_card(employee_id=emp_id, date_from=d_from, date_to=d_to) or []
            rows = [
                {
                    'item_id': r.get('item_id'),
                    'balance_qty': r.get('balance_qty'),
                    'first_op': r.get('first_op'),
                    'last_op': r.get('last_op'),
                }
                for r in rows
            ]
            self.m_card.set_rows(rows)
        except Exception as e:
            log.exception("Błąd ładowania karty emp=%s df=%s dt=%s", emp_id, d_from, d_to)
            QMessageBox.warning(self, "Błąd ładowania karty", str(e))
