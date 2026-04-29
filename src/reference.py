"""
Reference range definitions loader for HealthTests Aggregator.

Reads from config/reference_ranges.yaml.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

_DEFAULT_CONFIG = Path(__file__).parent.parent / "config" / "reference_ranges.yaml"


@dataclass
class ReferenceZone:
    """A named, colored band for chart visualization."""
    label: str
    color: str
    min: Optional[float] = None
    max: Optional[float] = None


@dataclass
class ExamReference:
    """Reference range definition for one exam type."""
    canonical_name: str
    unit: str
    ref_type: str           # "range" | "max_only" | "min_only" | "qualitative"
    min: Optional[float] = None
    max: Optional[float] = None
    note: str = ""
    zones: list[ReferenceZone] = field(default_factory=list)

    def summary(self) -> str:
        """Human-readable summary of the reference limits."""
        if self.ref_type == "range" and self.min is not None and self.max is not None:
            return f"{self.min} – {self.max} {self.unit}"
        if self.ref_type == "max_only" and self.max is not None:
            return f"≤ {self.max} {self.unit}"
        if self.ref_type == "min_only" and self.min is not None:
            return f"≥ {self.min} {self.unit}"
        return "Qualitativo"


def load_references(path: "Path | None" = None) -> dict[str, "ExamReference"]:
    """
    Load exam reference ranges from YAML.

    Returns a dict keyed by uppercase alias name → ExamReference.
    Returns an empty dict if the config file does not exist.
    """
    if path is None:
        path = _DEFAULT_CONFIG
    if not Path(path).exists():
        return {}

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    refs: dict[str, ExamReference] = {}
    for canonical, cfg in data.items():
        zones = [
            ReferenceZone(
                label=z["label"],
                color=z.get("color", "#aaaaaa"),
                min=z.get("min"),
                max=z.get("max"),
            )
            for z in cfg.get("zones", [])
        ]
        ref = ExamReference(
            canonical_name=canonical,
            unit=cfg.get("unit", ""),
            ref_type=cfg.get("type", "range"),
            min=cfg.get("min"),
            max=cfg.get("max"),
            note=cfg.get("note", ""),
            zones=zones,
        )
        for alias in cfg.get("aliases", [canonical]):
            refs[alias.strip().upper()] = ref
        refs[canonical.strip().upper()] = ref

    return refs


def get_reference(exam_name: str, refs: dict[str, ExamReference]) -> Optional[ExamReference]:
    """Look up a reference by exam name (case-insensitive, strips whitespace)."""
    return refs.get(exam_name.strip().upper())
