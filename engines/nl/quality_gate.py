"""Final quality gate (PART 2 §20).

Aggregates every per-cell check into a severity-classified report. Each issue
carries a severity (INFO/WARNING/CRITICAL — PART 2 §12): INFO never blocks
export, WARNING is visible but non-blocking, CRITICAL blocks export. The
report's `.status` is one of PASSED / PASSED_WITH_WARNINGS / FAILED_CRITICAL.

Checks: German residue · model-name integrity (loss/substitution/count,
delegated to ModelNameIntegrityValidator) · name rules (length, brackets,
commas, forbidden endings, malformed punctuation) · metadata leaks ·
separator (`<br>`) corruption · unresolved GPT failures · information loss ·
suspicious identical output · too-short output · unresolved review warnings ·
name-compression events · plus workbook-level coverage errors.
"""

import re
from dataclasses import dataclass, field

from engines.nl.terminology import get_terminology
from engines.nl.residue_gate import get_residue_gate
from engines.nl.product_name_engine import get_product_name_engine
from engines.nl.info_preservation import get_info_validator
from engines.nl.model_integrity import get_model_integrity_validator
from engines.nl.types import CellResult, Severity

_METADATA_LEAK_RE = re.compile(
    r"(?mi)^(?:Categorie|Category|Product\s*type|Context|Note|Explanation"
    r"|Toelichting|Vertaling|Translation)\s*:.*$"
)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


@dataclass
class GateIssue:
    row: int
    column: str
    issue: str
    source: str
    output: str
    proposed_fix: str = ""
    severity: Severity = Severity.CRITICAL


@dataclass
class GateReport:
    issues: list = field(default_factory=list)
    coverage_errors: list = field(default_factory=list)
    info_events: list = field(default_factory=list)  # non-blocking, review-panel-only

    @property
    def critical_issues(self) -> list:
        return [i for i in self.issues if i.severity == Severity.CRITICAL]

    @property
    def warning_issues(self) -> list:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    @property
    def status(self) -> str:
        if self.critical_issues or self.coverage_errors:
            return "FAILED_CRITICAL"
        if self.warning_issues:
            return "PASSED_WITH_WARNINGS"
        return "PASSED"

    @property
    def passed(self) -> bool:
        """Export is allowed — no CRITICAL issues and no coverage gaps.
        Warnings are visible but non-blocking (PART 2 §20)."""
        return self.status != "FAILED_CRITICAL"

    @property
    def issue_count(self) -> int:
        return len(self.issues) + len(self.coverage_errors)


class QualityGate:
    def __init__(self):
        self._term = get_terminology()
        self._residue = get_residue_gate()
        self._name = get_product_name_engine()
        self._info = get_info_validator()
        self._model_integrity = get_model_integrity_validator()

    def check_cell(self, cell: CellResult) -> list[GateIssue]:
        issues: list[GateIssue] = []
        src, tgt = cell.source, cell.target

        def add(issue: str, fix: str = "", severity: Severity = Severity.CRITICAL):
            issues.append(GateIssue(cell.row, cell.column, issue, src, tgt, fix, severity))

        # Unresolved GPT failure → could not translate; never ship German.
        if cell.gpt_failed:
            add("GPT translation failed — cell could not be translated",
                "retry translation or translate manually", Severity.CRITICAL)

        # German residue.
        residue = self._residue.scan(tgt)
        if residue:
            proposed, _ = self._term.apply(tgt)
            add(f"German residue: {residue}", proposed, Severity.CRITICAL)

        # Model-name integrity (loss, count mismatch, cross-model substitution).
        mi = self._model_integrity.validate(tgt, cell.model_names)
        for msg in mi.issues:
            add(f"model integrity: {msg}", severity=Severity.CRITICAL)

        # Metadata leak (e.g. GPT prefixing "Categorie:" onto the value).
        leak = _METADATA_LEAK_RE.search(tgt)
        if leak:
            add(f"metadata leak: {leak.group(0)!r}", _METADATA_LEAK_RE.sub("", tgt).strip(), Severity.CRITICAL)

        # Separator corruption — <br> count must match the source.
        if _BR_RE.findall(src) and len(_BR_RE.findall(src)) != len(_BR_RE.findall(tgt)):
            add(f"<br> count changed ({len(_BR_RE.findall(src))}→{len(_BR_RE.findall(tgt))})",
                severity=Severity.CRITICAL)

        # Information loss (numbers / colors / models / abbreviations / dimension labels).
        for msg in self._info.validate(src, tgt, cell.model_names).issues:
            add(f"information loss: {msg}", severity=Severity.CRITICAL)

        # Suspicious identical output (multi-word German prose that never translated).
        identical = self._info.classify_identical(src, tgt, cell.model_names)
        if identical == "SUSPICIOUS_IDENTICAL":
            add("source and output are identical — looks untranslated, not a valid cognate/model/code",
                severity=Severity.WARNING)

        # Too-short output with an entity-preservation signal.
        if self._info.looks_too_short(src, tgt, cell.model_names):
            add("translation is suspiciously short relative to the source", severity=Severity.WARNING)

        # Name-column rules (any malformation surviving the compression engine).
        if cell.column == "name":
            for msg in self._name.validate(tgt):
                add(f"name rule: {msg}", severity=Severity.CRITICAL)

        # Name-compression event (PART 2 §11) — INFO events are review-panel-only
        # and don't count as an issue; WARNING/CRITICAL do.
        ev = cell.compression_event
        if ev and ev.severity != Severity.INFO:
            add(f"name compression ({ev.strategy}): removed {ev.removed_segments or '(nothing)'}",
                ev.recommendation, ev.severity)

        # Unresolved review warnings (unknown abbreviation, glossary flag, etc.).
        for w in cell.warnings:
            if "requires review" in w.lower():
                add(f"unresolved warning: {w}", severity=Severity.WARNING)

        return issues

    def evaluate(self, cells: list[CellResult], coverage_errors=()) -> GateReport:
        report = GateReport(coverage_errors=list(coverage_errors))
        for cell in cells:
            ev = cell.compression_event
            if ev and ev.severity == Severity.INFO:
                report.info_events.append(ev)
            if not (cell.target or "").strip():
                continue
            report.issues.extend(self.check_cell(cell))
        return report


_instance: QualityGate | None = None


def get_quality_gate() -> QualityGate:
    global _instance
    if _instance is None:
        _instance = QualityGate()
    return _instance
