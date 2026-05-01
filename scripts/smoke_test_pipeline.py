import asyncio
from pathlib import Path
import sys

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
    if not SAMPLE_PDF.exists():
        print(f"Skipping smoke test; sample PDF is not available: {SAMPLE_PDF}")
        return

    client = TestClient(app)

    health = client.get("/health")
    health.raise_for_status()
    assert health.json() == {"status": "ok"}

    normal = run_redaction(client)
    direct = asyncio.run(run_direct_redaction())
    assert len(normal["hits"]) == len(direct["hits"]), "API and direct pipeline hit counts differ"
    assert normal["supplier_names"] == direct["supplier_names"], "API and direct pipeline supplier names differ"
    warning_path = run_redaction(client, use_ocr="true", use_llm_extraction="true")

    print("API health: ok")
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
