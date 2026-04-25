"""Tests for aggregator.build_dataframe, focusing on exam name normalization."""

from datetime import date

import pandas as pd
import pytest

from src.models import ExamResult, ParsedDocument
from src.aggregator import build_dataframe


def _make_doc(results):
    return ParsedDocument(source_file="test.pdf", lab="Lab Teste", results=results)


def _result(name, value="1.0", dt=date(2024, 1, 15)):
    return ExamResult(
        exam_name=name,
        value=value,
        unit="mg/dL",
        reference_range=None,
        date=dt,
        lab="Lab Teste",
        source_file="test.pdf",
    )


class TestUnicodeHyphenDedup:
    """Exam names that differ only in hyphen character should be merged into one."""

    def test_unicode_hyphen_u2010(self):
        """U+2010 HYPHEN vs U+002D HYPHEN-MINUS same exam name → 1 row."""
        doc = _make_doc([
            _result("25 Hidroxi-Vitamina D"),   # U+002D (ASCII)
            _result("25 Hidroxi\u2010Vitamina D"),  # U+2010 (Unicode hyphen)
        ])
        df = build_dataframe([doc])
        assert df["exam_name"].nunique() == 1

    def test_en_dash_u2013(self):
        """U+2013 EN DASH vs ASCII hyphen → 1 row."""
        doc = _make_doc([
            _result("HDL-Colesterol"),
            _result("HDL\u2013Colesterol"),
        ])
        df = build_dataframe([doc])
        assert df["exam_name"].nunique() == 1

    def test_multiple_hyphen_variants_same_exam(self):
        """Three variants of the same exam (different dates) deduplicate to one name."""
        doc = _make_doc([
            _result("LDL-Colesterol", dt=date(2022, 1, 1)),
            _result("LDL\u2010Colesterol", dt=date(2023, 1, 1)),
            _result("LDL\u2011Colesterol", dt=date(2024, 1, 1)),
        ])
        df = build_dataframe([doc])
        assert df["exam_name"].nunique() == 1
        assert len(df) == 3  # three distinct dates → three rows

    def test_normalized_name_is_uppercase(self):
        """Resulting exam_name should be uppercase ASCII-hyphen form."""
        doc = _make_doc([_result("25 Hidroxi\u2010Vitamina D")])
        df = build_dataframe([doc])
        assert df["exam_name"].iloc[0] == "25 HIDROXI-VITAMINA D"

    def test_different_exams_not_merged(self):
        """Exams with genuinely different names are not collapsed."""
        doc = _make_doc([
            _result("Glicose"),
            _result("Insulina"),
        ])
        df = build_dataframe([doc])
        assert df["exam_name"].nunique() == 2


class TestCaseInsensitiveDedup:
    """Same exam name in different cases on the same date → deduplicated."""

    def test_mixed_case_same_date(self):
        doc = _make_doc([
            _result("Hemoglobina"),
            _result("HEMOGLOBINA"),
        ])
        df = build_dataframe([doc])
        assert len(df) == 1

    def test_mixed_case_different_dates(self):
        doc = _make_doc([
            _result("Hemoglobina", dt=date(2023, 1, 1)),
            _result("HEMOGLOBINA", dt=date(2024, 1, 1)),
        ])
        df = build_dataframe([doc])
        assert df["exam_name"].nunique() == 1
        assert len(df) == 2
