from pathlib import Path


async def extract_text_with_document_intelligence(
    path: Path,
    endpoint: str | None,
    key: str | None,
) -> str | None:
    if not endpoint or not key:
        return None

    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
    from azure.core.credentials import AzureKeyCredential

    client = DocumentIntelligenceClient(endpoint, AzureKeyCredential(key))
    with path.open("rb") as stream:
        poller = client.begin_analyze_document(
            "prebuilt-read",
            AnalyzeDocumentRequest(bytes_source=stream.read()),
        )
    result = poller.result()
    return result.content or ""
