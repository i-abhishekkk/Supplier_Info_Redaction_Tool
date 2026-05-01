from pathlib import Path
from urllib.parse import urljoin

import fitz
import httpx
import streamlit as st
from PIL import Image

from app.config import get_settings
from app.detection import parse_supplier_names
from app.models import RedactionOptions, RedactionResult


def main() -> None:
    st.set_page_config(
        page_title="Supplier Redaction Workspace",
        page_icon=None,
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    apply_theme()
    initialize_state()

    render_header()
    render_workflow()


def initialize_state() -> None:
    st.session_state.setdefault("last_result", None)
    st.session_state.setdefault("last_file_name", None)
    st.session_state.setdefault("last_error", None)
    st.session_state.setdefault("last_download_bytes", None)
    st.session_state.setdefault("last_download_name", None)


def render_header() -> None:
    st.markdown(
        """
        <section class="hero">
            <div>
                <p class="eyebrow">Business document anonymization</p>
                <h1>Supplier Redaction Workspace</h1>
                <p class="hero-copy">
                    Prepare tender and contract files for review by removing supplier names,
                    logos, and identifying images from PDF or DOCX documents.
                </p>
            </div>
            <div class="status-panel">
                <span>Upload</span>
                <span>Detect</span>
                <span>Redact</span>
                <span>Download</span>
            </div>
        </section>
        <section class="flow-strip">
            <div><strong>1</strong><span>Select document</span></div>
            <div><strong>2</strong><span>Confirm supplier names</span></div>
            <div><strong>3</strong><span>Choose OCR and image rules</span></div>
            <div><strong>4</strong><span>Download clean output</span></div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_workflow() -> None:
    left, right = st.columns([1.0, 1.05], gap="large")
    with left:
        st.markdown('<div class="panel-title">Setup</div>', unsafe_allow_html=True)
        uploaded_file = render_upload_panel()
        options = render_redaction_panel(uploaded_file)
    with right:
        st.markdown('<div class="panel-title">Review</div>', unsafe_allow_html=True)
        render_preview_panel(uploaded_file)
        render_result_panel()

    render_process_bar(uploaded_file, options)


def render_upload_panel():
    st.markdown(
        '<div class="section-title"><span>1</span><strong>Document</strong></div>',
        unsafe_allow_html=True,
    )
    uploaded_file = st.file_uploader(
        "Choose a PDF or DOCX file",
        type=["pdf", "docx"],
        accept_multiple_files=False,
        help="Supported formats: PDF and DOCX. Files up to 300 MB are allowed when using run_ui.ps1.",
    )
    if uploaded_file:
        size_kb = uploaded_file.size / 1024
        st.markdown(
            f"""
            <div class="file-summary">
                <div>
                    <span class="muted">Selected file</span>
                    <strong>{uploaded_file.name}</strong>
                </div>
                <div>
                    <span class="muted">Size</span>
                    <strong>{size_kb:,.1f} KB</strong>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div class="guidance-box">
                <strong>Start with the source file.</strong>
                <span>Upload a PDF or DOCX contract. A PDF preview will appear on the right.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    return uploaded_file


def render_redaction_panel(uploaded_file) -> RedactionOptions:
    st.markdown(
        '<div class="section-title"><span>2</span><strong>Redaction setup</strong></div>',
        unsafe_allow_html=True,
    )
    supplier_text = st.text_area(
        "Known supplier names",
        placeholder="Enter names separated by new lines, semicolons, or commas.\nExample:\nA.F.J. Development Company; Kelly Properties, LLC",
        height=124,
        help="Legal commas such as 'Company, LLC' are kept as part of the supplier name.",
    )

    detection_mode = st.radio(
        "Supplier discovery",
        ["Manual names only", "Use LLM extraction", "Use LLM + heuristic detection"],
        horizontal=True,
        help="LLM extraction requires OPENAI_API_KEY. Heuristic detection is useful for drafts but may find non-supplier organizations.",
    )

    image_mode = st.segmented_control(
        "Image and logo redaction",
        ["Header/footer logos", "All images", "Do not redact images"],
        default="Header/footer logos",
        help="Supplier logos are usually in headers or footers. Use all images for stricter anonymization.",
    )

    with st.expander("OCR and processing controls", expanded=False):
        ocr_mode = st.selectbox(
            "Tesseract OCR",
            ["Auto", "Force OCR", "Disable OCR"],
            help="Auto runs OCR only when the PDF has little selectable text. Force OCR is useful for scanned documents.",
        )
        replacement_text = st.text_input("Replacement label", value="REDACTED")

    names = parse_supplier_names(supplier_text)
    use_llm = detection_mode in {"Use LLM extraction", "Use LLM + heuristic detection"}
    detect_supplier_names = detection_mode == "Use LLM + heuristic detection"
    use_ocr = {"Auto": None, "Force OCR": True, "Disable OCR": False}[ocr_mode]
    redact_all_images = image_mode == "All images"
    redact_header_footer_images = image_mode == "Header/footer logos"

    if uploaded_file and not names and not use_llm and not detect_supplier_names:
        st.warning("Add supplier names or turn on LLM extraction before processing.")

    return RedactionOptions(
        supplier_names=names,
        detect_supplier_names=detect_supplier_names,
        use_llm_extraction=use_llm,
        use_ocr=use_ocr,
        redact_all_images=redact_all_images,
        redact_header_footer_images=redact_header_footer_images,
        replacement_text=replacement_text or "REDACTED",
    )


def render_preview_panel(uploaded_file) -> None:
    st.markdown(
        '<div class="section-title"><span>3</span><strong>Document preview</strong></div>',
        unsafe_allow_html=True,
    )
    if not uploaded_file:
        st.markdown(
            """
            <div class="empty-preview">
                <strong>No document selected</strong>
                <span>The first page preview appears here for PDF files.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix == ".pdf":
        preview = render_pdf_first_page(uploaded_file.getvalue())
        if preview:
            st.image(preview, use_container_width=True)
        else:
            st.info("Preview is unavailable for this PDF, but it can still be processed.")
    else:
        st.markdown(
            """
            <div class="empty-preview">
                <strong>DOCX selected</strong>
                <span>Word documents are processed directly and returned as redacted DOCX files.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_result_panel() -> None:
    result: RedactionResult | None = st.session_state.get("last_result")
    st.markdown(
        '<div class="section-title"><span>4</span><strong>Latest result</strong></div>',
        unsafe_allow_html=True,
    )
    if st.session_state.get("last_error"):
        st.error(st.session_state["last_error"])
        return
    if not result:
        st.markdown(
            """
            <div class="empty-preview small">
                <strong>No redacted file yet</strong>
                <span>Process a document to see the redaction summary and download button.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    text_hits = sum(1 for hit in result.hits if hit.kind == "text")
    image_hits = sum(1 for hit in result.hits if hit.kind == "image")
    pages = sorted({hit.page for hit in result.hits if hit.page is not None})
    render_metrics(text_hits, image_hits, len(result.supplier_names), len(pages))

    if result.supplier_names:
        st.markdown("**Supplier names used**")
        st.write(", ".join(result.supplier_names))

    if result.extraction_sources:
        st.markdown("**Extraction sources**")
        st.write(", ".join(label.replace("-", " ") for label in result.extraction_sources))

    if result.warnings:
        with st.expander("Processing warnings", expanded=True):
            for warning in result.warnings:
                st.warning(warning)

    download_bytes = st.session_state.get("last_download_bytes")
    download_name = st.session_state.get("last_download_name") or Path(result.output_path).name
    if download_bytes:
        st.download_button(
            "Download redacted document",
            data=download_bytes,
            file_name=download_name,
            mime=result.media_type,
            use_container_width=True,
            type="primary",
        )

    with st.expander("Redaction details", expanded=False):
        render_hit_table(result)


def render_process_bar(uploaded_file, options: RedactionOptions) -> None:
    st.markdown('<div class="action-strip">', unsafe_allow_html=True)
    col_a, col_b, col_c = st.columns([0.7, 0.15, 0.15])
    with col_a:
        st.caption("Review the setup, then run redaction. The generated document is saved under data/outputs.")
    with col_b:
        clear = st.button("Clear result", use_container_width=True)
    with col_c:
        process = st.button("Run redaction", type="primary", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if clear:
        st.session_state["last_result"] = None
        st.session_state["last_error"] = None
        st.session_state["last_file_name"] = None
        st.session_state["last_download_bytes"] = None
        st.session_state["last_download_name"] = None
        st.rerun()

    if process:
        if not uploaded_file:
            st.error("Upload a PDF or DOCX file first.")
            return
        if not options.supplier_names and not options.use_llm_extraction and not options.detect_supplier_names:
            st.error("Add supplier names or enable LLM extraction before running redaction.")
            return
        process_document(uploaded_file, options)


def process_document(uploaded_file, options: RedactionOptions) -> None:
    st.session_state["last_error"] = None
    st.session_state["last_download_bytes"] = None
    st.session_state["last_download_name"] = None
    with st.status("Redacting document", expanded=True) as status:
        st.write("Sending document to the redaction API.")
        st.write("Applying supplier-name, OCR, and image rules.")
        try:
            result = request_redaction(uploaded_file, options)
            st.write("Preparing download.")
            download_bytes = download_redacted_document(result)
        except Exception as exc:
            st.session_state["last_result"] = None
            st.session_state["last_error"] = str(exc)
            status.update(label="Redaction failed", state="error")
            return
        st.session_state["last_result"] = result
        st.session_state["last_file_name"] = uploaded_file.name
        st.session_state["last_download_bytes"] = download_bytes
        st.session_state["last_download_name"] = Path(result.output_path).name
        status.update(label="Redaction complete", state="complete")
    st.rerun()


def request_redaction(uploaded_file, options: RedactionOptions) -> RedactionResult:
    api_url = get_api_url()
    data = {
        "supplier_names": "\n".join(options.supplier_names),
        "detect_supplier_names": str(options.detect_supplier_names).lower(),
        "use_llm_extraction": str(bool(options.use_llm_extraction)).lower(),
        "redact_all_images": str(options.redact_all_images).lower(),
        "redact_header_footer_images": str(options.redact_header_footer_images).lower(),
        "replacement_text": options.replacement_text,
    }
    if options.use_ocr is not None:
        data["use_ocr"] = str(options.use_ocr).lower()

    files = {
        "file": (
            Path(uploaded_file.name).name,
            uploaded_file.getvalue(),
            uploaded_file.type or "application/octet-stream",
        )
    }
    timeout = httpx.Timeout(600.0, connect=10.0)
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(urljoin(api_url + "/", "redact"), data=data, files=files)
            response.raise_for_status()
    except httpx.ConnectError as exc:
        raise RuntimeError(f"Cannot connect to redaction API at {api_url}. Start the FastAPI backend first.") from exc
    except httpx.HTTPStatusError as exc:
        detail = _extract_api_error(exc.response)
        raise RuntimeError(f"Redaction API failed: {detail}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Redaction API request failed: {exc}") from exc
    return RedactionResult.model_validate(response.json())


def download_redacted_document(result: RedactionResult) -> bytes:
    if not result.download_url:
        raise RuntimeError("Redaction API did not return a download URL.")
    api_url = get_api_url()
    download_url = urljoin(api_url + "/", result.download_url.lstrip("/"))
    timeout = httpx.Timeout(120.0, connect=10.0)
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(download_url)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = _extract_api_error(exc.response)
        raise RuntimeError(f"Download failed: {detail}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Download request failed: {exc}") from exc
    return response.content


def get_api_url() -> str:
    return get_settings().redaction_api_url.rstrip("/")


def _extract_api_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text or response.reason_phrase
    detail = payload.get("detail")
    return str(detail or payload)


def render_metrics(text_hits: int, image_hits: int, supplier_count: int, page_count: int) -> None:
    cols = st.columns(4)
    cols[0].metric("Text redactions", text_hits)
    cols[1].metric("Image redactions", image_hits)
    cols[2].metric("Supplier names", supplier_count)
    cols[3].metric("Pages touched", page_count)


def render_hit_table(result: RedactionResult) -> None:
    if not result.hits:
        st.write("No redaction hits were recorded.")
        return
    rows = [
        {
            "Type": hit.kind,
            "Page": hit.page or "",
            "Value": hit.value or "",
            "Reason": hit.reason.replace("-", " "),
        }
        for hit in result.hits[:250]
    ]
    st.dataframe(rows, hide_index=True, use_container_width=True)
    if len(result.hits) > 250:
        st.caption(f"Showing first 250 of {len(result.hits)} hits.")


def render_pdf_first_page(content: bytes) -> Image.Image | None:
    try:
        doc = fitz.open(stream=content, filetype="pdf")
        page = doc[0]
        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.4, 1.4), alpha=False)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        doc.close()
        return image
    except Exception:
        return None


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ink: #17202a;
            --muted: #536272;
            --panel: #ffffff;
            --line: #d7dde6;
            --accent: #087568;
            --accent-dark: #075e54;
            --soft: #e8f5f2;
            --soft-line: #b8ded7;
            --page: #f5f7fa;
            --navy: #1f2a3a;
        }
        .stApp {
            background: var(--page);
            color: var(--ink);
        }
        [data-testid="stHeader"] {
            background: #ffffff !important;
            color: var(--ink) !important;
            border-bottom: 1px solid var(--line);
        }
        [data-testid="stHeader"] *,
        [data-testid="stToolbar"] *,
        [data-testid="stDecoration"] * {
            color: var(--ink) !important;
            fill: var(--ink) !important;
            opacity: 1 !important;
        }
        [data-testid="stToolbar"] button,
        [data-testid="stHeader"] button,
        [data-testid="stMainMenu"] button,
        button[kind="header"] {
            background: #ffffff !important;
            color: var(--accent-dark) !important;
            border-color: var(--line) !important;
        }
        [data-testid="stToolbar"] button:hover,
        [data-testid="stHeader"] button:hover,
        [data-testid="stMainMenu"] button:hover,
        button[kind="header"]:hover {
            background: #f6fbfa !important;
            color: var(--accent-dark) !important;
            border-color: var(--accent) !important;
        }
        [data-testid="stToolbar"] button *,
        [data-testid="stHeader"] button *,
        [data-testid="stMainMenu"] button *,
        button[kind="header"] * {
            color: inherit !important;
            fill: currentColor !important;
            opacity: 1 !important;
        }
        [data-testid="stMainMenu"],
        [data-testid="stMainMenu"] div,
        [data-baseweb="popover"],
        [data-baseweb="popover"] > div {
            background-color: #ffffff !important;
            color: var(--ink) !important;
        }
        [data-testid="stMainMenu"] *,
        [data-baseweb="popover"] * {
            color: var(--ink) !important;
            fill: var(--ink) !important;
            opacity: 1 !important;
        }
        [data-testid="stDecoration"] {
            background: var(--accent) !important;
        }
        .block-container {
            padding-top: 1.2rem;
            padding-bottom: 2.5rem;
            max-width: 1280px;
        }
        h1, h2, h3, p, label, span, div {
            letter-spacing: 0;
        }
        label, .stMarkdown, .stText, .stCaption, [data-testid="stWidgetLabel"] {
            color: var(--ink) !important;
        }
        [data-testid="stWidgetLabel"] p {
            font-size: 0.96rem;
            font-weight: 700;
            color: var(--ink) !important;
        }
        .stRadio label, .stSelectbox label, .stTextArea label, .stTextInput label, .stFileUploader label {
            color: var(--ink) !important;
        }
        .hero {
            display: flex;
            justify-content: space-between;
            gap: 24px;
            align-items: center;
            padding: 30px 32px;
            margin-bottom: 14px;
            background:
                linear-gradient(135deg, rgba(8,117,104,0.12), rgba(255,255,255,0.96) 48%),
                #ffffff;
            border: 1px solid var(--line);
            border-radius: 8px;
            color: var(--ink);
            box-shadow: 0 14px 32px rgba(31, 42, 58, 0.08);
        }
        .eyebrow {
            margin: 0 0 8px 0;
            color: var(--accent);
            font-size: 0.82rem;
            text-transform: uppercase;
            font-weight: 700;
        }
        .hero h1 {
            font-size: 2.35rem;
            margin: 0;
            letter-spacing: 0;
            color: var(--navy);
            line-height: 1.12;
        }
        .hero-copy {
            max-width: 760px;
            color: #394758;
            font-size: 1.02rem;
            line-height: 1.55;
            margin: 12px 0 0 0;
        }
        .status-panel {
            display: grid;
            grid-template-columns: repeat(2, minmax(72px, 1fr));
            gap: 8px;
            min-width: 210px;
        }
        .status-panel span {
            border: 1px solid var(--soft-line);
            background: var(--soft);
            color: var(--accent-dark);
            padding: 10px 12px;
            border-radius: 6px;
            text-align: center;
            font-weight: 700;
            font-size: 0.82rem;
        }
        .flow-strip {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 10px;
            margin-bottom: 22px;
        }
        .flow-strip div {
            display: flex;
            align-items: center;
            gap: 10px;
            background: #ffffff;
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 12px 14px;
            min-height: 48px;
        }
        .flow-strip strong {
            width: 26px;
            height: 26px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: var(--accent);
            color: #ffffff;
            border-radius: 50%;
            font-size: 0.8rem;
        }
        .flow-strip span {
            color: var(--ink);
            font-size: 0.9rem;
            font-weight: 650;
        }
        .panel-title {
            margin: 0 0 12px 0;
            padding: 13px 16px;
            background: var(--navy);
            color: #ffffff;
            border-radius: 8px;
            font-size: 1rem;
            font-weight: 800;
        }
        .section-title {
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 1.02rem;
            font-weight: 800;
            color: var(--ink);
            margin: 18px 0 12px 0;
        }
        .section-title span {
            width: 26px;
            height: 26px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: #ffffff;
            border: 1px solid var(--soft-line);
            color: var(--accent-dark);
            border-radius: 50%;
            font-size: 0.82rem;
            font-weight: 800;
        }
        .section-title strong {
            color: var(--ink);
        }
        .file-summary {
            display: grid;
            grid-template-columns: 1fr 140px;
            gap: 12px;
            padding: 16px;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: var(--panel);
            margin: 10px 0 20px 0;
        }
        .file-summary div {
            display: flex;
            flex-direction: column;
            gap: 3px;
        }
        .muted {
            color: var(--muted);
            font-size: 0.82rem;
        }
        .guidance-box {
            display: flex;
            flex-direction: column;
            gap: 5px;
            padding: 15px 16px;
            border-radius: 8px;
            background: #ffffff;
            border: 1px solid var(--line);
            color: var(--muted);
            margin: 10px 0 18px 0;
        }
        .guidance-box strong {
            color: var(--ink);
            font-size: 0.96rem;
        }
        .guidance-box span {
            color: var(--muted);
            font-size: 0.92rem;
            line-height: 1.45;
        }
        .empty-preview {
            min-height: 260px;
            border: 1px dashed #aeb8c5;
            background: #ffffff;
            border-radius: 8px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            gap: 8px;
            color: var(--muted);
            text-align: center;
            padding: 24px;
        }
        .empty-preview.small {
            min-height: 170px;
        }
        .empty-preview strong {
            color: var(--ink);
            font-size: 1rem;
        }
        .action-strip {
            margin-top: 24px;
            padding: 16px;
            border: 1px solid var(--line);
            background: #ffffff;
            border-radius: 8px;
        }
        div[data-testid="stMetric"] {
            background: white;
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 12px 14px;
        }
        div[data-testid="stMetric"] label {
            color: var(--muted) !important;
        }
        div[data-testid="stMetricValue"] {
            color: var(--navy);
            font-weight: 800;
        }
        [data-testid="stFileUploader"] section {
            background: #ffffff;
            border: 1.5px dashed #95a3b5;
            border-radius: 8px;
            padding: 18px;
        }
        [data-testid="stFileUploader"] section:hover {
            border-color: var(--accent);
            background: #fbfffe;
        }
        [data-testid="stFileUploader"] button {
            border-radius: 6px;
            border: 1px solid var(--accent);
            background: #ffffff !important;
            color: var(--accent-dark) !important;
            font-weight: 700;
        }
        [data-testid="stFileUploader"] button:hover {
            background: var(--accent) !important;
            border-color: var(--accent) !important;
            color: #ffffff !important;
        }
        [data-testid="stFileUploader"] button *,
        [data-testid="stFileUploader"] button:hover * {
            color: inherit !important;
            opacity: 1 !important;
        }
        .stTextArea textarea, .stTextInput input {
            border: 1px solid #b9c3d0;
            border-radius: 8px;
            color: var(--ink);
            background: #ffffff;
            font-size: 0.96rem;
        }
        .stSelectbox div[data-baseweb="select"] > div,
        div[data-baseweb="radio"] label,
        div[data-baseweb="tab-list"] button,
        div[data-baseweb="button-group"] button {
            color: var(--ink) !important;
        }
        .stSelectbox div[data-baseweb="select"],
        .stSelectbox div[data-baseweb="select"] > div,
        .stSelectbox div[data-baseweb="select"] div,
        div[data-baseweb="popover"] ul,
        div[data-baseweb="popover"] li,
        div[data-baseweb="menu"] {
            background-color: #ffffff !important;
            color: var(--ink) !important;
            opacity: 1 !important;
        }
        .stSelectbox div[data-baseweb="select"] svg,
        .stSelectbox div[data-baseweb="select"] span,
        .stSelectbox div[data-baseweb="select"] input,
        .stSelectbox div[data-baseweb="select"] [role="combobox"],
        div[data-baseweb="popover"] li *,
        div[data-baseweb="menu"] * {
            color: var(--ink) !important;
            fill: var(--ink) !important;
            opacity: 1 !important;
        }
        .stSelectbox div[data-baseweb="select"] > div:hover,
        div[data-baseweb="popover"] li:hover,
        div[data-baseweb="menu"] li:hover {
            background-color: #f6fbfa !important;
            color: var(--accent-dark) !important;
        }
        div[data-baseweb="popover"] li[aria-selected="true"],
        div[data-baseweb="menu"] li[aria-selected="true"] {
            background-color: var(--soft) !important;
            color: var(--accent-dark) !important;
            font-weight: 800 !important;
        }
        div[role="radiogroup"] label,
        div[role="radiogroup"] label *,
        div[role="radiogroup"] p,
        div[role="radiogroup"] span {
            color: var(--ink) !important;
            opacity: 1 !important;
        }
        div[role="radiogroup"] label {
            background: #ffffff !important;
            border: 1px solid var(--line) !important;
            border-radius: 8px !important;
            padding: 8px 10px !important;
            margin-right: 6px !important;
        }
        div[role="radiogroup"] label:has(input:checked) {
            background: var(--soft) !important;
            border-color: var(--accent) !important;
        }
        div[data-baseweb="button-group"] button,
        div[data-baseweb="button-group"] button *,
        div[data-testid="stSegmentedControl"] button,
        div[data-testid="stSegmentedControl"] button *,
        div[data-testid="stSegmentedControl"] label,
        div[data-testid="stSegmentedControl"] label *,
        div[data-testid="stSegmentedControl"] p,
        div[data-testid="stSegmentedControl"] span {
            color: var(--ink) !important;
            opacity: 1 !important;
        }
        div[data-baseweb="button-group"] button,
        div[data-testid="stSegmentedControl"] button,
        div[data-testid="stSegmentedControl"] label {
            background-color: #ffffff !important;
            color: var(--ink) !important;
            border-color: var(--line) !important;
            box-shadow: none !important;
        }
        div[data-baseweb="button-group"] button:hover,
        div[data-testid="stSegmentedControl"] button:hover,
        div[data-testid="stSegmentedControl"] label:hover {
            background-color: #f6fbfa !important;
            color: var(--accent-dark) !important;
            border-color: var(--accent) !important;
        }
        div[data-baseweb="button-group"] button[aria-pressed="true"],
        div[data-testid="stSegmentedControl"] button[aria-pressed="true"],
        div[data-testid="stSegmentedControl"] label:has(input:checked) {
            background-color: var(--soft) !important;
            color: var(--accent-dark) !important;
            border-color: var(--accent) !important;
            font-weight: 800 !important;
        }
        div[data-baseweb="button-group"] button *,
        div[data-baseweb="button-group"] button:hover *,
        div[data-baseweb="button-group"] button[aria-pressed="true"] *,
        div[data-testid="stSegmentedControl"] button *,
        div[data-testid="stSegmentedControl"] button:hover *,
        div[data-testid="stSegmentedControl"] button[aria-pressed="true"] *,
        div[data-testid="stSegmentedControl"] label *,
        div[data-testid="stSegmentedControl"] label:hover *,
        div[data-testid="stSegmentedControl"] label:has(input:checked) * {
            color: inherit !important;
            opacity: 1 !important;
        }
        .stAlert {
            border-radius: 8px;
        }
        .stExpander {
            border: 1px solid var(--line);
            border-radius: 8px;
            background: #ffffff;
        }
        [data-testid="stExpander"] details {
            background: #ffffff;
        }
        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] button,
        div.streamlit-expanderHeader,
        div.streamlit-expanderHeader *,
        div[data-testid="stExpander"] div[role="button"],
        div[data-testid="stExpander"] div[role="button"] * {
            background-color: #ffffff !important;
            color: var(--ink) !important;
            opacity: 1 !important;
        }
        [data-testid="stExpander"] {
            background-color: #ffffff !important;
            color: var(--ink) !important;
        }
        [data-testid="stExpander"] div[data-testid="stDataFrame"],
        [data-testid="stExpander"] div[data-testid="stDataFrame"] *,
        [data-testid="stExpander"] iframe,
        [data-testid="stExpander"] canvas {
            background-color: initial !important;
            color: initial !important;
        }
        [data-testid="stExpander"] summary:hover,
        [data-testid="stExpander"] button:hover,
        div.streamlit-expanderHeader:hover,
        div.streamlit-expanderHeader:hover *,
        div[data-testid="stExpander"] div[role="button"]:hover,
        div[data-testid="stExpander"] div[role="button"]:hover * {
            background-color: #f6fbfa !important;
            color: var(--accent-dark) !important;
            opacity: 1 !important;
        }
        [data-testid="stExpander"] summary {
            background: #ffffff !important;
            color: var(--ink) !important;
            border-radius: 8px;
        }
        [data-testid="stExpander"] summary:hover {
            background: #f6fbfa !important;
            color: var(--accent-dark) !important;
        }
        [data-testid="stExpander"] summary *,
        [data-testid="stExpander"] summary:hover * {
            color: inherit !important;
            opacity: 1 !important;
        }
        .stImage img {
            border: 1px solid var(--line);
            border-radius: 8px;
            background: #ffffff;
        }
        div.stButton > button[kind="primary"], div.stDownloadButton > button[kind="primary"] {
            background: var(--accent);
            border-color: var(--accent);
            color: #ffffff;
            font-weight: 800;
            border-radius: 8px;
        }
        div.stButton > button[kind="primary"]:hover, div.stDownloadButton > button[kind="primary"]:hover {
            background: var(--accent-dark);
            border-color: var(--accent-dark);
        }
        div.stButton > button, div.stDownloadButton > button {
            background: #ffffff !important;
            border: 1px solid var(--accent) !important;
            color: var(--accent-dark) !important;
            border-radius: 8px;
            font-weight: 700;
        }
        div.stButton > button:hover, div.stDownloadButton > button:hover {
            background: #f6fbfa !important;
            border-color: var(--accent-dark) !important;
            color: var(--accent-dark) !important;
        }
        div.stButton > button *, div.stDownloadButton > button *,
        div.stButton > button:hover *, div.stDownloadButton > button:hover * {
            color: inherit !important;
            opacity: 1 !important;
        }
        @media (max-width: 760px) {
            .hero {
                flex-direction: column;
                align-items: flex-start;
                padding: 22px;
            }
            .hero h1 {
                font-size: 2rem;
            }
            .status-panel {
                width: 100%;
            }
            .flow-strip {
                grid-template-columns: 1fr;
            }
            .file-summary {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
