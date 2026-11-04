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

def create_document(content: str, filename: str, output_format: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if output_format in PLAIN_TEXT_FORMATS:
        target = safe_output_path(filename, output_format)
        target.write_text(content, encoding="utf-8")
        return target

    target = safe_output_path(filename, "docx")
    doc = Document()
    doc.add_heading(Path(target).stem.replace("_", " "), 0)
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
    doc.save(target)
    return target
