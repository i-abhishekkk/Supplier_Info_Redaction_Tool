from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class RedactionOptions(BaseModel):
    supplier_names: list[str] = Field(default_factory=list)
    detect_supplier_names: bool = False
    use_llm_extraction: bool | None = None
    use_ocr: bool | None = None
    redact_all_images: bool = False
    redact_header_footer_images: bool = True
    replacement_text: str = "REDACTED"


class RedactionHit(BaseModel):
    kind: Literal["text", "image"]
    page: int | None = None
    value: str | None = None
    reason: str


class RedactionResult(BaseModel):
    input_path: Path
    output_path: Path
    media_type: str
    hits: list[RedactionHit]
    supplier_names: list[str]
    extraction_sources: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    download_url: str | None = None
