from loguru import logger
from pathlib import Path
import sys
import getpass


def setup_logging(log_dir: Path, level: str = "INFO", workstation: str | None = None):
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = "{time:YYYY-MM-DD HH:mm:ss}|{level}|{extra[os_user]}|{extra[workstation]}|{message}"
    logger.remove()
    logger.add(
        sys.stdout,
        level=level,
        enqueue=True,
        backtrace=False,
        diagnose=False,
        format=fmt,
    )
    logger.add(
        log_dir / "app.log",
        rotation="10 MB",
        retention="14 days",
        encoding="utf-8",
        level=level,
        enqueue=True,
        format=fmt,
    )
    return logger.bind(os_user=getpass.getuser(), workstation=workstation or "UNKNOWN")
