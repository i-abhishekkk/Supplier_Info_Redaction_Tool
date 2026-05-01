import gc
import shutil
import threading
import time
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import get_settings
from app.detection import parse_supplier_names
from app.models import RedactionOptions, RedactionResult
from app.redactors import redact_document

app = FastAPI(title=get_settings().app_name)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/redact", response_model=RedactionResult)
async def redact(
    file: UploadFile = File(...),
    supplier_names: str = Form(""),
    detect_supplier_names: bool = Form(False),
    use_llm_extraction: bool | None = Form(None),
    use_ocr: bool | None = Form(None),
    redact_all_images: bool = Form(False),
    redact_header_footer_images: bool = Form(True),
    replacement_text: str = Form("REDACTED"),
) -> RedactionResult:
    settings = get_settings()
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".docx"}:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")

    original_name = Path(file.filename or f"upload{suffix}").name
    request_dir = settings.upload_dir / uuid4().hex[:8]
    request_dir.mkdir(parents=True, exist_ok=True)
    upload_path = request_dir / original_name
    with upload_path.open("wb") as output:
        shutil.copyfileobj(file.file, output)

    names = parse_supplier_names(supplier_names)
    options = RedactionOptions(
        supplier_names=names,
        detect_supplier_names=detect_supplier_names,
        use_llm_extraction=use_llm_extraction,
        use_ocr=use_ocr,
        redact_all_images=redact_all_images,
        redact_header_footer_images=redact_header_footer_images,
        replacement_text=replacement_text or "REDACTED",
    )
    try:
        result = await redact_document(upload_path, options)
        result.download_url = f"/download?{urlencode({'path': str(result.output_path)})}"
        _remove_request_dir_later(request_dir)
        return result
    except Exception as exc:
        _remove_request_dir(request_dir)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        await file.close()


@app.get("/download")
def download(path: str) -> FileResponse:
    settings = get_settings()
    output_path = Path(path).resolve()
    output_root = settings.output_dir.resolve()
    if output_root not in output_path.parents and output_path != output_root:
        raise HTTPException(status_code=403, detail="Download path is outside output directory")
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(output_path, filename=output_path.name)


def _remove_request_dir(path: Path) -> None:
    for _ in range(10):
        gc.collect()
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return
        time.sleep(0.5)


def _remove_request_dir_later(path: Path) -> None:
    thread = threading.Thread(target=_delayed_remove_request_dir, args=(path,), daemon=True)
    thread.start()


def _delayed_remove_request_dir(path: Path) -> None:
    time.sleep(1)
    _remove_request_dir(path)
