"""
Aggregates ParsedDocument results into a consolidated pandas DataFrame.

Output schema:
    exam_name | date | value | unit | reference_range | lab | source_file
"""

from datetime import date
from typing import Optional

import pandas as pd

from src.models import ParsedDocument, ExamResult


def build_dataframe(documents: list[ParsedDocument]) -> pd.DataFrame:
    """Flatten all exam results into a single DataFrame, deduplicated."""
    rows = []
    for doc in documents:
        for r in doc.results:
            rows.append({
                "exam_name": r.exam_name,
                "date": r.date,
                "value_raw": r.value,
                "value_numeric": r.numeric_value(),
                "unit": r.unit,
                "reference_range": r.reference_range,
                "lab": r.lab,
                "source_file": r.source_file,
            })

    if not rows:
        return pd.DataFrame(columns=[
            "exam_name", "date", "value_raw", "value_numeric",
            "unit", "reference_range", "lab", "source_file",
        ])

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])

    # Normalize exam names for deduplication (uppercase, collapse spaces)
    df["exam_name_key"] = df["exam_name"].str.upper().str.strip().str.replace(r"\s+", " ", regex=True)
    df = df.sort_values(["exam_name_key", "date"]).reset_index(drop=True)

    # Deduplicate: keep last occurrence for same exam+date combination
    df = df.drop_duplicates(subset=["exam_name_key", "date"], keep="last")

    # Replace exam_name with normalized version (uppercase) for consistency
    df["exam_name"] = df["exam_name_key"]
    df = df.drop(columns=["exam_name_key"])

    df = df.sort_values(["exam_name", "date"]).reset_index(drop=True)
    return df


def pivot_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create a pivot table with exam names as rows and dates as columns.
    Values are value_raw strings.
    """
    if df.empty:
        return df

    pivot = df.pivot_table(
        index="exam_name",
        columns="date",
        values="value_raw",
        aggfunc="last",
    )
    # Format column headers as date strings
    pivot.columns = [
        d.strftime("%d/%m/%Y") if hasattr(d, "strftime") else str(d)
        for d in pivot.columns
    ]
    pivot = pivot.sort_index()
    return pivot


def get_exam_history(df: pd.DataFrame, exam_name: str) -> pd.DataFrame:
    """Return time-series data for a single exam."""
    mask = df["exam_name"].str.lower() == exam_name.lower()
    return df[mask].sort_values("date").reset_index(drop=True)


def list_exams(df: pd.DataFrame) -> list[str]:
    """Return sorted list of unique exam names."""
    return sorted(df["exam_name"].unique().tolist())
