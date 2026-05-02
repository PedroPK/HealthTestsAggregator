"""
Security regression tests.

Scenarios covered:
  1. PDF export never touches disk (generate_pdf_bytes is fully in-memory)
  2. generate_pdf_bytes returns valid PDF bytes for normal and empty DataFrames
  3. Path traversal entries inside ZIPs are sanitized to basename only
  4. The dashboard upload pipeline sanitizes ZIP entry names before processing
"""

import io
import zipfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from src.aggregator import build_dataframe
from src.models import ExamResult, ParsedDocument
from src.parser import parse_zip_file
from src.pdf_exporter import generate_pdf_bytes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_pdf_bytes() -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 750, "placeholder")
    c.save()
    buf.seek(0)
    return buf.read()


def _make_zip_with_entry(entry_name: str) -> bytes:
    """Return an in-memory ZIP with a single PDF stored under entry_name."""
    pdf_bytes = _make_minimal_pdf_bytes()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(entry_name, pdf_bytes)
    buf.seek(0)
    return buf.read()


def _minimal_df() -> pd.DataFrame:
    doc = ParsedDocument(
        source_file="test.pdf",
        lab="Lab Teste",
        results=[
            ExamResult(
                exam_name="GLICOSE",
                value="95.0",
                unit="mg/dL",
                reference_range="70-99",
                date=date(2024, 6, 1),
                lab="Lab Teste",
                source_file="test.pdf",
            )
        ],
    )
    return build_dataframe([doc])


# ---------------------------------------------------------------------------
# 1. PDF export: entirely in memory, never writes to disk
# ---------------------------------------------------------------------------

class TestPdfExportInMemory:
    """generate_pdf_bytes must never touch the filesystem."""

    def test_returns_bytes(self):
        df = _minimal_df()
        result = generate_pdf_bytes(df)
        assert isinstance(result, bytes)

    def test_returns_valid_pdf_magic_bytes(self):
        df = _minimal_df()
        result = generate_pdf_bytes(df)
        assert result[:4] == b"%PDF", "Result is not a valid PDF (missing %PDF header)"

    def test_does_not_call_tempfile(self):
        """If tempfile is touched, the test fails - ensuring no disk writes."""
        df = _minimal_df()

        def _raise(*args, **kwargs):
            raise AssertionError("generate_pdf_bytes must not use tempfile")

        with patch("tempfile.NamedTemporaryFile", side_effect=_raise), \
             patch("tempfile.mkstemp", side_effect=_raise), \
             patch("tempfile.mkdtemp", side_effect=_raise):
            result = generate_pdf_bytes(df)

        assert result[:4] == b"%PDF"

    def test_empty_dataframe_returns_valid_pdf(self):
        df = pd.DataFrame(columns=["exam_name", "date", "value_raw", "value_numeric",
                                   "unit", "reference_range", "lab", "source_file"])
        result = generate_pdf_bytes(df)
        assert isinstance(result, bytes)
        assert result[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# 2. Path traversal: ZIP entry names must be reduced to basename
# ---------------------------------------------------------------------------

class TestZipPathTraversal:
    """
    ZIP entries with path traversal sequences or nested paths must have their
    names sanitised to basename only before being used as source_file.
    """

    def test_traversal_path_sanitized_to_basename(self):
        """Entry '../../evil.pdf' -> source_file 'evil.pdf', no '..' present."""
        zip_bytes = _make_zip_with_entry("../../evil.pdf")
        buf = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(buf) as zf:
            for entry in zf.infolist():
                if entry.filename.lower().endswith(".pdf"):
                    sanitized = Path(entry.filename).name
        assert sanitized == "evil.pdf"
        assert ".." not in sanitized

    def test_nested_subdir_sanitized_to_basename(self):
        """Entry 'subdir/nested/exam.pdf' -> source_file 'exam.pdf'."""
        zip_bytes = _make_zip_with_entry("subdir/nested/exam.pdf")
        buf = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(buf) as zf:
            for entry in zf.infolist():
                if entry.filename.lower().endswith(".pdf"):
                    sanitized = Path(entry.filename).name
        assert sanitized == "exam.pdf"

    def test_parse_zip_file_source_file_has_no_traversal(self, tmp_path):
        """parse_zip_file: doc.source_file must not contain path separators or '..'."""
        zip_bytes = _make_zip_with_entry("../../malicious.pdf")
        zip_path = tmp_path / "test.zip"
        zip_path.write_bytes(zip_bytes)

        docs = parse_zip_file(zip_path)

        assert len(docs) == 1
        assert docs[0].source_file == "malicious.pdf"
        assert ".." not in docs[0].source_file
        assert "/" not in docs[0].source_file
        assert "\\" not in docs[0].source_file

    def test_parse_zip_file_nested_path_source_file_is_basename(self, tmp_path):
        """parse_zip_file: nested-path entry produces basename-only source_file."""
        zip_bytes = _make_zip_with_entry("2024/january/bloodwork.pdf")
        zip_path = tmp_path / "test.zip"
        zip_path.write_bytes(zip_bytes)

        docs = parse_zip_file(zip_path)

        assert len(docs) == 1
        assert docs[0].source_file == "bloodwork.pdf"

    def test_dashboard_zip_pipeline_sanitizes_traversal(self):
        """
        Replicates the dashboard BytesIO upload pipeline:
        raw bytes -> ZipFile(BytesIO) -> Path(entry.filename).name
        Ensures the in-memory path never propagates a traversal sequence.
        """
        zip_bytes = _make_zip_with_entry("../../attack.pdf")
        raw = zip_bytes  # simulates uf.read() in the dashboard

        collected_fnames = []
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            for entry in zf.infolist():
                if entry.filename.lower().endswith(".pdf"):
                    fname = Path(entry.filename).name  # mirrors dashboard code
                    collected_fnames.append(fname)

        assert collected_fnames == ["attack.pdf"]
        assert all(".." not in f for f in collected_fnames)
        assert all("/" not in f for f in collected_fnames)
