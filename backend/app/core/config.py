from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "local-academic-ai-assistant"
    app_host: str = "127.0.0.1"
    app_port: int = 4000
    cors_allow_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    data_root: str = "backend/data"
    catalog_dir: str = "backend/data/catalog"
    uploads_dir: str = "backend/data/uploads"
    runtime_dir: str = "backend/data/runtime"

    sqlite_path: str = "backend/data/runtime/chatbot.db"

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_chat_model: str = "qwen2.5:7b-instruct"
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_timeout_seconds: int = 120

    max_chunk_chars: int = 1400
    chunk_overlap_chars: int = 180
    retrieval_top_k: int = 6
    retrieval_min_score: float = 0.12
    max_history_messages: int = 14

    upload_max_bytes: int = 25 * 1024 * 1024
    startup_index_catalog: bool = False
    admin_password: str = "change_me_now"
    url_ingest_timeout_seconds: int = 20
    url_ingest_max_chars: int = 400000
    google_sheets_service_account_file: str = ""
    google_sheets_service_account_json: str = ""
    google_sheets_api_timeout_seconds: int = 20

    @property
    def project_root_path(self) -> Path:
        return PROJECT_ROOT

    def resolve_path(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return (self.project_root_path / path).resolve()

    @property
    def data_root_path(self) -> Path:
        return self.resolve_path(self.data_root)

    @property
    def catalog_dir_path(self) -> Path:
        return self.resolve_path(self.catalog_dir)

    @property
    def uploads_dir_path(self) -> Path:
        return self.resolve_path(self.uploads_dir)

    @property
    def runtime_dir_path(self) -> Path:
        return self.resolve_path(self.runtime_dir)

    @property
    def sqlite_path_resolved(self) -> Path:
        return self.resolve_path(self.sqlite_path)

    @property
    def cors_origins(self) -> list[str]:
        raw = (self.cors_allow_origins or "").strip()
        if not raw:
            return []
        return [part.strip() for part in raw.split(",") if part.strip()]

    @property
    def google_sheets_credentials_configured(self) -> bool:
        return bool(self.google_sheets_service_account_file.strip() or self.google_sheets_service_account_json.strip())


settings = Settings()


def ensure_data_dirs() -> None:
    settings.data_root_path.mkdir(parents=True, exist_ok=True)
    settings.catalog_dir_path.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir_path.mkdir(parents=True, exist_ok=True)
    settings.runtime_dir_path.mkdir(parents=True, exist_ok=True)
    settings.sqlite_path_resolved.parent.mkdir(parents=True, exist_ok=True)
