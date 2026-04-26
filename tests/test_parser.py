"""
Regression tests for parser integrity.

Scenarios covered:
  1. All pages of a PDF are read (guards against iterators that consume pdf.pages)
  2. All PDFs inside a ZIP are processed (no silent skips)
  3. Multi-date data points per exam are fully preserved end-to-end
"""

import io
import zipfile
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.aggregator import build_dataframe
from src.models import ExamResult, ParsedDocument
from src.parser import parse_pdf_bytes, parse_zip_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_pdf_bytes() -> bytes:
    """Create a minimal valid PDF using reportlab."""
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 750, "placeholder")
    c.save()
    buf.seek(0)
    return buf.read()


def _make_zip_with_pdfs(names: list[str]) -> bytes:
    """Return an in-memory ZIP containing one minimal PDF per name."""
    pdf_bytes = _make_minimal_pdf_bytes()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in names:
            zf.writestr(name, pdf_bytes)
    buf.seek(0)
    return buf.read()


def _make_exam_doc(exam_name: str, dates: list[date]) -> ParsedDocument:
    results = [
        ExamResult(
            exam_name=exam_name,
            value=str(float(i + 1)),
            unit="mg/dL",
            reference_range=None,
            date=d,
            lab="Lab Teste",
            source_file="test.pdf",
        )
        for i, d in enumerate(dates)
    ]
    return ParsedDocument(source_file="test.pdf", lab="Lab Teste", results=results)


# ---------------------------------------------------------------------------
# 1. All pages of a PDF must be read
# ---------------------------------------------------------------------------

class TestAllPagesRead:
    """
    parse_pdf_bytes must call extract_text() on every page.

    Any wrapper around pdf.pages that consumes the iterator (e.g. tqdm with
    a generator, or wrapping inside a closed context) will make this fail.
    """

    def _mock_pdf_context(self, n_pages: int):
        mock_pages = []
        for i in range(n_pages):
            p = MagicMock()
            p.extract_text.return_value = f"Page {i + 1} text"
            mock_pages.append(p)

        mock_pdf = MagicMock()
        mock_pdf.pages = mock_pages

        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_pdf)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        return mock_ctx, mock_pages

    def test_all_pages_extracted_single_page(self):
        mock_ctx, pages = self._mock_pdf_context(1)
        with patch("src.parser.pdfplumber.open", return_value=mock_ctx):
            parse_pdf_bytes(b"fake", "test.pdf")
        assert pages[0].extract_text.call_count == 1

    def test_all_pages_extracted_two_pages(self):
        mock_ctx, pages = self._mock_pdf_context(2)
        with patch("src.parser.pdfplumber.open", return_value=mock_ctx):
            parse_pdf_bytes(b"fake", "test.pdf")
        calls = sum(p.extract_text.call_count for p in pages)
        assert calls == 2, (
            f"Expected extract_text() called 2 times (one per page), got {calls}. "
            "pdf.pages iterator may have been consumed or short-circuited."
        )

    def test_all_pages_extracted_five_pages(self):
        mock_ctx, pages = self._mock_pdf_context(5)
        with patch("src.parser.pdfplumber.open", return_value=mock_ctx):
            parse_pdf_bytes(b"fake", "test.pdf")
        calls = sum(p.extract_text.call_count for p in pages)
        assert calls == 5, (
            f"Expected extract_text() called 5 times, got {calls}. "
            "A page iterator wrapper likely consumed some pages prematurely."
        )

    def test_no_page_called_more_than_once(self):
        """Each page should be read exactly once — no double-reads."""
        mock_ctx, pages = self._mock_pdf_context(3)
        with patch("src.parser.pdfplumber.open", return_value=mock_ctx):
            parse_pdf_bytes(b"fake", "test.pdf")
        for i, p in enumerate(pages):
            assert p.extract_text.call_count == 1, (
                f"Page {i + 1} was read {p.extract_text.call_count} times, expected 1."
            )


# ---------------------------------------------------------------------------
# 2. All PDFs inside a ZIP must be processed
# ---------------------------------------------------------------------------

