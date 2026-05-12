import re
from dataclasses import dataclass
from typing import Literal


SensitiveField = Literal["email", "phone", "bank_account", "address"]

SENSITIVE_FIELD_LABELS: dict[SensitiveField, str] = {
    "email": "Email addresses",
    "phone": "Phone numbers",
    "bank_account": "Bank account details",
    "address": "Addresses",
}

SENSITIVE_FIELD_ORDER: tuple[SensitiveField, ...] = ("email", "phone", "bank_account", "address")

_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)

_PHONE_PATTERN = re.compile(
    r"(?<![\w])(?:\+?\d{1,3}[\s.-]?)?(?:\d{10}|\d{5}[\s.-]?\d{5}|(?:\(?\d{2,5}\)?[\s.-]?)?\d{3,5}[\s.-]?\d{4})(?![\w])"
)

_BANK_PATTERNS = [
    re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b", re.IGNORECASE),
    re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b", re.IGNORECASE),
    re.compile(
        r"\b(?:account|acct|a/c|iban|routing|sort code|swift|bic|ifsc|bank)\b[^\n\r]{0,40}?\b[A-Z0-9][A-Z0-9 -]{5,34}\b",
        re.IGNORECASE,
    ),
]

_ADDRESS_KEYWORD_PATTERN = re.compile(
    r"\b(?:address|addr|street|st\.?|road|rd\.?|avenue|ave\.?|lane|ln\.?|drive|dr\.?|"
    r"boulevard|blvd\.?|floor|suite|unit|apartment|apt\.?|building|block|sector|phase|"
    r"city|state|zip|postal|postcode|pin code|pincode)\b",
    re.IGNORECASE,
)

_ADDRESS_LINE_PATTERN = re.compile(
    r"(?:\b\d{1,6}\b.*\b(?:street|st\.?|road|rd\.?|avenue|ave\.?|lane|ln\.?|drive|dr\.?|"
    r"boulevard|blvd\.?|floor|suite|unit|apartment|apt\.?|building|block|sector|phase)\b)"
    r"|(?:\b(?:zip|postal|postcode|pin code|pincode)\b\s*[:#-]?\s*\d{5,6}\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SensitiveTextMatch:
    value: str
    field: SensitiveField

    @property
    def label(self) -> str:
        return SENSITIVE_FIELD_LABELS[self.field]


def normalize_sensitive_fields(values: list[str] | tuple[str, ...] | None) -> list[SensitiveField]:
    if not values:
        return []

    allowed = set(SENSITIVE_FIELD_ORDER)
    normalized: list[SensitiveField] = []
    for value in values:
        key = str(value).strip().lower().replace("-", "_").replace(" ", "_")
        if key in allowed and key not in normalized:
            normalized.append(key)  # type: ignore[arg-type]
    return normalized


def parse_sensitive_fields(value: str) -> list[SensitiveField]:
    parts = re.split(r"[\s,;|]+", value.strip()) if value.strip() else []
    return normalize_sensitive_fields(parts)


def find_sensitive_text_matches(text: str, fields: list[SensitiveField]) -> list[SensitiveTextMatch]:
    matches: list[SensitiveTextMatch] = []
    selected = set(fields)

    if "email" in selected:
        matches.extend(SensitiveTextMatch(match.group(0), "email") for match in _EMAIL_PATTERN.finditer(text))

    if "phone" in selected:
        matches.extend(_find_phone_matches(text))

    if "bank_account" in selected:
        matches.extend(_find_bank_matches(text))

    if "address" in selected:
        matches.extend(_find_address_matches(text))

    return _dedupe_matches(matches)


def replace_sensitive_text(text: str, fields: list[SensitiveField], replacement_text: str) -> tuple[str, list[str]]:
    labels: list[str] = []
    updated = text
    for match in sorted(find_sensitive_text_matches(text, fields), key=lambda item: len(item.value), reverse=True):
        updated, count = re.subn(re.escape(match.value), replacement_text, updated, flags=re.IGNORECASE)
        labels.extend(match.label for _ in range(count))
    return updated, labels


def _find_phone_matches(text: str) -> list[SensitiveTextMatch]:
    matches: list[SensitiveTextMatch] = []
    for match in _PHONE_PATTERN.finditer(text):
        value = match.group(0).strip()
        digits = re.sub(r"\D", "", value)
        if 10 <= len(digits) <= 15 and _looks_like_phone(value):
            matches.append(SensitiveTextMatch(value, "phone"))
    return matches


def _find_bank_matches(text: str) -> list[SensitiveTextMatch]:
    matches: list[SensitiveTextMatch] = []
    for pattern in _BANK_PATTERNS:
        matches.extend(SensitiveTextMatch(match.group(0).strip(), "bank_account") for match in pattern.finditer(text))
    return matches


def _find_address_matches(text: str) -> list[SensitiveTextMatch]:
    matches: list[SensitiveTextMatch] = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip(" ,;")
        if len(line) < 12 or len(line) > 180:
            continue
        if _ADDRESS_LINE_PATTERN.search(line) or (_ADDRESS_KEYWORD_PATTERN.search(line) and re.search(r"\d", line)):
            matches.append(SensitiveTextMatch(line, "address"))
    return matches


def _looks_like_phone(value: str) -> bool:
    return bool(re.search(r"[+().-]|\s", value)) or len(re.sub(r"\D", "", value)) == 10


def _dedupe_matches(matches: list[SensitiveTextMatch]) -> list[SensitiveTextMatch]:
    seen: set[tuple[str, str]] = set()
    result: list[SensitiveTextMatch] = []
    for match in matches:
        key = (match.value.lower(), match.field)
        if key not in seen:
            seen.add(key)
            result.append(match)
    return result
