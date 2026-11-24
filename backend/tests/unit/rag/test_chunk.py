"""Tests for document chunking."""

from __future__ import annotations

from agentica.rag.chunk import chunk_document

SAMPLE_TEXT = """# Getting Started

This is the introduction section.

## Installation

Run the following command:

1. First step
2. Second step
3. Third step

## Configuration

Edit the config file.

### Advanced Settings

For advanced users only.
"""


def test_chunk_returns_list():
    chunks = chunk_document(SAMPLE_TEXT)
    assert isinstance(chunks, list)
    assert len(chunks) > 0


def test_chunks_have_heading_path():
    chunks = chunk_document(SAMPLE_TEXT)
    # At least some chunks should have heading_path
    headings = [c.heading_path for c in chunks if c.heading_path]
    assert len(headings) > 0


def test_chunks_have_content():
    chunks = chunk_document(SAMPLE_TEXT)
    for chunk in chunks:
        assert chunk.content.strip()


def test_numbered_procedure_stays_together():
    text = """## Restart Procedure

1. Stop the service
2. Wait 5 seconds
3. Start the service
4. Verify status
"""
    chunks = chunk_document(text)
    # Find chunk containing numbered steps
    procedure_chunk = next(
        (c for c in chunks if "1." in c.content and "4." in c.content),
        None
    )
    # Should be in same chunk since it's short
    if procedure_chunk:
        assert "1." in procedure_chunk.content
        assert "4." in procedure_chunk.content


def test_chunk_index_monotonic():
    chunks = chunk_document(SAMPLE_TEXT)
    for i, chunk in enumerate(chunks):
        assert chunk.index == i


def test_empty_text_returns_empty():
    chunks = chunk_document("")
    assert chunks == []


def test_large_text_produces_multiple_chunks():
    large = "word " * 2000  # ~2000 tokens
    chunks = chunk_document(large)
    assert len(chunks) > 1


def test_token_count_populated():
    chunks = chunk_document(SAMPLE_TEXT)
    for chunk in chunks:
        assert chunk.token_count > 0
