"""Model Name Integrity Validator (PART 2 §10).

A dedicated, reusable check that every protected model name in a translated
cell: exists in the output, is spelled/capitalized identically, and appears
the expected number of times — plus a check that no *other* known model name
was substituted in by mistake (the "Paku -> Baldo" failure mode).

Reused by the quality gate (blocking check) and the QA page's test tool, so
"test a term" reflects the same rule that actually blocks export.
"""

import re
from collections import Counter
from dataclasses import dataclass, field

from engines.nl.model_protector import CURATED_MODELS


@dataclass
class ModelIntegrityResult:
    ok: bool
    issues: list = field(default_factory=list)


class ModelNameIntegrityValidator:

    def validate(self, target: str, model_names, other_known_models=None) -> ModelIntegrityResult:
        issues: list[str] = []
        tgt = target or ""
        expected = Counter(m for m in model_names if m)

        for m, exp_count in expected.items():
            actual_count = tgt.count(m)
            if actual_count == 0:
                issues.append(f"model name '{m}' missing from output")
            elif actual_count < exp_count:
                issues.append(f"model name '{m}' appears {actual_count}x, expected {exp_count}x")
            elif actual_count > exp_count:
                issues.append(f"model name '{m}' appears {actual_count}x, expected {exp_count}x (possible duplication)")

        # Cross-model substitution: a DIFFERENT known model name shows up in
        # the output when it wasn't one of this cell's expected models. A
        # curated model token can legitimately be a SUBSTRING of a multi-word
        # expected model (e.g. "fit"/"move" inside "Fit Move II"), so exclude
        # by substring, not just exact match.
        candidates = other_known_models if other_known_models is not None else CURATED_MODELS
        expected_lower = {m.lower() for m in expected}
        for other in candidates:
            if not other or any(other.lower() in exp for exp in expected_lower):
                continue
            if re.search(rf"\b{re.escape(other)}\b", tgt, re.IGNORECASE):
                issues.append(f"unexpected model name '{other}' found — possible substitution")

        return ModelIntegrityResult(ok=not issues, issues=issues)


_instance: ModelNameIntegrityValidator | None = None


def get_model_integrity_validator() -> ModelNameIntegrityValidator:
    global _instance
    if _instance is None:
        _instance = ModelNameIntegrityValidator()
    return _instance
