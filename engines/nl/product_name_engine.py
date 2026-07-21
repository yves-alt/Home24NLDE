"""Dutch product-name compression engine (PART 2 §1-9).

Enforces Home24.nl rules for the `name` column and, when a name exceeds the
40-character limit, compresses it by generating several candidates and
scoring them — never a blind truncation. Operates on the already-translated
Dutch name (the pipeline calls this after translation); the German source and
this cell's protected model names are optional context used for scoring and
the GPT last resort.

Priority model (§3):
  P1 — product type + model name: never dropped by any candidate.
  P2 — principal feature/material/essential accessory: dropped only if every
       P3 clause is already gone and the name still doesn't fit.
  P3 — secondary accessory/detail: dropped first, one clause at a time.
  P4 — bare connectors/articles: never appear as their own clause (they're
       the separators between clauses), so nothing to "drop" here directly —
       they naturally disappear when the clause they connect is dropped.

Candidate strategies (§6): full name; connector compression (met -> +);
drop clauses starting from the lowest priority; head-only (product type +
model + first P2 clause). A GPT rewrite (§7) is tried only when none of those
are both valid and <=40 chars; each result — deterministic or GPT — is scored
by the same validator, so nothing is trusted blind. Word-boundary truncation
(§8) is the absolute last resort and always raises a CRITICAL compression
event.
"""

import re
from dataclasses import dataclass, field

from engines.nl.terminology import get_terminology, _MATERIALS, _COLORS
from engines.nl.model_protector import get_model_protector
from engines.nl.residue_gate import get_residue_gate
from engines.nl.types import Severity, NameCompressionEvent

MAX_NAME_LENGTH = 40

# Words/sequences a name must never end on.
FORBIDDEN_ENDINGS = [
    "met", "van", "voor", "uit", "en", "of", "bij", "tot", "per", "als",
    "incl.", "inkl.", "incl", "inkl",
    "keramische", "schuine", "schuin", "houten", "eikenhouten",
    "elektrische", "verstelbare", "ronde", "rechte", "open",
]

# Clause-separating connectors — also the P3/P4 "weak" boundary the shortener
# is allowed to compress or drop across.
_CONNECTOR_RE = re.compile(
    r"\s+(met|en|of|voor|van|uit|incl\.|inkl\.)\s+|\s*([+&/,])\s*|\s+-\s+"
)
_WEAK_TAIL = {"met", "van", "voor", "en", "of", "+", "-", "/", "incl.", "inkl.", "&"}

_OPT_RE = re.compile(r"\bopt\.")


@dataclass
class NameResult:
    name: str
    warnings: list = field(default_factory=list)
    was_shortened: bool = False
    compression_event: NameCompressionEvent | None = None


@dataclass
class _Clause:
    text: str
    connector_before: str | None   # None for the head clause
    priority: int                  # 1 (never drop) .. 3 (drop first)


