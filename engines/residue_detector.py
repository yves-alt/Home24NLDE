import re
from dataclasses import dataclass


GERMAN_RESIDUE_PATTERNS = [
    (r"\bund\b", "en"),
    (r"\boder\b", "of"),
    (r"\bmit\b(?!\s+\w+look)", "met"),
    (r"\bfür\b", "voor"),
    (r"\bvon\b", "van"),
    (r"\baus\b", "van"),
    (r"\bauf\b", "op"),
    (r"\bein(?:e|em|en|er|es)?\b", "een"),
    (r"\bist\b", "is"),
    (r"\bnicht\b", "niet"),
    (r"\bsehr\b", "zeer"),
    (r"\bgut\b", "goed"),
    (r"\bgroß\b", "groot"),
    (r"\bklein\b", "klein"),
    (r"\bneu\b", "nieuw"),
    (r"\balt\b", "oud"),
    (r"\bhoch\b", "hoog"),
    (r"\bniedrig\b", "laag"),
    (r"\bbreit\b", "breed"),
    (r"\btief\b", "diep"),
    (r"\bpraktisch\b", "praktisch"),
    (r"\bmodern\b", "modern"),
    (r"\bstilvoll\b", "stijlvol"),
    (r"\belegan[tz]\b", "elegant"),
    (r"\brobust\b", "robuust"),
    (r"\bkomfortabel\b", "comfortabel"),
    (r"\binkl(?:usive)?\b", "incl."),
    (r"\bexkl(?:usive)?\b", "excl."),
    (r"\bmontiert\b", "gemonteerd"),
    (r"\bgeliefert\b", "geleverd"),
]

HYBRID_PATTERNS = [
    r"Keukeninsel",
    r"Douchematt(?!e)",
    r"Kookfeld",
    r"Kookkom",
    r"Notelaar(?!\s*look)",
    r"Zaagruw\s*Decor",
    r"IJzer(?!\s*\w)",
    r"IJs(?!\s*(?:koud|thee|blok))",
    r"Badewanne",
    r"Treppe",
    r"Wandschrank",
]

DUTCH_CAPITALIZATION_FIXES = [
    (r"\bIjzer\b", "IJzer"),
    (r"\bIjsland\b", "IJsland"),
]


@dataclass
class ResidueResult:
    text: str
    german_residues: list[str]
    hybrids: list[str]
    was_modified: bool


class GermanResidueDetector:

    def detect_and_clean(self, text: str, auto_fix: bool = True) -> ResidueResult:
        if not text:
            return ResidueResult(text, [], [], False)

        result = text
        german_found = []
        hybrid_found = []

        for pattern, replacement in GERMAN_RESIDUE_PATTERNS:
            m = re.search(pattern, result, re.IGNORECASE)
            if m:
                german_found.append(m.group(0))
                if auto_fix:
                    result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

        for pattern in HYBRID_PATTERNS:
            m = re.search(pattern, result, re.IGNORECASE)
            if m:
                hybrid_found.append(m.group(0))

        for pattern, replacement in DUTCH_CAPITALIZATION_FIXES:
            result = re.sub(pattern, replacement, result)

        was_modified = result != text
        return ResidueResult(result, german_found, hybrid_found, was_modified)

    def has_residue(self, text: str) -> bool:
        r = self.detect_and_clean(text, auto_fix=False)
        return bool(r.german_residues or r.hybrids)


_instance: GermanResidueDetector | None = None


def get_residue_detector() -> GermanResidueDetector:
    global _instance
    if _instance is None:
        _instance = GermanResidueDetector()
    return _instance
