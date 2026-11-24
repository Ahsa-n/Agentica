"""Tests for document extraction."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from agentica.rag.extract import ExtractionError, extract_text


def test_extract_txt():
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False, encoding="utf-8") as f:
        f.write("Hello world\nThis is a test.")
        path = Path(f.name)
    text = extract_text(path)
    assert "Hello world" in text
    path.unlink()


def test_extract_markdown():
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False, encoding="utf-8") as f:
        f.write("# Title\n\nSome content.")
        path = Path(f.name)
    text = extract_text(path)
    assert "Title" in text
    path.unlink()


def test_unsupported_raises():
    with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
        path = Path(f.name)
    with pytest.raises(ExtractionError):
        extract_text(path)
    path.unlink()


def test_html_extraction():
    with tempfile.NamedTemporaryFile(suffix=".html", mode="w", delete=False, encoding="utf-8") as f:
        f.write("<html><body><h1>Title</h1><p>Content</p><script>evil()</script></body></html>")
        path = Path(f.name)
    text = extract_text(path)
    assert "Title" in text
    assert "Content" in text
    assert "evil" not in text  # script tag stripped
    path.unlink()
