"""Structure-aware chunking — 300–500 tokens, ~50 token overlap.
Numbered procedures stay together; each chunk gets a heading-path prefix.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import tiktoken

_ENC = tiktoken.get_encoding("cl100k_base")
_CHUNK_SIZE = 400
_OVERLAP = 50


@dataclass
class Chunk:
    index: int
    heading_path: str | None
    content: str
    token_count: int


def _count_tokens(text: str) -> int:
    return len(_ENC.encode(text))


def _split_into_sections(text: str) -> list[tuple[str | None, str]]:
    """Split text on markdown headings; return [(heading_path, body), ...]."""
    heading_re = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
    sections: list[tuple[str | None, str]] = []
    heading_stack: list[tuple[int, str]] = []
    last_pos = 0

    for m in heading_re.finditer(text):
        body = text[last_pos : m.start()].strip()
        if body:
            path = " > ".join(h for _, h in heading_stack) if heading_stack else None
            sections.append((path, body))

        level = len(m.group(1))
        title = m.group(2).strip()
        heading_stack = [(lvl, h) for lvl, h in heading_stack if lvl < level]
        heading_stack.append((level, title))
        last_pos = m.end()

    tail = text[last_pos:].strip()
    if tail:
        path = " > ".join(h for _, h in heading_stack) if heading_stack else None
        sections.append((path, tail))

    return sections


def _is_numbered_procedure_line(line: str) -> bool:
    return bool(re.match(r"^\s*\d+[\.\)]\s+", line))


def _emit_chunk(heading_path: str | None, text: str, index: int) -> Chunk:
    prefix = f"[{heading_path}]\n" if heading_path else ""
    content = prefix + text.strip()
    return Chunk(index=index, heading_path=heading_path, content=content,
                 token_count=_count_tokens(content))


def _chunk_section(heading_path: str | None, body: str) -> list[Chunk]:
    """Split a section body into token-sized chunks with overlap."""
    lines = body.splitlines()
    paragraphs: list[str] = []
    current: list[str] = []

    for line in lines:
        if _is_numbered_procedure_line(line):
            if current and not _is_numbered_procedure_line(current[-1]):
                paragraphs.append("\n".join(current).strip())
                current = []
        current.append(line)
    if current:
        paragraphs.append("\n".join(current).strip())

    chunks: list[Chunk] = []
    buffer = ""
    buf_tokens = 0

    def _flush() -> None:
        nonlocal buffer, buf_tokens
        if buffer.strip():
            chunks.append(_emit_chunk(heading_path, buffer.strip(), len(chunks)))
        buffer = ""
        buf_tokens = 0

    for para in paragraphs:
        para_tokens = _count_tokens(para)

        if para_tokens > _CHUNK_SIZE:
            # Para is too big on its own — flush buffer, then split para by tokens
            _flush()
            tokens = _ENC.encode(para)
            pos = 0
            while pos < len(tokens):
                end = min(pos + _CHUNK_SIZE, len(tokens))
                sub = _ENC.decode(tokens[pos:end]).strip()
                if sub:
                    chunks.append(_emit_chunk(heading_path, sub, len(chunks)))
                if end >= len(tokens):
                    break
                pos = end - _OVERLAP
                if pos < 0:
                    pos = 0
        elif buf_tokens + para_tokens > _CHUNK_SIZE and buffer:
            chunks.append(_emit_chunk(heading_path, buffer.strip(), len(chunks)))
            # Overlap: keep last _OVERLAP tokens from previous buffer
            overlap_text = _ENC.decode(_ENC.encode(buffer)[-_OVERLAP:])
            buffer = overlap_text + "\n" + para
            buf_tokens = _count_tokens(buffer)
        else:
            buffer = (buffer + "\n" + para).strip() if buffer else para
            buf_tokens += para_tokens

    _flush()
    return chunks


def chunk_document(text: str) -> list[Chunk]:
    """Chunk a full document into structure-aware chunks."""
    sections = _split_into_sections(text)
    all_chunks: list[Chunk] = []
    global_index = 0
    for heading_path, body in sections:
        for chunk in _chunk_section(heading_path, body):
            prefix = f"[{heading_path}]\n" if heading_path and not chunk.content.startswith("[") else ""
            all_chunks.append(Chunk(
                index=global_index,
                heading_path=heading_path,
                content=prefix + chunk.content,
                token_count=chunk.token_count,
            ))
            global_index += 1
    return all_chunks
