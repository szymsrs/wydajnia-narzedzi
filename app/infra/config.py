# app/infra/config.py
from __future__ import annotations
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import json
from pathlib import Path
from PySide6.QtWidgets import QMessageBox


class DBSettings(BaseModel):
    host: str
    port: int = 3306
    user: str
    password: str
    database: str


class FeaturesSettings(BaseModel):
    import_rw_pdf: bool = False
    rfid_required: bool = False
    pin_fallback: bool = True   # <- NOWE
    exceptions_panel: bool = False


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WYD_", env_nested_delimiter="__")
    app_name: str = "Wydajnia Narzędzi"
    workstation_id: str
    theme: str = "dark"
    db: DBSettings
    alerts: dict = Field(default_factory=dict)
    features: FeaturesSettings = Field(default_factory=FeaturesSettings)


def load_settings(config_path: Path) -> AppSettings:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return AppSettings(**data)


def load_app_config(base_dir: Path) -> AppSettings:
    """Load application configuration from ``config/app.json``.

    Args:
        base_dir: Root directory of the project.

    Raises:
        FileNotFoundError: If the configuration file does not exist.

    Returns:
        Parsed :class:`AppSettings` instance.
    """
    config_path = base_dir / "config" / "app.json"
    if not config_path.exists():
        QMessageBox.critical(
            None,
            "Brak konfiguracji",
            f"Nie znaleziono pliku konfiguracyjnego: {config_path}",
        )
        raise FileNotFoundError(f"Brak pliku: {config_path}")
    return load_settings(config_path)
