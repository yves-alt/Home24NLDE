"""Shared data types for the NL localization engine."""

from dataclasses import dataclass, field


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