class DutchProductNameEngine:

    def __init__(self):
        self._term = get_terminology()
        self._protector = get_model_protector()
        self._residue = get_residue_gate()

    # ── public entry points ─────────────────────────────────────────────

    def optimize(self, name: str, source: str = "", model_names=None, row: int = 0) -> NameResult:
        if not name or not name.strip():
            return NameResult(name, [])

        model_names = [m for m in (model_names or []) if m]
        warnings: list[str] = []
        result = self._clean(name)
        result = self._capitalize_first(result)
        result = self._strip_forbidden_endings(result)
        had_opt = bool(_OPT_RE.search(name))

        if len(result) <= MAX_NAME_LENGTH:
            result = self._restore_opt_if_lost(result, had_opt)
            return NameResult(result, warnings)

        compressed, event, strategy_warnings = self._compress(
            result, source=source, model_names=model_names, row=row,
        )
        compressed = self._strip_forbidden_endings(compressed)
        compressed = self._capitalize_first(compressed)
        compressed = self._restore_opt_if_lost(compressed, had_opt)
        warnings.extend(strategy_warnings)
        if compressed != result:
            warnings.append("Product name shortened — review recommended")

        # §5: source_has_opt == translation_has_opt. Compression can legitimately
        # have no room left to restore it — that must be flagged, not silent.
        if had_opt and not _OPT_RE.search(compressed):
            warnings.append("'opt.' present in source but lost during compression — review required")
            if event:
                event.severity = Severity.CRITICAL
                event.recommendation = ("'opt.' could not be preserved within the 40-character limit — "
                                        "manual review required.")

        return NameResult(compressed, warnings, was_shortened=True, compression_event=event)

    def validate(self, name: str) -> list[str]:
        """Return quality-gate issues for a finished name (§9)."""
        issues: list[str] = []
        if not name:
            return issues
        if len(name) > MAX_NAME_LENGTH:
            issues.append(f"name exceeds {MAX_NAME_LENGTH} chars ({len(name)})")
        if name.count("(") != name.count(")") or name.count("[") != name.count("]"):
            issues.append("name has unmatched brackets")
        if any(b in name for b in "()[]{}"):
            issues.append("name contains brackets")
        if "," in name:
            issues.append("name contains a comma")
        if "  " in name:
            issues.append("name contains doubled spaces")
        if "..." in name or name.endswith(".."):
            issues.append("name contains a trailing ellipsis")
        if re.search(r"(^|\s)-(\s|$)", name) or re.search(r"-{2,}", name):
            issues.append("name contains a malformed hyphen")
        if re.search(r"/\s*$", name) or re.search(r"^\s*/", name):
            issues.append("name has a dangling slash fragment")
        words = name.split()
        if words:
            last = words[-1].lower().strip(".,;:")
            if (last in {w.strip(".") for w in FORBIDDEN_ENDINGS} and last != "opt") \
                    or words[-1] in {"+", "-", "/", "&", ","}:
                issues.append(f"name ends on forbidden word '{words[-1]}'")
        return issues

    # ── cleanup ──────────────────────────────────────────────────────────

    def _clean(self, name: str) -> str:
        result = name.strip()
        result = re.sub(r"\s*[\(\[\{][^\)\]\}]*[\)\]\}]\s*", " ", result)
        result = result.replace(",", " ")
        result = re.sub(r"\s{2,}", " ", result).strip()
        return result

    def _capitalize_first(self, text: str) -> str:
        for i, ch in enumerate(text):
            if ch.isalpha():
                return text[:i] + ch.upper() + text[i + 1:]
        return text

    def _strip_forbidden_endings(self, name: str) -> str:
        words = name.split()
        changed = True
        while changed and words:
            changed = False
            last = words[-1].lower().strip(".,;:")
            last_full = words[-1].lower()
            if last == "opt":  # "opt." is a protected abbreviation, never stripped (§5)
                break
            if last in {w.strip(".") for w in FORBIDDEN_ENDINGS} or last_full in FORBIDDEN_ENDINGS:
                words.pop()
                changed = True
            elif words[-1] in {"+", "-", "/", "&"}:
                words.pop()
                changed = True
        return " ".join(words) if words else name

    def _restore_opt_if_lost(self, name: str, had_opt: bool) -> str:
        """§5: source_has_opt == translation_has_opt. If compression dropped it
        and there's room, reinsert it; the caller still records a warning via
        the compression event when this can't be done cleanly."""
        if not had_opt or _OPT_RE.search(name):
            return name
        candidate = f"{name} opt." if not name.endswith(".") else f"{name[:-1]} opt."
        return candidate if len(candidate) <= MAX_NAME_LENGTH else name

    # ── semantic parsing (§2) ───────────────────────────────────────────

    def _parse_clauses(self, name: str, model_names: list) -> list[_Clause]:
        # Split on connector boundaries, keeping the connector that preceded
        # each clause so it can be re-joined naturally.
        parts = _CONNECTOR_RE.split(name)
        # re.split with multiple groups returns [text, g1, g2, g3, text, g1, ...]
        # where exactly one of g1/g2/g3 is non-None per boundary. Rebuild pairs.
        clauses: list[_Clause] = []
        i = 0
        head = parts[0].strip()
        clauses.append(_Clause(head, None, 1))  # head = product type + model, always P1
        i = 1
        while i < len(parts):
            connector = next((g for g in parts[i:i + 3] if g), None)
            i += 3
            if i - 1 >= len(parts):
                break
            text = (parts[i - 1] if i - 1 < len(parts) else "") or ""
            text = text.strip()
            if not text:
                continue
            clauses.append(_Clause(text, connector, self._priority_of(text, model_names)))
        return [c for c in clauses if c.text]

    def _priority_of(self, clause_text: str, model_names: list) -> int:
        if any(m and m in clause_text for m in model_names):
            return 1
        low = clause_text.lower()
        # Material/color/accessory-noun presence = principal feature (P2 — §3
        # lists "principal material" explicitly, so this must be checked
        # before falling through to P3, not just accessory-type nouns).
        for nl_value in list(self._term.PRODUCT_TYPE_MAP.values()) + list(_MATERIALS.values()) + list(_COLORS.values()):
            if nl_value.lower() in low:
                return 2
        if re.search(r"\d", clause_text):  # dimensions/quantities — relevant, not secondary
            return 2
        return 3

    # ── candidate generation + scoring (§6) ─────────────────────────────

    def _join(self, head: str, clauses: list) -> str:
        out = head
        for c in clauses:
            connector = c.connector_before or "met"
            sep = "" if connector in ("+", "&", "/") else " "
            out = f"{out} {connector}{sep}{c.text}" if sep else f"{out} {connector}{c.text}"
        return re.sub(r"\s{2,}", " ", out).strip()

    def _is_valid_candidate(self, text: str, model_names: list) -> bool:
        if not text or len(text) > MAX_NAME_LENGTH:
            return False
        if any(m and m not in text for m in model_names):
            return False
        if self._residue.scan(text):
            return False
        if self.validate(text):
            return False
        return True

    def _score(self, text: str, dropped: int) -> float:
        # Longer (denser) valid candidates score higher; each dropped clause
        # costs a fixed penalty so "drop fewer" is always preferred.
        return len(text) - dropped * 3

    def _compress(self, name: str, source: str, model_names: list, row: int):
        clauses = self._parse_clauses(name, model_names)
        head = clauses[0].text if clauses else name
        tail = clauses[1:]

        candidates: list[tuple[str, int, str]] = []  # (text, dropped_count, strategy)

        # A — full name (already known to be too long, kept for scoring symmetry).
        candidates.append((name, 0, "none"))

        # B — connector compression: "met" -> "+" where it shortens the name.
        compact = re.sub(r"\bmet\b", "+", name)
        compact = re.sub(r"\s*\+\s*", " + ", compact).strip()
        if compact != name:
            candidates.append((compact, 0, "connector compression"))

        # D — drop clauses lowest-priority-first, one at a time.
        by_priority = sorted(range(len(tail)), key=lambda i: -tail[i].priority)
        remaining = list(tail)
        dropped = 0
        for idx in sorted(by_priority, reverse=True):
            if idx >= len(remaining):
                continue
            trial = list(remaining)
            del trial[idx]
            dropped += 1
            candidates.append((self._join(head, trial), dropped, "secondary segment removal"))
            remaining = trial

        # E — head + first P2 clause only (principal feature), everything else gone.
        principal = next((c for c in tail if c.priority <= 2), None)
        if principal:
            candidates.append((
                self._join(head, [principal]), len(tail) - 1, "product type + model + principal feature only",
            ))
        candidates.append((head, len(tail), "product type + model only"))

        scored = [
            (self._score(text, dropped), text, dropped, strategy)
            for text, dropped, strategy in candidates
            if self._is_valid_candidate(text, model_names)
        ]

        removed_from_full = lambda chosen: [c.text for c in tail if c.text not in chosen]

        if scored:
            scored.sort(key=lambda t: t[0], reverse=True)
            _, best_text, dropped, strategy = scored[0]
            severity = Severity.WARNING if dropped else Severity.INFO
            event = NameCompressionEvent(
                row=row, source=source, full_translation=name, compressed_name=best_text,
                removed_segments=removed_from_full(best_text), strategy=strategy,
                severity=severity,
                recommendation="Verify the removed component(s) are not commercially essential."
                if dropped else "",
            )
            return best_text, event, []

        # F — GPT fallback: only reached when nothing deterministic fit.
        gpt_text = self._gpt_fallback(name, source, model_names)
        if gpt_text and self._is_valid_candidate(gpt_text, model_names):
            event = NameCompressionEvent(
                row=row, source=source, full_translation=name, compressed_name=gpt_text,
                removed_segments=removed_from_full(gpt_text), strategy="GPT-assisted rewrite",
                severity=Severity.WARNING,
                recommendation="AI-shortened name — verify commercial accuracy.",
            )
            return gpt_text, event, []

        # §8 — absolute last resort: word-boundary trim, never mid-word.
        truncated = self._truncate_on_word_boundary(head, tail)
        event = NameCompressionEvent(
            row=row, source=source, full_translation=name, compressed_name=truncated,
            removed_segments=removed_from_full(truncated), strategy="emergency word-boundary truncation",
            severity=Severity.CRITICAL,
            recommendation="No compression strategy produced a valid name within 40 characters — "
                           "manual review required before publication.",
        )
        return truncated, event, ["Name required emergency fallback truncation — human review required"]

    def _truncate_on_word_boundary(self, head: str, tail: list) -> str:
        words = head.split()
        floor = min(3, len(words)) or len(words)
        candidate = head
        for c in tail:
            trial = f"{candidate} {c.text}"
            if len(trial) > MAX_NAME_LENGTH:
                break
            candidate = trial
        if len(candidate) > MAX_NAME_LENGTH:
            while len(" ".join(words)) > MAX_NAME_LENGTH and len(words) > floor:
                words.pop()
            candidate = " ".join(words)
            if len(candidate) > MAX_NAME_LENGTH:
                candidate = candidate[:MAX_NAME_LENGTH].rsplit(" ", 1)[0].strip()
        return candidate

    def _gpt_fallback(self, name: str, source: str, model_names: list) -> str | None:
        from engines.nl.gpt_client import get_gpt_client
        gpt = get_gpt_client()
        if not gpt.available:
            return None
        # Mask the ALREADY-KNOWN model names directly rather than re-detecting
        # via the capitalized-word heuristic — this name is by definition long
        # (compression only runs when it's over 40 chars), so the heuristic
        # would also sweep up ordinary Dutch/German nouns further in the
        # string as fake models, leaving them untranslated in GPT's response.
        masked, mapping = name, {}
        for i, m in enumerate(dict.fromkeys(mn for mn in model_names if mn), start=1):
            ph = f"⟦M{i}⟧"
            masked = masked.replace(m, ph)
            mapping[ph] = m
        res = gpt.compress_name(masked, MAX_NAME_LENGTH, source=source)
        if not res.ok or not res.text:
            return None
        restored = self._protector.restore(res.text, mapping)
        restored, _ = self._term.apply(restored)
        return restored.strip()


_instance: DutchProductNameEngine | None = None


def get_product_name_engine() -> DutchProductNameEngine:
    global _instance
    if _instance is None:
        _instance = DutchProductNameEngine()
    return _instance
