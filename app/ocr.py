import re
from dataclasses import dataclass
from pathlib import Path

import fitz
import pytesseract
from PIL import Image
from pytesseract import Output, TesseractNotFoundError

from app.config import get_settings


@dataclass(frozen=True)
class OcrWord:
    text: str
    page: int
    rect: fitz.Rect
    confidence: int


@dataclass(frozen=True)
class OcrPage:
    page: int
    text: str
    words: list[OcrWord]


@dataclass(frozen=True)
class OcrResult:
    pages: list[OcrPage]
    warnings: list[str]

    @property
    def text(self) -> str:
        return "\n".join(page.text for page in self.pages)


def run_pdf_ocr(path: Path) -> OcrResult:
    settings = get_settings()
    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

    warnings: list[str] = []
    pages: list[OcrPage] = []
    zoom = settings.ocr_dpi / 72

    try:
        doc = fitz.open(path)
        for page_index, page in enumerate(doc):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            data = pytesseract.image_to_data(image, output_type=Output.DICT)
            words = _read_words(data, page_index + 1, zoom, settings.ocr_min_confidence)
            pages.append(OcrPage(page=page_index + 1, text=_join_ocr_text(words), words=words))
        doc.close()
    except TesseractNotFoundError:
        warnings.append(
            "Tesseract OCR is not installed or is not on PATH. Install it and set TESSERACT_CMD if needed."
        )
    return OcrResult(pages=pages, warnings=warnings)


def find_ocr_name_rects(ocr_pages: list[OcrPage], supplier_names: list[str]) -> list[tuple[int, fitz.Rect, str]]:
    matches: list[tuple[int, fitz.Rect, str]] = []
    for page in ocr_pages:
        normalized_words = [_normalize_token(word.text) for word in page.words]
        for name in supplier_names:
            name_tokens = [_normalize_token(token) for token in name.split()]
            name_tokens = [token for token in name_tokens if token]
            if not name_tokens:
                continue
            for index in range(0, len(normalized_words) - len(name_tokens) + 1):
                if normalized_words[index : index + len(name_tokens)] == name_tokens:
                    rect = page.words[index].rect
                    for word in page.words[index + 1 : index + len(name_tokens)]:
                        rect = rect | word.rect
                    matches.append((page.page, _pad_rect(rect, 1.5), name))
    return matches


def _read_words(data: dict, page_number: int, zoom: float, min_confidence: int) -> list[OcrWord]:
    words: list[OcrWord] = []
    total = len(data.get("text", []))
    for index in range(total):
        text = str(data["text"][index]).strip()
        if not text:
            continue
        try:
            confidence = int(float(data["conf"][index]))
        except (TypeError, ValueError):
            confidence = -1
        if confidence < min_confidence:
            continue
        x = data["left"][index] / zoom
        y = data["top"][index] / zoom
        width = data["width"][index] / zoom
        height = data["height"][index] / zoom
        words.append(
            OcrWord(
                text=text,
                page=page_number,
                rect=fitz.Rect(x, y, x + width, y + height),
                confidence=confidence,
            )
        )
    return words


def _join_ocr_text(words: list[OcrWord]) -> str:
    lines: list[str] = []
    current: list[str] = []
    previous_y: float | None = None
    for word in words:
        if previous_y is not None and abs(word.rect.y0 - previous_y) > 8:
            lines.append(" ".join(current))
            current = []
        current.append(word.text)
        previous_y = word.rect.y0
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)


def _normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9&]+", "", value.lower())


def _pad_rect(rect: fitz.Rect, amount: float) -> fitz.Rect:
    return fitz.Rect(rect.x0 - amount, rect.y0 - amount, rect.x1 + amount, rect.y1 + amount)
