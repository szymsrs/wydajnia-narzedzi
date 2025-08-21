# app/main.py
from __future__ import annotations
from pathlib import Path
import sys
from typing import Optional
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog
from PySide6.QtCore import QTimer
from PySide6.QtGui import QShortcut, QKeySequence

# pozwala uruchamiać main.py bezpośrednio (Run Python File)
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.infra.logging import setup_logging
from app.ui.shell import MainWindow, apply_theme
from app.infra.config import load_settings
from app.dal.db import make_conn_str, create_engine_and_session, ping
from app.ui.login_dialog import LoginDialog
from app.core.auth import AuthRepo  # repo do pracy modułów (np. Użytkownicy)

# ⬇️ Import naszego importera RW (nic więcej nie zmieniamy)
from app.services.rw.importer import import_rw_pdf


def _display_name(session: dict | None) -> str:
    """Ładna nazwa użytkownika do logów/UI."""
    if not session:
        return ""
    fn = (session.get("first_name") or "").strip()
    ln = (session.get("last_name") or "").strip()
    if fn or ln:
        return f"{fn} {ln}".strip()
    return session.get("name") or session.get("login") or ""


def _do_import_rw(parent_window, repo, operator_user_id: int, station_id: str, logs_dir: Path) -> None:
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
    debug_path = str((logs_dir / f"rw_import_{Path(pdf_path).stem}.log").resolve())

    try:
        result = import_rw_pdf(
            repo=repo,
            pdf_path=pdf_path,
            operator_user_id=operator_user_id,
            station=station_id,
            commit=True,                      # od razu wykonujemy (jak RW ma być „wydaniem”)
            item_mapping=None,                # opcjonalnie można tu przekazać mapowanie {sku: item_id}
            allow_create_missing=False,       # ustaw True, jeśli chcesz auto-dodawać brakujące SKU
            debug_path=debug_path,
        )
    except Exception as e:
        QMessageBox.critical(parent_window, "Import RW – błąd krytyczny", str(e))
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
            for it in items[:20]:  # nie zalewamy okna
                msg_lines.append(f"   - {it.get('sku_src')} | {it.get('name_src')} | {it.get('uom')} | qty={it.get('qty')}")
            if len(items) > 20:
                msg_lines.append(f"   ... i jeszcze {len(items)-20} pozycji")
        msg_lines.append(f"\nLog parsowania: {result.get('debug_path') or debug_path}")
        QMessageBox.warning(parent_window, "Import RW – potrzebne uzupełnienia", "\n".join(msg_lines))
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


def main():
    base_dir = Path(__file__).resolve().parents[1]
    log = setup_logging(base_dir / "logs")

    app = QApplication(sys.argv)

    # --- Wczytanie configu
    config_path = base_dir / "config" / "app.json"
    if not config_path.exists():
        QMessageBox.critical(
            None,
            "Błąd konfiguracji",
            f"Brak pliku: {config_path}\nUtwórz config/app.json na bazie app.json.example."
        )
        sys.exit(2)

    settings = load_settings(config_path)
    log.info(f"Start: {settings.app_name} na stanowisku {settings.workstation_id}")

    # --- Próba połączenia z DB
    engine = SessionLocal = None
    db_ok = False
    db_error = None
    try:
        conn_str = make_conn_str(
            settings.db.host, settings.db.port,
            settings.db.user, settings.db.password, settings.db.database
        )
        engine, SessionLocal = create_engine_and_session(conn_str)
        ping(engine)
        db_ok = True
        log.info("Połączenie z DB: OK")
    except Exception as e:
        db_error = str(e)
        log.exception("Błąd połączenia z DB – start w trybie offline")

    # --- Motyw UI
    apply_theme(settings.theme)

    # --- Inicjalizacja repo (przed logowaniem!)
    repo = None
    if db_ok:
        cfg = {
            "db": {
                "host": settings.db.host,
                "port": settings.db.port,
                "user": settings.db.user,
                "password": settings.db.password,
                "name": settings.db.database,
            }
        }
        try:
            repo = AuthRepo(cfg)
        except Exception as e:
            log.exception(f"Błąd inicjalizacji AuthRepo: {e}")
            repo = None

    # --- Logowanie (tylko gdy DB i repo gotowe)
    session_data = None
    if db_ok and repo:
        login_dlg = LoginDialog(repo=repo, station_id=settings.workstation_id)
        if login_dlg.exec() == LoginDialog.Accepted:
            session_data = login_dlg.session or {}
            name = _display_name(session_data)
            role = session_data.get("role", "")
            method = session_data.get("method", "unknown")
            log.info(f"Zalogowano: {name} ({role}) metodą {method}")
        else:
            log.info("Logowanie anulowane – zamykam aplikację.")
            sys.exit(0)

    # --- Uruchomienie głównego okna (jedno okno na całą sesję)
    win = MainWindow(
        settings.app_name,
        db_ok=db_ok,
        db_error=db_error,
        session=session_data,
        repo=repo,
    )

    # obsługa wylogowania → logowanie w TYM SAMYM oknie (bez tworzenia nowych okien)
    win.request_logout.connect(win.handle_logout)

    win.show()

    # komunikat o trybie offline
    if not db_ok and db_error:
        QTimer.singleShot(250, lambda: QMessageBox.warning(
            win,
            "Baza danych niedostępna",
            "Nie udało się połączyć z bazą danych.\n"
            "Aplikacja działa w trybie offline (tylko UI).\n\n"
            f"Szczegóły:\n{db_error}"
        ))

    # --- ⬇️ SKRÓT KLAWIATUROWY: Import RW (Ctrl+I) — tylko gdy DB i repo są dostępne
    if db_ok and repo and session_data:
        logs_dir = (base_dir / "logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        operator_id = int(session_data.get("user_id") or session_data.get("id") or 0)

        sc_import = QShortcut(QKeySequence("Ctrl+I"), win)
        sc_import.setWhatsThis("Import RW (PDF)")
        sc_import.activated.connect(
            lambda: _do_import_rw(
                parent_window=win,
                repo=repo,
                operator_user_id=operator_id,
                station_id=settings.workstation_id,
                logs_dir=logs_dir
            )
        )

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
