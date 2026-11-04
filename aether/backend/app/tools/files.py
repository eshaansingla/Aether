from pathlib import Path
from docx import Document
from app.config import OUTPUT_DIR

def safe_output_path(filename: str, extension: str) -> Path:
    # Strip directories and unsafe characters; output stays within OUTPUT_DIR.
    clean = Path(filename).name
    clean = "".join(ch for ch in clean if ch.isalnum() or ch in (" ", "-", "_", ".")).strip()
    if not clean:
        clean = "aether_output"
    if not clean.lower().endswith(f".{extension}"):
        clean = f"{Path(clean).stem}.{extension}"
    target = (OUTPUT_DIR / clean).resolve()
    if OUTPUT_DIR.resolve() not in target.parents:
        raise ValueError("Invalid output path.")
    return target

PLAIN_TEXT_FORMATS = {"txt", "md", "csv", "json", "py", "js", "ts", "html", "css", "java", "c", "cpp", "sh", "yaml", "xml"}

def _write_docx_body(doc: Document, content: str):
    for block in content.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        first = lines[0].strip()
        if len(first) < 100 and (first.startswith("#") or first.lower().startswith(
            ("introduction", "conclusion", "references", "abstract", "background")
        )):
            doc.add_heading(first.lstrip("# ").strip(), level=1)
            remainder = "\n".join(lines[1:]).strip()
            if remainder:
                doc.add_paragraph(remainder)
        else:
            doc.add_paragraph(block)

def create_document(content: str, filename: str, output_format: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if output_format in PLAIN_TEXT_FORMATS:
        target = safe_output_path(filename, output_format)
        target.write_text(content, encoding="utf-8")
        return target

    target = safe_output_path(filename, "docx")
    doc = Document()
    doc.add_heading(Path(target).stem.replace("_", " "), 0)
    _write_docx_body(doc, content)
    doc.save(target)
    return target

def _output_path(name: str) -> Path:
    # Path(name).name strips any directory component, so this can never escape
    # OUTPUT_DIR regardless of what a crafted name contains.
    path = OUTPUT_DIR / Path(name).name
    if not path.is_file():
        raise FileNotFoundError(name)
    return path

def read_document_text(name: str) -> str:
    path = _output_path(name)
    ext = path.suffix.lower().lstrip(".")
    if ext == "docx":
        paragraphs = Document(path).paragraphs
        # The title heading (added by create_document/write_document_text as a level-0
        # "Title"-styled paragraph) is shown separately as the modal's own header — if it
        # weren't skipped here, editing and saving the body would duplicate it as a plain
        # line of text on every round-trip, since write_document_text always re-adds it.
        if paragraphs and paragraphs[0].style and paragraphs[0].style.name == "Title":
            paragraphs = paragraphs[1:]
        return "\n\n".join(p.text for p in paragraphs)
    if ext in PLAIN_TEXT_FORMATS:
        return path.read_text(encoding="utf-8")
    raise ValueError(f"'.{ext}' files can't be previewed in-app yet — download it instead.")

def write_document_text(name: str, content: str):
    path = _output_path(name)
    ext = path.suffix.lower().lstrip(".")
    if ext == "docx":
        doc = Document()
        doc.add_heading(path.stem.replace("_", " "), 0)
        _write_docx_body(doc, content)
        doc.save(path)
    elif ext in PLAIN_TEXT_FORMATS:
        path.write_text(content, encoding="utf-8")
    else:
        raise ValueError(f"'.{ext}' files can't be edited in-app yet — download it instead.")
    return {"name": path.name, "text": content}
