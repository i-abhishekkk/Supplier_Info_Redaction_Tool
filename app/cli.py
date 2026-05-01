import argparse
import asyncio
from pathlib import Path

from app.detection import parse_supplier_names
from app.models import RedactionOptions
from app.redactors import redact_document


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Redact supplier names and optional images from PDF/DOCX files.")
    parser.add_argument("input", type=Path, help="Path to a PDF or DOCX file.")
    parser.add_argument("--supplier", action="append", default=[], help="Supplier name to redact. Can be repeated.")
    parser.add_argument("--detect", action="store_true", help="Enable heuristic supplier-name detection.")
    parser.add_argument("--llm", action="store_true", help="Use OpenAI extraction when OPENAI_API_KEY is configured.")
    parser.add_argument("--ocr", action="store_true", help="Force Tesseract OCR, even for selectable-text PDFs.")
    parser.add_argument("--no-ocr", action="store_true", help="Disable Tesseract OCR for this run.")
    parser.add_argument("--redact-all-images", action="store_true", help="Redact every image in the document.")
    parser.add_argument(
        "--keep-header-footer-images",
        action="store_true",
        help="Do not automatically redact images in header/footer regions.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    supplier_names = []
    for value in args.supplier:
        supplier_names.extend(parse_supplier_names(value))
    result = await redact_document(
        args.input,
        RedactionOptions(
            supplier_names=supplier_names,
            detect_supplier_names=args.detect,
            use_llm_extraction=args.llm,
            use_ocr=False if args.no_ocr else (True if args.ocr else None),
            redact_all_images=args.redact_all_images,
            redact_header_footer_images=not args.keep_header_footer_images,
        ),
    )
    print(f"Output: {result.output_path}")
    print(f"Supplier names: {', '.join(result.supplier_names) if result.supplier_names else '(none)'}")
    print(f"Sources: {', '.join(result.extraction_sources) if result.extraction_sources else '(none)'}")
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f"- {warning}")
    print(f"Redactions: {len(result.hits)}")


if __name__ == "__main__":
    asyncio.run(main())
