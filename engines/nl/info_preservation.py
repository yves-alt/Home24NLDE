"""Information preservation validator (PART 8).

Data must never disappear during translation. This validator compares a source
segment with its Dutch target and flags anything lost:

* numbers / dimensions  — every number in the source must survive (multiset)
* colors                — a German color must be represented by its NL form
* model names           — every protected model name must be present
* abbreviations         — known appliance abbreviations must be expanded

Material wood-look transformations (Eiche → eikenlook) make strict material
enforcement unreliable, so materials are covered by the residue gate (German
material words may not survive) rather than re-checked here.
"""

import re
from collections import Counter
from dataclasses import dataclass, field

from engines.nl.terminology import GERMAN_MARKERS
from engines.nl.model_protector import CURATED_MODELS

_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
# Appliance abbreviations whose NL expansion must appear if the abbrev was present in source.
_ABBREV_REQUIRED = {
    "MW": "magnetron",
    "GSP": "vaatwasser",
    "KS": "koelkast",
    "KGK": "koel-vriescombinatie",
}

# German color → Dutch form that must appear in the target.
# (Mirrors _COLORS from terminology; extracted here to avoid circular import.)
_COLOR_MAP = {
    "Schwarz": "zwart",
    "Schwarzbraun": "zwartbruin",
    "Weiß": "wit", "Weiss": "wit",
    "Hellgrau": "lichtgrijs",
    "Dunkelgrau": "donkergrijs",
    "Grau": "grijs",
    "Hellbraun": "lichtbruin",
    "Dunkelbraun": "donkerbruin",
    "Braun": "bruin",
    "Hellblau": "lichtblauw",
    "Dunkelblau": "donkerblauw",
    "Blau": "blauw",
    "Grün": "groen",
    "Olivgrün": "olijfgroen",
    "Gelb": "geel",
    "Rot": "rood",
    "Violett": "paars",
    "Türkis": "turquoise",
    "Silber": "zilver",
    "Anthrazit": "antraciet",
    "Mehrfarbig": "meerkleurig",
}


@dataclass
class PreservationReport:
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


class InformationPreservationValidator:

    def validate(self, source: str, target: str, model_names=()) -> PreservationReport:
        issues: list[str] = []
        if not source:
            return PreservationReport(issues)
        src = source
        tgt = target or ""
        tgt_low = tgt.lower()

        # 1. Numbers (multiset) — every source number must appear in the target.
        src_nums = Counter(_NUM_RE.findall(src))
        tgt_nums = Counter(_NUM_RE.findall(tgt))
        for num, count in src_nums.items():
            if tgt_nums[num] < count:
                issues.append(f"number '{num}' missing from translation")

        # 2. Colors — German color must be represented by its Dutch form.
        for de, nl in _COLOR_MAP.items():
            if re.search(rf"\b{re.escape(de)}\b", src, re.IGNORECASE):
                if nl.lower() not in tgt_low:
                    issues.append(f"color '{de}' not represented as '{nl}'")

        # 3. Model names.
        for m in model_names:
            if m and m not in tgt:
                issues.append(f"model name '{m}' lost")

        # 4. Appliance abbreviations expanded.
        for abbr, expansion in _ABBREV_REQUIRED.items():
            if re.search(rf"\b{abbr}\b", src) and expansion not in tgt_low:
                issues.append(f"abbreviation '{abbr}' not expanded to '{expansion}'")

        # 5. Dimension label B x H x T → B x H x D preservation.
        if re.search(r"\bB\s*[xX]\s*H\s*[xX]\s*T\b", src):
            if not re.search(r"\bB\s*[xX]\s*H\s*[xX]\s*D\b", tgt, re.IGNORECASE):
                issues.append("dimension label 'B x H x T' not converted to 'B x H x D'")

        return PreservationReport(issues)

    # ── identical-output classification (PART 2 §18) ────────────────────

    def classify_identical(self, source: str, target: str, model_names=()) -> str | None:
        """Return 'VALID_IDENTICAL' / 'SUSPICIOUS_IDENTICAL' / None (not
        identical). A German source surviving unchanged isn't always wrong —
        it may be a model name, brand, code, or a term the glossary itself
        maps to the same spelling."""
        src = (source or "").strip()
        tgt = (target or "").strip()
        if not src or not tgt or src != tgt:
            return None
        words = src.split()
        if len(words) <= 1:
            return "VALID_IDENTICAL"
        if src in model_names or src.lower() in CURATED_MODELS:
            return "VALID_IDENTICAL"
        if GERMAN_MARKERS.search(src):
            return "SUSPICIOUS_IDENTICAL"
        # Multi-word but no German-only marker found — likely a legitimate
        # shared term (e.g. an international product name); not flagged.
        return "VALID_IDENTICAL"

    # ── too-short translation detection (PART 2 §19) ────────────────────

    def looks_too_short(self, source: str, target: str, model_names=()) -> bool:
        """Flag a translation as suspiciously short when the length ratio is
        low AND an entity-preservation signal fired (numbers/colors/models/
        abbreviations dropped) — German compounds legitimately shrink in
        Dutch, so ratio alone would false-positive constantly. Below an
        extreme ratio, flag regardless: even a compact Dutch compound rarely
        drops below ~15% of a substantive German source's length, so this
        catches material/descriptive-only loss the entity checks can't see
        (materials are deliberately not enforced there — see module docstring)."""
        src, tgt = (source or "").strip(), (target or "").strip()
        if not src or not tgt or len(src) < 8:
            return False
        ratio = len(tgt) / max(len(src), 1)
        if ratio < 0.15:
            return True
        if ratio >= 0.4:
            return False
        return bool(self.validate(src, tgt, model_names).issues)


_instance: InformationPreservationValidator | None = None


def get_info_validator() -> InformationPreservationValidator:
    global _instance
    if _instance is None:
        _instance = InformationPreservationValidator()
    return _instance
