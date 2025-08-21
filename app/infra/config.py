from __future__ import annotations
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import json
from pathlib import Path

class DBSettings(BaseModel):
    host: str
    port: int = 3306
    user: str
    password: str
    database: str

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WYD_", env_nested_delimiter="__")
    app_name: str = "Wydajnia Narzędzi"
    workstation_id: str
    theme: str = "dark"
    db: DBSettings
    alerts: dict = Field(default_factory=dict)

def load_settings(config_path: Path) -> AppSettings:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return AppSettings(**data)
