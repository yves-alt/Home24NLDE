"""Final quality gate (PART 15).

Aggregates every per-cell check into a single pass/fail decision. Export is
allowed only when there are zero issues. Each issue carries row, column, the
problem, the source, the produced output, and a proposed fix so the reviewer
sees exactly what to do.

Checks: German residue · model-name loss/change · name rules (>40 chars,
brackets, commas, forbidden endings) · metadata leaks · separator (<br>)
corruption · unresolved GPT failures · information loss · unresolved warnings ·
plus workbook-level coverage errors (skipped columns / missing cells).
"""

import re
from dataclasses import dataclass, field

from engines.nl.terminology import get_terminology
from engines.nl.residue_gate import get_residue_gate
from engines.nl.product_name_engine import get_product_name_engine
from engines.nl.info_preservation import get_info_validator
from engines.nl.types import CellResult

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


@dataclass
class GateReport:
    issues: list[GateIssue] = field(default_factory=list)
    coverage_errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.issues and not self.coverage_errors

    @property
    def issue_count(self) -> int:
        return len(self.issues) + len(self.coverage_errors)


class QualityGate:
    def __init__(self):
        self._term = get_terminology()
        self._residue = get_residue_gate()
        self._name = get_product_name_engine()
        self._info = get_info_validator()

    def check_cell(self, cell: CellResult) -> list[GateIssue]:
        issues: list[GateIssue] = []
        src, tgt = cell.source, cell.target

        def add(issue: str, fix: str = ""):
            issues.append(GateIssue(cell.row, cell.column, issue, src, tgt, fix))

        # Unresolved GPT failure → could not translate; never ship German.
        if cell.gpt_failed:
            add("GPT translation failed — cell could not be translated",
                "retry translation or translate manually")

        # German residue.
        residue = self._residue.scan(tgt)
        if residue:
            proposed, _ = self._term.apply(tgt)
            add(f"German residue: {residue}", proposed)

        # Model-name preservation.
        for m in cell.model_names:
            if m and m not in tgt:
                add(f"model name '{m}' lost or altered", f"restore '{m}'")

        # Metadata leak.
        leak = _METADATA_LEAK_RE.search(tgt)
        if leak:
            add(f"metadata leak: {leak.group(0)!r}", _METADATA_LEAK_RE.sub("", tgt).strip())

        # Separator corruption — <br> count must match the source.
        if _BR_RE.findall(src) and len(_BR_RE.findall(src)) != len(_BR_RE.findall(tgt)):
            add(f"<br> count changed ({len(_BR_RE.findall(src))}→{len(_BR_RE.findall(tgt))})")

        # Information loss (numbers / colors / models / abbreviations).
        for msg in self._info.validate(src, tgt, cell.model_names).issues:
            add(f"information loss: {msg}")

        # Name-column rules.
        if cell.column == "name":
            for msg in self._name.validate(tgt):
                add(f"name rule: {msg}", self._name.optimize(tgt).name)

        # Unresolved review warnings (e.g. unknown abbreviation).
        for w in cell.warnings:
            if "requires review" in w.lower():
                add(f"unresolved warning: {w}")

        return issues

    def evaluate(self, cells: list[CellResult], coverage_errors=()) -> GateReport:
        report = GateReport(coverage_errors=list(coverage_errors))
        for cell in cells:
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
