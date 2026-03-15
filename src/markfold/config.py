from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_prefix="MARKFOLD_",
        extra="ignore",
    )

    app_name: str = "MarkFold"
    debug: bool = False
    database_url: str = "sqlite:///data/markfold.db"
    vault_root: Path = Field(default=PROJECT_ROOT / "vault")
    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = None
    openai_model: str | None = None
    feishu_app_id: str | None = None
    feishu_app_secret: SecretStr | None = None
    feishu_base_url: str = "https://open.feishu.cn"
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    @property
    def work_items_dir(self) -> Path:
        return self.vault_root / "work-items"

    @property
    def attachments_dir(self) -> Path:
        return self.vault_root / "attachments"

    @property
    def database_path(self) -> Path | None:
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix) or self.database_url.endswith(":memory:"):
            return None
        raw_path = Path(self.database_url[len(prefix) :])
        if raw_path.is_absolute():
            return raw_path
        return PROJECT_ROOT / raw_path

    def ensure_directories(self) -> None:
        if not self.vault_root.is_absolute():
            self.vault_root = PROJECT_ROOT / self.vault_root
        self.vault_root.mkdir(parents=True, exist_ok=True)
        self.work_items_dir.mkdir(parents=True, exist_ok=True)
        self.attachments_dir.mkdir(parents=True, exist_ok=True)
        database_path = self.database_path
        if database_path is not None:
            database_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
