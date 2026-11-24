"""Document text extraction — PDF, DOCX, HTML, Markdown, TXT."""

from __future__ import annotations

from pathlib import Path


class ExtractionError(Exception):
    pass


def extract_text(path: Path) -> str:
    """Extract plain text from a document. Raises ExtractionError if unsupported or scan."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    elif suffix in (".docx", ".doc"):
        return _extract_docx(path)
    elif suffix in (".html", ".htm"):
        return _extract_html(path)
    elif suffix in (".md", ".markdown"):
        return path.read_text(encoding="utf-8", errors="replace")
    elif suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="replace")
    else:
        raise ExtractionError(f"Unsupported file type: {suffix}")


def _extract_pdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)
    result = "\n\n".join(pages).strip()
    if not result:
        raise ExtractionError(f"failed: no extractable text (possibly scanned PDF): {path.name}")
    return result


def _extract_docx(path: Path) -> str:
    from docx import Document
    doc = Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def _extract_html(path: Path) -> str:
    from bs4 import BeautifulSoup
    html = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    return soup.get_text(separator="\n").strip()
