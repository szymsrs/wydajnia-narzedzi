# app/main.py
from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

# pozwala uruchamiać main.py bezpośrednio (Run Python File)
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.auth import AuthRepo  # noqa: E402
from app.core.rfid_stub import RFIDReader  # noqa: E402
from app.dal.db import create_engine_and_session, ping  # noqa: E402
from app.infra.config import load_settings  # noqa: E402
from app.infra.logging import (  # noqa: E402
    set_station,
    set_user,
    setup_logging,
)
from app.repo.reports_repo import ReportsRepo  # noqa: E402
from app.services.rw.importer import import_rw_pdf  # noqa: E402
from app.ui.login_dialog import LoginDialog  # noqa: E402
from app.ui.shell import MainWindow, apply_theme  # noqa: E402

log = logging.getLogger(__name__)


def _display_name(session: dict | None) -> str:
    """Ładna nazwa użytkownika do logów/UI."""
    if not session:
        return ""
    fn = (session.get("first_name") or "").strip()
    ln = (session.get("last_name") or "").strip()
    if fn or ln:
        return f"{fn} {ln}".strip()
    return session.get("name") or session.get("login") or ""


def _do_import_rw(
    parent_window, repo, operator_user_id: int, station_id: str, logs_dir: Path
) -> None:
    """
    Minimalny workflow:
     - wybór pliku PDF
     - import RW przez app.services.rw.importer.import_rw_pdf
     - komunikaty o brakach / sukcesie
    """
    dlg = QFileDialog(parent_window)
    dlg.setWindowTitle("Wybierz plik RW (PDF)")
    dlg.setFileMode(QFileDialog.ExistingFile)
    dlg.setNameFilter("Dokumenty RW (*.pdf)")
    if not dlg.exec():
        return
    files = dlg.selectedFiles()
    if not files:
        return

    pdf_path = files[0]
    debug_path = str(
        (logs_dir / f"rw_import_{Path(pdf_path).stem}.log").resolve()
    )  # noqa: E501

    try:
        log.info("Start importu RW: %s", pdf_path)
        result = import_rw_pdf(
            repo=repo,
            pdf_path=pdf_path,
            operator_user_id=operator_user_id,
            station=station_id,
            commit=True,  # od razu wykonujemy (jak RW ma być „wydaniem”)
            item_mapping=None,  # opcjonalnie: mapowanie {sku: item_id}
            # ustaw True, jeśli chcesz auto-dodawać brakujące SKU
            allow_create_missing=False,
            debug_path=debug_path,
        )
    except Exception as e:
        log.exception("Import RW – błąd krytyczny")
        QMessageBox.critical(
            parent_window,
            "Import RW – błąd krytyczny",
            str(e),
        )
        return

    # Obsługa braków (pracownik / pozycje)
    if not result.get("ok"):
        need = result.get("need", {})
        msg_lines = ["Import RW wymaga uzupełnień:"]
        if "employee" in need:
            hint = (need["employee"].get("hint") or "").strip()
            cand = need["employee"].get("candidates") or []
            msg_lines.append(f"• Pracownik: hint='{hint}'")
            if cand:
                msg_lines.append("  Kandydaci:")
                for c in cand:
                    fn = c.get("first_name", "")
                    ln = c.get("last_name", "")
                    msg_lines.append(f"   - {fn} {ln} (id={c.get('id')})")
            else:
                msg_lines.append("  (brak kandydatów)")
        if "items" in need:
            items = need["items"] or []
            msg_lines.append("• Pozycje bez mapowania SKU → item_id:")
            for it in items[:20]:
                msg_lines.append(
                    f"   - {it.get('sku_src')} | {it.get('name_src')} | {it.get('uom')} | "  # noqa: E501
                    f"qty={it.get('qty')}"
                )
            if len(items) > 20:
                msg_lines.append(f"   ... i jeszcze {len(items)-20} pozycji")
        msg_lines.append(
            f"\nLog parsowania: {result.get('debug_path') or debug_path}"
        )  # noqa: E501
        QMessageBox.warning(
            parent_window,
            "Import RW – potrzebne uzupełnienia",
            "\n".join(msg_lines),
        )
        return

    # Sukces
    rw = result.get("rw", {}) or {}
    info = [
        "Import RW zakończony.",
        f"Nr: {rw.get('no') or '-'}",
        f"Data: {rw.get('date') or '-'}",
        f"Operacja UUID: {result.get('op_uuid') or '-'}",
        f"Log parsowania: {result.get('debug_path') or debug_path}",
    ]
    QMessageBox.information(parent_window, "Import RW – OK", "\n".join(info))
    log.info("Import RW zakończony powodzeniem")


