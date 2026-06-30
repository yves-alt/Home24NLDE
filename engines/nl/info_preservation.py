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


_instance: InformationPreservationValidator | None = None


def get_info_validator() -> InformationPreservationValidator:
    global _instance
    if _instance is None:
        _instance = InformationPreservationValidator()
    return _instance
