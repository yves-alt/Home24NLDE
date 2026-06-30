"""German residue gate (PART 6).

Deterministically auto-fixes known German via the terminology brain, then
reports any critical German that survives. The orchestrator escalates anything
still German to GPT and, if it is *still* unresolved, the quality gate blocks
export. No exported cell may contain German residue.
"""

import re
from dataclasses import dataclass, field

from engines.nl.terminology import get_terminology

# Extra residue markers beyond the terminology critical list.
_EXTRA_RESIDUE = re.compile(
    r"\b(?:\d+\s*-?\s*flammig|Kombi\s+aus|Stk\.?|Stück|ca\."
    r"|Pflegeleicht|platzsparend|multifunktional|hochwertig|gemütlich"
    r"|Wohnzimmer|Schlafzimmer|Esszimmer|Kinderzimmer|Badezimmer"
    r"|Stauraum|Lieferung|Verpackung|Montage(?!\s*-?handle)"
    r"|bestehend\s+aus|in\s+verschiedenen\s+(?:Farben|Größen)"
    r"|erhältlich|geliefert|enthalten|zzgl|MwSt)\b",
    re.IGNORECASE,
)


@dataclass
class ResidueReport:
    text: str
    remaining: list[str] = field(default_factory=list)
    was_fixed: bool = False

    @property
    def is_clean(self) -> bool:
        return not self.remaining


class GermanResidueGateNL:
    def __init__(self):
        self._term = get_terminology()

    def autofix(self, text: str) -> ResidueReport:
        """Run deterministic terminology auto-fix, then detect what survives."""
        if not text:
            return ResidueReport(text, [], False)
        fixed, _ = self._term.apply(text)
        remaining = self.scan(fixed)
        return ResidueReport(fixed, remaining, fixed != text)

    def scan(self, text: str) -> list[str]:
        """Return critical German tokens present (dedup, order-preserving)."""
        if not text:
            return []
        found = self._term.remaining_german(text)
        found += [m.group(0) for m in _EXTRA_RESIDUE.finditer(text)]
        return list(dict.fromkeys(found))

    def is_clean(self, text: str) -> bool:
        return not self.scan(text)


_instance: GermanResidueGateNL | None = None


def get_residue_gate() -> GermanResidueGateNL:
    global _instance
    if _instance is None:
        _instance = GermanResidueGateNL()
    return _instance
