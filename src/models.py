from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class ExamResult:
    """Represents a single exam measurement from a specific date."""
    exam_name: str
    value: str
    unit: Optional[str]
    reference_range: Optional[str]
    date: date
    lab: str
    source_file: str

    def is_numeric(self) -> bool:
        try:
            float(self.value.replace(",", "."))
            return True
        except (ValueError, AttributeError):
            return False

    def numeric_value(self) -> Optional[float]:
        if self.is_numeric():
            return float(self.value.replace(",", "."))
        return None


@dataclass
class ParsedDocument:
    """Holds all exam results extracted from a single PDF file."""
    source_file: str
    lab: str
    results: list[ExamResult] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)
