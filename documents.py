"""Turn an uploaded file into plain text for Explore. Local only; nothing is sent here."""
from __future__ import annotations

import io
from dataclasses import dataclass

import settings

SUPPORTED_TYPES = ["txt", "md", "pdf"]


@dataclass
class ExtractedDoc:
    ok: bool
    text: str = ""
    message: str = ""
    truncated: bool = False


def extract_text(filename: str, data: bytes) -> ExtractedDoc:
    """Return the document's text, or a reason it could not be read."""
    if len(data) > settings.DOC_MAX_BYTES:
        mb = settings.DOC_MAX_BYTES // 1_000_000
        return ExtractedDoc(False, message=f"That file is larger than {mb} MB. Split it or paste the key parts.")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in SUPPORTED_TYPES:
        return ExtractedDoc(False, message="Upload a .txt, .md, or .pdf file.")

    if ext == "pdf":
        text = _pdf_text(data)
        if text is None:
            return ExtractedDoc(False, message="Could not read that PDF. Try a text-based PDF or paste the text.")
    else:
        text = data.decode("utf-8", errors="replace")

    text = text.strip()
    if not text:
        return ExtractedDoc(False, message="No readable text found in that file.")

    truncated = len(text) > settings.DOC_MAX_CHARS
    if truncated:
        text = text[: settings.DOC_MAX_CHARS]
    return ExtractedDoc(True, text=text, truncated=truncated)


def _pdf_text(data: bytes) -> str | None:
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:  # damaged or encrypted files
        return None
