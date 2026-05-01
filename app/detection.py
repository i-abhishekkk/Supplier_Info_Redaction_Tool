import json
import os
import re
from collections import Counter


LEGAL_SUFFIX_PATTERN = (
    r"(?:Inc\.?|INC\.?|Incorporated|INCORPORATED|Corp\.?|CORP\.?|Corporation|CORPORATION|"
    r"Company|COMPANY|Co\.?|CO\.?|LLC|L\.L\.C\.|Ltd\.?|LTD\.?|Limited|LIMITED|"
    r"LLP|L\.L\.P\.|LP|L\.P\.|PLC|Pvt\.?\s+Ltd\.?|Private\s+Limited)"
)

ENTITY_PATTERN = re.compile(
    rf"\b([A-Z][A-Za-z0-9&.,' -]{{2,90}}\s+{LEGAL_SUFFIX_PATTERN})\b",
)

PARTY_PATTERN = re.compile(
    r"\b(?:between|by and between|seller|buyer|supplier|vendor|contractor|assignor|assignee|client|customer)\s+"
    r"(?:is\s+|:?\s*)([A-Z][A-Za-z0-9&.,' -]{2,90}\s+"
    rf"{LEGAL_SUFFIX_PATTERN})\b",
)

NOISE_WORDS = {
    "agreement",
    "assignment",
    "amendment",
    "exhibit",
    "schedule",
    "section",
    "document",
    "printed",
    "including",
    "such",
    "scope",
    "costs",
    "attachments",
    "documents",
    "laws",
    "rights",
    "purchase",
    "receivables",
}


def normalize_name(value: str) -> str:
    value = re.sub(r"\s+", " ", value.strip(" \t\r\n,;:()[]{}"))
    return value


def parse_supplier_names(value: str) -> list[str]:
    raw_parts = re.split(
        rf"[\r\n;]+|,\s+(?!{LEGAL_SUFFIX_PATTERN}\b)",
        value,
        flags=re.IGNORECASE,
    )
    return [name for part in raw_parts if (name := normalize_name(part))]


def extract_supplier_candidates(text: str, max_candidates: int = 20) -> list[str]:
    candidates: list[str] = []
    for pattern in (ENTITY_PATTERN, PARTY_PATTERN):
        for match in pattern.finditer(text):
            candidate = normalize_name(match.group(1))
            if _looks_like_name(candidate):
                candidates.append(candidate)

    counts = Counter(candidates)
    ranked = sorted(counts, key=lambda item: (-counts[item], len(item), item.lower()))
    return ranked[:max_candidates]


def merge_supplier_names(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for group in groups:
        for value in group:
            for name in expand_supplier_name_variants(value):
                key = _dedupe_key(name)
                if name and key not in seen:
                    seen.add(key)
                    merged.append(name)
    return merged


def expand_supplier_name_variants(value: str) -> list[str]:
    name = normalize_name(value)
    if not name:
        return []

    variants: list[str] = [name]
    parts = [
        normalize_name(part)
        for part in re.split(r"\s+(?:and|&|\|)\s+", name, flags=re.IGNORECASE)
        if normalize_name(part)
    ]
    if len(parts) > 1:
        variants.extend(parts)

    for candidate in list(variants):
        variants.extend(_legal_suffix_variants(candidate))

    seen: set[str] = set()
    result: list[str] = []
    for variant in variants:
        key = _dedupe_key(variant)
        if key not in seen:
            seen.add(key)
            result.append(variant)
    return result


def _legal_suffix_variants(name: str) -> list[str]:
    variants: list[str] = []
    if re.search(r"\bL\.?L\.?C\.?$", name, flags=re.IGNORECASE):
        stem = re.sub(r",?\s+L\.?L\.?C\.?$", "", name, flags=re.IGNORECASE)
        variants.extend([f"{stem} LLC", f"{stem}, LLC", f"{stem} L.L.C."])
    if re.search(r"\bCompany$", name, flags=re.IGNORECASE):
        variants.extend([f"{name} LLC", f"{name}, LLC", f"{name} L.L.C."])
    if re.search(r"\bInc\.?$", name, flags=re.IGNORECASE):
        stem = re.sub(r",?\s+Inc\.?$", "", name, flags=re.IGNORECASE)
        variants.extend([f"{stem} Inc", f"{stem}, Inc.", f"{stem} Incorporated"])
    return [normalize_name(variant) for variant in variants]


def _dedupe_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip(" ,;:()[]{}")


def _looks_like_name(candidate: str) -> bool:
    words = [word.lower().strip(".,") for word in candidate.split()]
    if len(candidate) < 4 or len(words) > 14:
        return False
    if any(word in NOISE_WORDS for word in words[:2]):
        return False
    return any(word[:1].isalpha() for word in words)


async def extract_with_openai(text: str, model: str) -> list[str]:
    if not os.getenv("OPENAI_API_KEY"):
        return []

    from openai import AsyncOpenAI

    client = AsyncOpenAI()
    excerpt = text[:24000]
    prompt = (
        "Extract supplier, vendor, bidder, contractor, seller, assignor, assignee, buyer, "
        "customer, and named legal party organization names from this tender or contract text. "
        "Return only JSON with a supplier_names array of strings. Do not include people, dates, "
        "addresses, agreement titles, or generic role labels.\n\n"
        f"{excerpt}"
    )
    response = await client.responses.create(
        model=model,
        input=prompt,
        text={"format": {"type": "json_object"}},
    )
    try:
        payload = json.loads(response.output_text)
    except json.JSONDecodeError:
        return []
    values = payload.get("supplier_names", [])
    if not isinstance(values, list):
        return []
    return [normalize_name(str(value)) for value in values if str(value).strip()]
