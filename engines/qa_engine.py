import re
from dataclasses import dataclass, field
from database.database import get_connection


FORBIDDEN_PATTERNS: dict[str, str] = {
    r"\bKeukeninsel\b": "kookeiland",
    r"\bDouchematt(?!e)\b": "douchemat",
    r"\bKookfeld\b": "kookplaat",
    r"\bKookkom\b": "braadpan",
    r"\bNotelaar\s+Dekor\b": "notenlook",
    r"\bZaagruw\s*Decor\b": "grof gezaagde look",
    r"\bDecor\b(?!\s*\w)": "look",
    r"\bIjzer\b(?!\s*hout)": "IJzer",
    r"\bIJs\b(?!\s*(?:koud|thee|blok|kast|water))": "ijs",
    r"\bBadewanne\b": "bad",
    r"\bWandschrank\b": "wandkast",
    r"\bTreppe\b": "trap",
}

GERMAN_WORDS_IN_NL = [
    r"\bund\b", r"\boder\b", r"\bmit\b", r"\bfür\b", r"\bvon\b", r"\bein(?:e|em|en|er|es)?\b",
    r"\bist\b", r"\bgroß\b", r"\bneu\b", r"\bhoch\b", r"\bbreit\b", r"\btief\b",
    r"\binkl\.\s*MwSt\b", r"\bzzgl\b", r"\bzzgl\.\b",
    r"\bMontage\b", r"\bVerpackung\b", r"\bLieferung\b",
]

PLURAL_CORRECTIONS: dict[str, str] = {
    r"\bstoels\b": "stoelen",
    r"\btafels\b": "tafels",
    r"\blampes\b": "lampen",
    r"\bkasten\b(?!\s+\w)": "kasten",
    r"\bregels\b": "rekken",
}

CAPITALIZATION_RULES: list[tuple[str, str]] = [
    (r"\bIjzer\b", "IJzer"),
    (r"\bIjsland\b", "IJsland"),
    (r"\b(de|het|een|van|in|op|met|voor|bij|over|door)\s+([A-Z])(?=[a-z])", lambda m: m.group(0).lower()),
]

AUTO_CORRECT_MAP: dict[str, str] = {
    **{p: r for p, r in FORBIDDEN_PATTERNS.items()},
    **{p: r for p, r in PLURAL_CORRECTIONS.items()},
}


@dataclass
class QAIssue:
    issue_type: str
    original: str
    suggestion: str
    position: int = 0
    auto_fixable: bool = False


@dataclass
class QAResult:
    original: str
    corrected: str
    issues: list[QAIssue] = field(default_factory=list)
    was_modified: bool = False

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def has_critical(self) -> bool:
        return any(i.issue_type in ("german_residue", "forbidden_pattern", "hybrid") for i in self.issues)


class DutchQAEngine:

    def validate(self, translation: str, source: str = "") -> QAResult:
        if not translation:
            return QAResult(translation, translation)

        result = translation
        issues: list[QAIssue] = []

        result, new_issues = self._check_forbidden(result)
        issues.extend(new_issues)

        result, new_issues = self._check_german_residue(result)
        issues.extend(new_issues)

        result, new_issues = self._check_capitalization(result)
        issues.extend(new_issues)

        result, new_issues = self._check_pluralization(result)
        issues.extend(new_issues)

        was_modified = result != translation
        return QAResult(translation, result, issues, was_modified)

    def _check_forbidden(self, text: str) -> tuple[str, list[QAIssue]]:
        issues = []
        for pattern, correction in FORBIDDEN_PATTERNS.items():
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                issues.append(QAIssue("forbidden_pattern", m.group(0), correction, m.start(), True))
                text = re.sub(pattern, correction, text, flags=re.IGNORECASE)
        return text, issues

    def _check_german_residue(self, text: str) -> tuple[str, list[QAIssue]]:
        issues = []
        for pattern in GERMAN_WORDS_IN_NL:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                issues.append(QAIssue("german_residue", m.group(0), "", m.start(), False))
        return text, issues

    def _check_capitalization(self, text: str) -> tuple[str, list[QAIssue]]:
        issues = []
        for pattern, correction in CAPITALIZATION_RULES:
            if callable(correction):
                new = re.sub(pattern, correction, text)
            else:
                new = re.sub(pattern, correction, text)
            if new != text:
                issues.append(QAIssue("capitalization", text, new, 0, True))
                text = new
        return text, issues

    def _check_pluralization(self, text: str) -> tuple[str, list[QAIssue]]:
        issues = []
        for pattern, correction in PLURAL_CORRECTIONS.items():
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                issues.append(QAIssue("pluralization", m.group(0), correction, m.start(), True))
                text = re.sub(pattern, correction, text, flags=re.IGNORECASE)
        return text, issues

    def validate_batch(self, pairs: list[tuple[str, str]]) -> list[QAResult]:
        return [self.validate(t, s) for s, t in pairs]

    def log_issues(self, filename: str, row_num: int, result: QAResult):
        for issue in result.issues:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO qa_log (filename, row_num, issue_type, original, corrected, auto_fixed) VALUES (?,?,?,?,?,?)",
                    (filename, row_num, issue.issue_type, issue.original, issue.suggestion, 1 if issue.auto_fixable else 0),
                )


_instance: DutchQAEngine | None = None


def get_qa_engine() -> DutchQAEngine:
    global _instance
    if _instance is None:
        _instance = DutchQAEngine()
    return _instance