class TestZipAllFilesProcessed:
    """parse_zip_file must return exactly one ParsedDocument per PDF in the archive."""

    def test_single_pdf_in_zip(self, tmp_path):
        zip_file = tmp_path / "test.zip"
        zip_file.write_bytes(_make_zip_with_pdfs(["exam_01.pdf"]))
        docs = parse_zip_file(zip_file)
        assert len(docs) == 1

    def test_three_pdfs_in_zip(self, tmp_path):
        names = ["exam_01.pdf", "exam_02.pdf", "exam_03.pdf"]
        zip_file = tmp_path / "test.zip"
        zip_file.write_bytes(_make_zip_with_pdfs(names))
        docs = parse_zip_file(zip_file)
        assert len(docs) == 3, (
            f"Expected 3 documents from ZIP, got {len(docs)}. "
            "Some PDF files inside the archive may have been silently skipped."
        )

    def test_non_pdf_entries_ignored(self, tmp_path):
        """TXT and JPG entries must not produce documents."""
        pdf_bytes = _make_minimal_pdf_bytes()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("exam_01.pdf", pdf_bytes)
            zf.writestr("notes.txt", b"text content")
            zf.writestr("scan.jpg", b"fake image bytes")
        zip_file = tmp_path / "mixed.zip"
        zip_file.write_bytes(buf.getvalue())

        docs = parse_zip_file(zip_file)
        assert len(docs) == 1

    def test_source_file_names_match_zip_entries(self, tmp_path):
        names = ["exam_01.pdf", "exam_02.pdf"]
        zip_file = tmp_path / "test.zip"
        zip_file.write_bytes(_make_zip_with_pdfs(names))

        docs = parse_zip_file(zip_file)
        source_names = {d.source_file for d in docs}
        assert source_names == set(names)

    def test_empty_zip_returns_empty_list(self, tmp_path):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w"):
            pass
        zip_file = tmp_path / "empty.zip"
        zip_file.write_bytes(buf.getvalue())

        docs = parse_zip_file(zip_file)
        assert docs == []


# ---------------------------------------------------------------------------
# 3. Multi-date data points must be fully preserved end-to-end
# ---------------------------------------------------------------------------

class TestMultiDateDataPointsPreserved:
    """
    The DataFrame produced by build_dataframe must contain one row per
    (exam_name, date) combination. This is the end-to-end regression that
    catches any bug where multi-date history is collapsed to a single point.
    """

    DATES = [
        date(2022, 1, 10),
        date(2023, 3, 15),
        date(2024, 6, 20),
        date(2025, 9, 5),
    ]

    def test_four_dates_produce_four_rows(self):
        doc = _make_exam_doc("GLICOSE", self.DATES)
        df = build_dataframe([doc])
        rows = df[df["exam_name"] == "GLICOSE"]
        assert len(rows) == 4, (
            f"Expected 4 data points for GLICOSE, got {len(rows)}. "
            "Exam history across dates is being collapsed."
        )

    def test_two_dates_produce_two_rows(self):
        doc = _make_exam_doc("HEMOGLOBINA", self.DATES[:2])
        df = build_dataframe([doc])
        rows = df[df["exam_name"] == "HEMOGLOBINA"]
        assert len(rows) == 2

    def test_multiple_exams_each_preserve_all_dates(self):
        docs = [
            _make_exam_doc("HEMOGLOBINA", self.DATES),
            _make_exam_doc("COLESTEROL TOTAL", self.DATES[:3]),
        ]
        df = build_dataframe(docs)
        assert len(df[df["exam_name"] == "HEMOGLOBINA"]) == 4
        assert len(df[df["exam_name"] == "COLESTEROL TOTAL"]) == 3

    def test_same_exam_across_two_documents_merged(self):
        """
        One exam spread across two separate ParsedDocuments (e.g. two PDFs)
        must produce the combined number of data points, not just one document's worth.
        """
        doc1 = _make_exam_doc("GLICOSE", [date(2023, 1, 1), date(2024, 1, 1)])
        doc2 = _make_exam_doc("GLICOSE", [date(2025, 1, 1)])
        df = build_dataframe([doc1, doc2])
        rows = df[df["exam_name"] == "GLICOSE"]
        assert len(rows) == 3, (
            f"Expected 3 data points across 2 documents, got {len(rows)}."
        )

    def test_dates_are_sorted_ascending(self):
        """Data points must be sorted by date so charts render correctly."""
        doc = _make_exam_doc("ACIDO URICO", list(reversed(self.DATES)))
        df = build_dataframe([doc])
        rows = df[df["exam_name"] == "ACIDO URICO"]
        dates = rows["date"].tolist()
        assert dates == sorted(dates), "Rows must be sorted by date ascending."

    def test_duplicate_exam_same_date_kept_once(self):
        """Same (exam, date) from two sources must deduplicate to one row."""
        d = date(2024, 6, 1)
        doc1 = _make_exam_doc("CREATININA", [d])
        doc2 = _make_exam_doc("CREATININA", [d])
        df = build_dataframe([doc1, doc2])
        rows = df[df["exam_name"] == "CREATININA"]
        assert len(rows) == 1, (
            f"Duplicate (exam, date) should yield 1 row, got {len(rows)}."
        )
