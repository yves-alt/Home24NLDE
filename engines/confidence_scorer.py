from dataclasses import dataclass
from enum import Enum


class ConfidenceLabel(str, Enum):
    EXACT_TM = "EXACT_TM"
    FUZZY_TM = "FUZZY_TM"
    GLOSSARY = "GLOSSARY"
    CONTEXT = "CONTEXT"
    GPT = "GPT"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


@dataclass
class ConfidenceScore:
    label: ConfidenceLabel
    score: float
    explanation: str
    needs_review: bool = False

    @property
    def color(self) -> str:
        return {
            ConfidenceLabel.EXACT_TM: "#22C55E",
            ConfidenceLabel.FUZZY_TM: "#F59E0B",
            ConfidenceLabel.GLOSSARY: "#8B5CF6",
            ConfidenceLabel.CONTEXT: "#06B6D4",
            ConfidenceLabel.GPT: "#EF4444",
            ConfidenceLabel.LOW_CONFIDENCE: "#DC2626",
        }.get(self.label, "#94A3B8")

    @property
    def badge_css(self) -> str:
        return {
            ConfidenceLabel.EXACT_TM: "badge-tm",
            ConfidenceLabel.FUZZY_TM: "badge-fuzzy",
            ConfidenceLabel.GLOSSARY: "badge-glossary",
            ConfidenceLabel.CONTEXT: "badge-glossary",
            ConfidenceLabel.GPT: "badge-ai",
            ConfidenceLabel.LOW_CONFIDENCE: "badge-ai",
        }.get(self.label, "")


def score_translation(
    source: str,
    translation: str,
    source_type: str,
    tm_score: float = 0.0,
    qa_issue_count: int = 0,
) -> ConfidenceScore:
    # Score based on source type
    if source_type == "TM_EXACT":
        base_score = 1.0
        label = ConfidenceLabel.EXACT_TM
        explanation = "Exact match in Translation Memory"

    elif source_type in ("TM_FUZZY", "TM_PATTERN"):
        base_score = max(tm_score, 0.0)
        label = ConfidenceLabel.FUZZY_TM
        explanation = f"Fuzzy TM match ({tm_score:.0%} similarity)"

    elif source_type == "GLOSSARY":
        base_score = 0.90
        label = ConfidenceLabel.GLOSSARY
        explanation = "Resolved via Dutch glossary"

    elif source_type == "CONTEXT":
        base_score = 0.85
        label = ConfidenceLabel.CONTEXT
        explanation = "Context-based translation rule"

    elif source_type == "TFIDF":
        base_score = max(tm_score * 0.9, 0.0)
        label = ConfidenceLabel.FUZZY_TM
        explanation = f"TF-IDF semantic match ({tm_score:.0%})"

    elif source_type == "AI":
        base_score = 0.70
        label = ConfidenceLabel.GPT
        explanation = "GPT fallback (no TM match)"

    else:
        base_score = 0.50
        label = ConfidenceLabel.LOW_CONFIDENCE
        explanation = "Source unknown"

    # Penalize for QA issues
    if qa_issue_count > 0:
        base_score -= 0.05 * qa_issue_count
        base_score = max(base_score, 0.0)

    if translation and len(translation) < 3:
        base_score *= 0.5

    if base_score < 0.60 and label not in (ConfidenceLabel.LOW_CONFIDENCE,):
        label = ConfidenceLabel.LOW_CONFIDENCE
        explanation += " (low score)"

    needs_review = (
        label == ConfidenceLabel.LOW_CONFIDENCE
        or (label == ConfidenceLabel.GPT and qa_issue_count > 0)
        or base_score < 0.65
    )

    return ConfidenceScore(
        label=label,
        score=round(base_score, 3),
        explanation=explanation,
        needs_review=needs_review,
    )


def score_batch(results: list[dict]) -> list[ConfidenceScore]:
    return [
        score_translation(
            source=r.get("source", ""),
            translation=r.get("target", ""),
            source_type=r.get("source_type", ""),
            tm_score=r.get("tm_score", 0.0),
            qa_issue_count=len(r.get("qa_issues", [])),
        )
        for r in results
    ]
