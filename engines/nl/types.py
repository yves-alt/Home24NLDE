"""Shared data types for the NL localization engine."""

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    """Review-panel severity (PART 2 §12). INFO never blocks export; WARNING
    is visible but non-blocking; CRITICAL blocks export."""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


_SEVERITY_ORDER = {Severity.INFO: 0, Severity.WARNING: 1, Severity.CRITICAL: 2}


def max_severity(*severities: "Severity") -> "Severity":
    present = [s for s in severities if s is not None]
    if not present:
        return Severity.INFO
    return max(present, key=lambda s: _SEVERITY_ORDER[s])


@dataclass
class NameCompressionEvent:
    """Structured record of what a product-name compression removed, and why
    (PART 2 §11)."""
    row: int = 0
    column: str = "name"
    source: str = ""
    full_translation: str = ""
    compressed_name: str = ""
    removed_segments: list = field(default_factory=list)
    strategy: str = ""
    severity: Severity = Severity.INFO
    recommendation: str = ""


@dataclass
class CellResult:
    row: int                 # 1-based data row index
    column: str
    source: str
    target: str
    origin: str = ""         # TM_EXACT | TM_ADAPTED | TERMINOLOGY | GPT | HUMAN | EMPTY
    confidence: float = 1.0
    confidence_label: str = "OK"
    model_names: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    gpt_failed: bool = False
    compression_event: "NameCompressionEvent | None" = None

    def to_preview(self) -> dict:
        return {
            "Row": self.row,
            "Column": self.column,
            "German source": self.source,
            "Dutch translation": self.target,
            "Confidence": self.confidence_label,
            "Origin": self.origin,
            "Warnings": "; ".join(self.warnings),
        }
