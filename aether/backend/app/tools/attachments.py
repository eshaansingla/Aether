import io
from pathlib import Path

TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".py", ".js", ".ts", ".html", ".css",
    ".java", ".c", ".cpp", ".sh", ".yaml", ".yml", ".xml", ".log",
}
# Capped well under the model's usable context window — a local model's context is
# finite and shared with the conversation history, so an uncapped multi-page PDF would
# silently push earlier turns (or the attachment itself) out of the window.
MAX_CHARS = 15000

def extract_text(filename: str, data: bytes) -> tuple[str, bool]:
    ext = Path(filename).suffix.lower()
    if ext == ".docx":
        text = _extract_docx(data)
    elif ext == ".pdf":
        text = _extract_pdf(data)
    elif ext in TEXT_EXTENSIONS or ext == "":
        text = _decode_text(data)
    else:
        raise ValueError(
            f"'{ext or 'this file type'}' isn't supported yet. "
            "Try .txt, .md, .docx, .pdf, .csv, .json, or a code file."
        )
    text = text.strip()
    if not text:
        raise ValueError("Couldn't find any readable text in that file.")
    truncated = len(text) > MAX_CHARS
    if truncated:
        text = text[:MAX_CHARS] + "\n[...truncated...]"
    return text, truncated

def _decode_text(data: bytes) -> str:
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")

def _extract_docx(data: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)

def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join((page.extract_text() or "") for page in reader.pages)
