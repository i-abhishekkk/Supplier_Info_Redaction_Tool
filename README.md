# Supplier Redaction Workspace

Business-facing Streamlit application and backend pipeline for redacting supplier names, logos, and images from tender or contract documents.

## What it does

- Accepts PDF and DOCX uploads.
- Shows a first-page preview for PDFs without creating temporary preview files.
- Redacts explicit supplier names supplied by the user.
- Can opt into OpenAI LLM extraction for supplier/vendor/bidder names.
- Can opt into likely organization-name detection with local regex heuristics.
- Uses native PDF text when available.
- Uses Tesseract OCR for scanned PDFs when installed.
- Optionally uses Azure Document Intelligence OCR when endpoint/key settings are present.
- Produces a downloadable redacted PDF or DOCX under `data/outputs`.

## Recommended UI

Start the backend API first:

```powershell
.\run_api.ps1
```

In a second PowerShell window, start the Streamlit UI:

```powershell
.\run_ui.ps1
```

Open `http://localhost:8501`.

Use `run_ui.ps1` on Windows. It redirects Streamlit's config and temp folders into this project so the app does not try to write to `C:\Users\<user>\.streamlit`. The UI sends documents to the FastAPI backend configured by `REDACTION_API_URL`, which defaults to `http://127.0.0.1:8000`.

This is the recommended interface for business users. It provides document upload, PDF preview, supplier-name input, LLM/OCR options, image redaction choices, redaction summary, warnings, and a download button backed by the API.

The launcher also disables Python bytecode generation so app usage does not keep creating project-level `__pycache__` folders.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Install the Tesseract OCR engine separately. On Windows, the usual install path is:

```text
C:\Program Files\Tesseract-OCR\tesseract.exe
```

If it is not on PATH, copy `.env.example` to `.env` and set:

```text
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

## Dependencies

The project keeps dependencies focused on the UI, API boundary, document processing, OCR, and optional AI extraction:

| Package | Purpose in this project | Why it is used |
| --- | --- | --- |
| `fastapi` | Backend API for upload, redaction, health checks, and downloads. | Provides a production-ready service boundary behind the Streamlit UI. |
| `uvicorn[standard]` | ASGI server for running the FastAPI app. | Needed to serve the backend locally and in deployment. |
| `httpx` | HTTP client used by Streamlit to call FastAPI. | Lets the UI use the same backend path that production integrations will use. |
| `python-multipart` | Multipart form/file parsing for FastAPI. | Required for `POST /redact` to receive uploaded PDF/DOCX files and options. |
| `pydantic-settings` | Runtime configuration from defaults and `.env`. | Keeps paths, OCR, OpenAI, Azure, and API URL settings centralized. |
| `streamlit` | Business-facing web interface. | Provides quick upload, preview, option selection, result summary, and download UI. |
| `PyMuPDF` | PDF reading, preview rendering, text extraction, redaction, image detection, and PDF saving. | It provides the core PDF operations needed by the redaction pipeline. |
| `python-docx` | DOCX reading, text replacement, media removal, and saving. | Enables Word document redaction without converting files to another format. |
| `Pillow` | Image object handling for previews and OCR input. | Bridges rendered PDF pages and image data used by Streamlit/Tesseract. |
| `pytesseract` | Python wrapper for Tesseract OCR. | Finds text in scanned or image-based PDFs when OCR is enabled. |
| `openai` | Optional LLM-based supplier/vendor/legal-party extraction. | Helps identify supplier names when manual input is incomplete. |
| `azure-ai-documentintelligence` | Optional Azure Document Intelligence OCR/text extraction. | Supports cloud OCR when Azure endpoint/key settings are configured. |

## Run API

```powershell
.\run_api.ps1
```

Open `http://127.0.0.1:8000/docs` and call `POST /redact`. This API view is useful for developers and integration testing.

The response includes `output_path` and `download_url`. Download it with:

```text
GET /download?path=<output_path>
```

## Run CLI

```powershell
python -m app.cli "contracts\Agreement of Purchase and Sale, A.F.J. Development Company and Kelly Properties, LLC.pdf" --supplier "A.F.J. Development Company"
```

Force OCR and LLM extraction:

```powershell
python -m app.cli "contracts\some-scanned-tender.pdf" --llm --ocr --redact-all-images
```

## Smoke Test

Run the end-to-end smoke test:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -B scripts\smoke_test_pipeline.py
```

The smoke test verifies API health, sample PDF upload through `/redact`, redacted output creation, download through `/download`, and the OCR/LLM-requested path. If Tesseract or `OPENAI_API_KEY` are missing, the test expects warnings rather than crashes.

## Configuration

Create `.env` when you want LLM/OCR configuration:

```text
USE_OPENAI_EXTRACTION=false
REDACTION_API_URL=http://127.0.0.1:8000
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.4-mini
USE_TESSERACT_OCR=true
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
OCR_MODE=auto
OCR_DPI=220
OCR_MIN_CONFIDENCE=45
NATIVE_TEXT_MIN_CHARS=80
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=
AZURE_DOCUMENT_INTELLIGENCE_KEY=
REDACT_ALL_IMAGES=false
REDACT_HEADER_FOOTER_IMAGES=true
```

## Project Structure

```text
app/
  main.py                    FastAPI endpoints
  config.py                  Settings and runtime directories
  models.py                  Pydantic request/result models
  redactors.py               Core PDF/DOCX redaction pipeline
  ocr.py                     Tesseract OCR and OCR-coordinate matching
  detection.py               Heuristics and OpenAI supplier extraction
  document_intelligence.py   Optional Azure Document Intelligence OCR
  cli.py                     Command-line runner

streamlit_app.py             Streamlit business UI
run_ui.ps1                   Windows launcher for Streamlit
run_api.ps1                  Windows launcher for FastAPI backend
scripts/
  generate_pipeline_document.py
  smoke_test_pipeline.py
docs/
  Supplier_Redaction_Pipeline_Technical_Documentation.docx
contracts/                   Optional local sample contracts, ignored by Git
data/
  uploads/                   Runtime upload copies
  outputs/                   Runtime redacted files
  streamlit_tmp/             Runtime Streamlit temp folder
```

## Runtime Data

Runtime folders are intentionally ignored by `.gitignore`:

- `data/uploads`
- `data/outputs`
- `data/streamlit_tmp`
- `data/streamlit_home`
- Python caches
- logs
- Office lock files

Only `.gitkeep` placeholders are kept so the folder structure remains available.

## Notes

Use explicit supplier names when possible. LLM extraction and heuristic detection are helpful discovery tools, but contracts often mention many organizations that are not suppliers, so a reviewer should confirm names before final redaction. Image redaction defaults to header/footer images because logos commonly appear there; use `redact_all_images` when the document has embedded supplier branding throughout.

Tesseract must be installed separately. The Python package `pytesseract` is only a wrapper around the Tesseract executable.

The redaction response includes `extraction_sources` and `warnings`, so an operator can see whether the result came from native PDF text, Tesseract OCR, Azure OCR, OpenAI extraction, manual names, or heuristic detection.
