from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Supplier Redaction API"
    data_dir: Path = Path("data")
    output_dir: Path = Path("data/outputs")
    upload_dir: Path = Path("data/uploads")
    redact_all_images: bool = False
    redact_header_footer_images: bool = True
    use_openai_extraction: bool = False
    openai_model: str = "gpt-5.4-mini"
    use_tesseract_ocr: bool = True
    tesseract_cmd: str | None = None
    ocr_mode: str = "auto"
    ocr_dpi: int = 220
    ocr_min_confidence: int = 45
    native_text_min_chars: int = 80
    azure_document_intelligence_endpoint: str | None = None
    azure_document_intelligence_key: str | None = None
    redaction_api_url: str = "http://127.0.0.1:8000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    return settings