def main():
    base_dir = Path(__file__).resolve().parents[1]

    app = QApplication(sys.argv)

    # --- Wczytanie configu
    config_path = base_dir / "config" / "app.json"
    if not config_path.exists():
        QMessageBox.critical(
            None,
            "Błąd konfiguracji",
            (
                f"Brak pliku: {config_path}\n"
                "Utwórz config/app.json na bazie app.json.example."
            ),
        )
        sys.exit(2)

    settings = load_settings(config_path)
    setup_logging(
        app_name="Wydajnia Narzędzi",
        station=settings.workstation_id or "UNKNOWN",
        capture_qt=True,
        capture_prints=False,
        console=False,
    )
    # Globalny hook wyjątków z GUI/slotów – zapis do logów
    def _excepthook(exctype, value, tb):
        try:
            log.critical("UNHANDLED EXCEPTION", exc_info=(exctype, value, tb))
        except Exception:
            pass
    sys.excepthook = _excepthook
    set_station(settings.workstation_id)
    log.info(
        "Start: %s na stanowisku %s",
        settings.app_name,
        settings.workstation_id,
    )

    # --- Inicjalizacja repo / połączenie z DB (healthcheck przez SELECT 1)
    repo = None
    reports_repo = None
    db_ok = False
    db_error = None
    try:
        # Konfiguracja DB dla create_engine_and_session
        # (bezpieczne URL.create pod spodem)
        cfg = {
            "db": {
                "host": settings.db.host,
                "port": settings.db.port,
                "user": settings.db.user,
                "password": settings.db.password,
                "database": settings.db.database,
            }
        }
        engine, _ = create_engine_and_session(cfg, log_sql=settings.log_sql)
        ping(engine)  # SELECT 1
        repo = AuthRepo(cfg)
        reports_repo = ReportsRepo(engine)  # <-- tworzymy repo raportów
        db_ok = True
        log.info("Połączenie z DB: OK")
    except Exception as e:
        db_error = str(e)
        log.error("Błąd połączenia z DB – start w trybie offline", exc_info=e)

    # --- Motyw UI
    apply_theme(settings.theme)

    # --- Logowanie (tylko gdy DB i repo gotowe)
    session_data = None
    if db_ok and repo:
        login_dlg = LoginDialog(repo=repo, station_id=settings.workstation_id)
        if login_dlg.exec() == LoginDialog.Accepted:
            session_data = login_dlg.session or {}
            name = _display_name(session_data)
            role = session_data.get("role", "")
            method = session_data.get("method", "unknown")
            set_user(name)
            log.info(f"Zalogowano: {name} ({role}) metodą {method}")
        else:
            log.info("Logowanie anulowane – zamykam aplikację.")
            sys.exit(0)

    # --- Utwórz czytnik RFID/PIN (stub) i przekaż do okna głównego
    rfid_reader = RFIDReader()

    # --- Uruchomienie głównego okna
    win = MainWindow(
        settings.app_name,
        db_ok=db_ok,
        db_error=db_error,
        session=session_data,
        repo=repo,  # AuthRepo
        reports_repo=reports_repo,  # <-- przekazujemy ReportsRepo do UI
        settings=settings,  # konfiguracja do UI
        rfid_reader=rfid_reader,  # stub czytnika
    )
    win.request_logout.connect(win.handle_logout)
    win.show()

    # komunikat o trybie offline
    if not db_ok and db_error:
        QTimer.singleShot(
            250,
            lambda: QMessageBox.warning(
                win,
                "Baza danych niedostępna",
                "Nie udało się połączyć z bazą danych.\n"
                "Aplikacja działa w trybie offline (tylko UI).\n\n"
                f"Szczegóły:\n{db_error}",
            ),
        )

    # --- ⬇️ Skrót: Import RW (Ctrl+I) — tylko gdy DB i repo są dostępne
    if db_ok and repo and session_data:
        logs_dir = base_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        operator_id = int(
            session_data.get("user_id") or session_data.get("id") or 0
        )  # noqa: E501

        sc_import = QShortcut(QKeySequence("Ctrl+I"), win)
        sc_import.setWhatsThis("Import RW (PDF)")
        sc_import.activated.connect(
            lambda: _do_import_rw(
                parent_window=win,
                repo=repo,
                operator_user_id=operator_id,
                station_id=settings.workstation_id,
                logs_dir=logs_dir,
            )
        )

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
