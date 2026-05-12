import asyncio
import time
from pathlib import Path
from uuid import uuid4
import sys

import fitz
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.detection import parse_supplier_names
from app.main import app
from app.models import RedactionOptions
from app.redactors import redact_document

SAMPLE_PDF = ROOT / "contracts" / "Agreement of Purchase and Sale, A.F.J. Development Company and Kelly Properties, LLC.pdf"
SUPPLIER_NAMES = "A.F.J. Development Company, Kelly Properties, LLC"


def run_redaction(client: TestClient, *, use_ocr: str = "false", use_llm_extraction: str = "false") -> dict:
    if not SAMPLE_PDF.exists():
        raise FileNotFoundError(f"Sample PDF is not available: {SAMPLE_PDF}")
    with SAMPLE_PDF.open("rb") as stream:
        response = client.post(
            "/redact",
            files={"file": (SAMPLE_PDF.name, stream, "application/pdf")},
            data={
                "supplier_names": SUPPLIER_NAMES,
                "detect_supplier_names": "false",
                "use_ocr": use_ocr,
                "use_llm_extraction": use_llm_extraction,
                "redact_all_images": "false",
                "redact_header_footer_images": "true",
                "replacement_text": "REDACTED",
            },
        )
    response.raise_for_status()
    payload = response.json()
    output_path = ROOT / payload["output_path"]
    assert output_path.exists(), f"Output file was not created: {output_path}"
    assert payload["hits"], "Expected at least one redaction hit"

    download = client.get("/download", params={"path": str(output_path)})
    download.raise_for_status()
    assert download.content, "Downloaded file is empty"
    return payload


def run_sensitive_redaction(client: TestClient) -> dict:
    sample_pdf = ROOT / "data" / "uploads" / f"smoke_sensitive_sample.{uuid4().hex[:8]}.pdf"
    create_sensitive_sample_pdf(sample_pdf)
    try:
        with sample_pdf.open("rb") as stream:
            response = client.post(
                "/redact",
                files={"file": (sample_pdf.name, stream, "application/pdf")},
                data={
                    "supplier_names": "",
                    "sensitive_fields": "email,phone,bank_account,address",
                    "detect_supplier_names": "false",
                    "use_ocr": "false",
                    "use_llm_extraction": "false",
                    "redact_all_images": "false",
                    "redact_header_footer_images": "false",
                    "replacement_text": "REDACTED",
                },
            )
        response.raise_for_status()
        payload = response.json()
        sensitive_hits = [hit for hit in payload["hits"] if "sensitive" in hit["reason"]]
        assert len(sensitive_hits) >= 4, "Expected sensitive information redactions"
        assert payload["sensitive_fields"] == ["email", "phone", "bank_account", "address"]
        return payload
    finally:
        remove_file_with_retry(sample_pdf)


def create_sensitive_sample_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Email: privacy@example.com")
    page.insert_text((72, 96), "Phone: +91 98765 43210")
    page.insert_text((72, 120), "Account No: 123456789012")
    page.insert_text((72, 144), "Address: 123 Green Street, Mumbai 400001")
    doc.save(path)
    doc.close()


def remove_file_with_retry(path: Path) -> None:
    for _ in range(10):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            time.sleep(0.5)


async def run_direct_redaction() -> dict:
    result = await redact_document(
        SAMPLE_PDF,
        RedactionOptions(
            supplier_names=parse_supplier_names(SUPPLIER_NAMES),
            detect_supplier_names=False,
            use_llm_extraction=False,
            use_ocr=False,
            redact_all_images=False,
            redact_header_footer_images=True,
            replacement_text="REDACTED",
        ),
    )
    return result.model_dump(mode="json")


def main() -> None:
    client = TestClient(app)
    sensitive = run_sensitive_redaction(client)

    if not SAMPLE_PDF.exists():
        print(f"Skipping smoke test; sample PDF is not available: {SAMPLE_PDF}")
        print(f"Sensitive redactions: {len([hit for hit in sensitive['hits'] if 'sensitive' in hit['reason']])}")
        return

    health = client.get("/health")
    health.raise_for_status()
    assert health.json() == {"status": "ok"}

    normal = run_redaction(client)
    direct = asyncio.run(run_direct_redaction())
    assert len(normal["hits"]) == len(direct["hits"]), "API and direct pipeline hit counts differ"
    assert normal["supplier_names"] == direct["supplier_names"], "API and direct pipeline supplier names differ"
    warning_path = run_redaction(client, use_ocr="true", use_llm_extraction="true")

    print("API health: ok")
    print(f"Sensitive redactions: {len([hit for hit in sensitive['hits'] if 'sensitive' in hit['reason']])}")
    print(f"Normal run output: {normal['output_path']}")
    print(f"Normal run redactions: {len(normal['hits'])}")
    print(f"Normal run sources: {', '.join(normal['extraction_sources'])}")
    print(f"OCR/LLM requested output: {warning_path['output_path']}")
    print(f"OCR/LLM requested redactions: {len(warning_path['hits'])}")
    print(f"OCR/LLM requested warnings: {len(warning_path['warnings'])}")
    for warning in warning_path["warnings"]:
        print(f"- {warning}")


if __name__ == "__main__":
    main()
