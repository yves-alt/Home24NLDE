"""Glossary compliance validation AFTER translation completes (PART 2 §15).

The deterministic pipeline applies the glossary during translation, but GPT
(or a stale TM entry) can still land on an unapproved synonym instead of the
official Dutch term. This re-checks the *finished* output against every
official-glossary term whose German source appears in the cell's source text.

Two outcomes per term:
  - "corrected": the German term itself survived untranslated in the output —
    an unambiguous, safe substring fix (this also reinforces the residue gate,
    scoped to official-glossary terms specifically).
  - "flagged": the approved Dutch term is missing but the German source isn't
    present either — GPT used some other wording. We don't guess what to
    replace; this is logged as a WARNING for human review instead.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime

from database.database import get_connection
from engines.nl.terminology import get_terminology


@dataclass
class GlossaryValidationEvent:
    source_term: str
    expected_target: str
    actual_output: str
    action: str  # "corrected" | "flagged"


@dataclass
class GlossaryComplianceResult:
    target: str
    events: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(e.action == "flagged" for e in self.events)


class GlossaryComplianceValidator:
    def __init__(self):
        self._term = get_terminology()

    def validate(self, source: str, target: str) -> GlossaryComplianceResult:
        events: list[GlossaryValidationEvent] = []
        result_target = target or ""
        src_low = (source or "").lower()
        if not src_low or not result_target:
            return GlossaryComplianceResult(result_target, events)
        tgt_low = result_target.lower()

        candidates = list(self._term._db_general.items()) + list(self._term._db_labels.items())
        for de, nl in candidates:
            de_low, nl_low = de.lower(), nl.lower()
            # Cheap substring pre-filter first (fast, avoids compiling/running a
            # regex for ~2-3k terms on every cell); the real containment check
            # is word-boundary-anchored, never a raw substring match — §15
            # explicitly warns against naive substring checks, and a short
            # source term like "t" -> "D" (a real row: a dimension-label
            # abbreviation) would otherwise corrupt any word containing a "t".
            if len(de_low) < 3 or de_low not in src_low or nl_low in tgt_low:
                continue
            src_pattern = re.compile(rf"\b{re.escape(de)}\b", re.IGNORECASE)
            if not src_pattern.search(source):
                continue
            tgt_pattern = re.compile(rf"\b{re.escape(de)}\b", re.IGNORECASE)
            if tgt_pattern.search(result_target):
                result_target = tgt_pattern.sub(nl, result_target, count=1)
                action = "corrected"
            else:
                action = "flagged"
            events.append(GlossaryValidationEvent(de, nl, target or "", action))
            tgt_low = result_target.lower()

        return GlossaryComplianceResult(result_target, events)


_instance: GlossaryComplianceValidator | None = None


def get_glossary_validator() -> GlossaryComplianceValidator:
    global _instance
    if _instance is None:
        _instance = GlossaryComplianceValidator()
    return _instance


def validate_cells(cells, filename: str = "") -> dict:
    """Run glossary compliance on every cell, apply safe corrections in place,
    and log flagged (unresolved) cases. Returns {"corrected": n, "flagged": [...]}."""
    validator = get_glossary_validator()
    corrected = 0
    flagged: list[tuple] = []
    now = datetime.now().isoformat()

    for cell in cells:
        if not (cell.target or "").strip():
            continue
        result = validator.validate(cell.source, cell.target)
        if result.target != cell.target:
            cell.target = result.target
            corrected += 1
        for e in result.events:
            if e.action == "flagged":
                flagged.append((filename, e.source_term, e.expected_target, e.actual_output, now))
                cell.warnings = list(cell.warnings) + [
                    f"glossary: expected '{e.expected_target}' for '{e.source_term}' — requires review"
                ]

    if flagged:
        try:
            with get_connection() as conn:
                conn.executemany(
                    "INSERT INTO glossary_validation_log "
                    "(filename, source_term, expected_target, actual_output, logged_at) "
                    "VALUES (?,?,?,?,?)",
                    flagged,
                )
        except Exception:
            pass

    return {"corrected": corrected, "flagged": len(flagged)}
