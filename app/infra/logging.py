# app/infra/logging.py
from __future__ import annotations
import logging, logging.config, os, sys, threading, traceback
from datetime import datetime
from pathlib import Path

# ── Kontekst wątku (użytkownik/stanowisko) ─────────────────────────────────────
_ctx = threading.local()
_ctx.user = "-"
_ctx.station = "-"

def set_station(station: str | None):
    _ctx.station = (station or "-").strip() or "-"

def set_user(full_name: str | None):
    _ctx.user = (full_name or "-").strip() or "-"

class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.user = getattr(_ctx, "user", "-")
        record.station = getattr(_ctx, "station", "-")
        return True

# ── Hook na nieobsłużone wyjątki ───────────────────────────────────────────────
def _excepthook(exc_type, exc, tb):
    logger = logging.getLogger("app")
    logger.critical("UNCAUGHT EXCEPTION",
                    exc_info=(exc_type, exc, tb))
    # zachowaj dotychczasowe zachowanie (stderr + exit code)
    sys.__excepthook__(exc_type, exc, tb)

# ── Konfiguracja logowania ────────────────────────────────────────────────────
def setup_logging(app_name: str, station: str | None = None) -> dict:
    """
    Inicjuje:
      - logs/app.log            (Rotating 5 MB x 10 plików)
      - logs/app-YYYYMMDD_HHMMSS_STAN.log  (log sesyjny)
    Zwraca dict z użytecznymi ścieżkami.
    """
    logs_dir = Path(__file__).resolve().parents[2] / "logs"
    os.makedirs(logs_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    station_norm = (station or "UNKNOWN").replace(os.sep, "_")
    session_log = logs_dir / f"{app_name.lower().replace(' ', '-')}-{ts}-{station_norm}.log"
    main_log = logs_dir / "app.log"

    fmt = "%(asctime)s|%(levelname)s|%(user)s|%(station)s|%(name)s|%(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "ctx": {"()": ContextFilter},
        },
        "formatters": {
            "std": {"format": fmt, "datefmt": datefmt},
        },
        "handlers": {
            "rotating": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "INFO",
                "filename": str(main_log),
                "maxBytes": 5 * 1024 * 1024,
                "backupCount": 10,
                "encoding": "utf-8",
                "formatter": "std",
                "filters": ["ctx"],
            },
            "session": {
                "class": "logging.FileHandler",
                "level": "DEBUG",
                "filename": str(session_log),
                "encoding": "utf-8",
                "formatter": "std",
                "filters": ["ctx"],
            },
            # w dev możesz odkomentować konsolę:
            # "console": {
            #     "class": "logging.StreamHandler",
            #     "level": "DEBUG",
            #     "stream": "ext://sys.stdout",
            #     "formatter": "std",
            #     "filters": ["ctx"],
            # },
        },
        "loggers": {
            "": {  # root
                "level": "INFO",
                "handlers": ["rotating", "session"],
            },
            "sqlalchemy": {
                "level": "WARNING",  # podbij do INFO przy debugowaniu SQL
                "handlers": ["rotating", "session"],
                "propagate": False,
            },
            "app": {
                "level": "DEBUG",
                "handlers": ["rotating", "session"],
                "propagate": False,
            },
        },
    })

    # ustaw wstępny kontekst
    set_station(station)
    set_user("-")

    # globalny hook na wyjątki
    sys.excepthook = _excepthook

    logging.getLogger("app").info("Start aplikacji")
    return {"main_log": str(main_log), "session_log": str(session_log), "logs_dir": str(logs_dir)}
