from loguru import logger
from pathlib import Path
import sys

def setup_logging(log_dir: Path, level: str = "INFO"):
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stdout, level=level, enqueue=True, backtrace=False, diagnose=False)
    logger.add(
        log_dir / "app.log",
        rotation="10 MB",
        retention="14 days",
        encoding="utf-8",
        level=level,
        enqueue=True,
    )
    return logger
