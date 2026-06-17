"""Dutch abbreviation resolver (PART 9).

Expands the abbreviations that recur in Home24 product data. Unknown short
all-caps tokens that are not obvious product codes are flagged for review
rather than silently passed through.
"""

import re
from dataclasses import dataclass, field


# Ordered (longest / most specific first) regex → replacement.
_RULES: list[tuple[re.Pattern, str]] = [
    # Dimension label forms → "B x H x D"
    (re.compile(r"\bB\s*x\s*H\s*x\s*T\b", re.IGNORECASE), "B x H x D"),
    (re.compile(r"\bBxHxT\b", re.IGNORECASE), "B x H x D"),
    (re.compile(r"\bBHT\b"), "B x H x D"),
    # "n-Set" / "ner-Set" / "n er Set" → "set van n"
    (re.compile(r"\b(\d+)\s*er[-\s]?Set\b", re.IGNORECASE), r"set van \1"),
    (re.compile(r"\b(\d+)[-\s]?Set\b", re.IGNORECASE), r"set van \1"),
    # Appliance abbreviations
    (re.compile(r"\bMW\b"), "magnetron"),
    (re.compile(r"\bGSP\b"), "vaatwasser"),
    (re.compile(r"\bKS\b"), "koelkast"),
    (re.compile(r"\bGS\b"), "vriezer"),
    (re.compile(r"\bKGK\b"), "koel-vriescombinatie"),
    (re.compile(r"\bCERAN\b", re.IGNORECASE), "keramische kookplaat"),
]

# All-caps tokens that are legitimate and need no expansion/flag.
_KNOWN_OK = {
    "LED", "MDF", "RVS", "TV", "USB", "HDMI", "EU", "NL", "DE", "XL", "XXL",
    "XS", "S", "M", "L", "B", "H", "D", "T", "W", "V", "A", "PVC", "ABS",
    "PU", "PE", "PP", "WC", "DVD", "HD", "UV", "IP44", "IP20", "IP65",
}

_ALLCAPS_RE = re.compile(r"\b[A-ZÄÖÜ]{2,5}\b")
_ROMAN_RE = re.compile(r"^(?:II|III|IV|VI|VII|VIII|IX|XI|XII)$")


@dataclass
class AbbrevResult:
    text: str
    warnings: list[str] = field(default_factory=list)


class DutchAbbreviationResolver:

    def resolve(self, text: str) -> AbbrevResult:
        if not text:
            return AbbrevResult(text, [])

        result = text
        for pat, repl in _RULES:
            result = pat.sub(repl, result)

        warnings = self._flag_unknown(result)
        return AbbrevResult(result, warnings)

    def _flag_unknown(self, text: str) -> list[str]:
        warnings: list[str] = []
        seen: set[str] = set()
        for m in _ALLCAPS_RE.finditer(text):
            tok = m.group(0)
            if tok in _KNOWN_OK or tok in seen or _ROMAN_RE.match(tok):
                continue
            # A token next to a digit (e.g. part of a code) is treated as a
            # product code and kept silently.
            start, end = m.span()
            around = text[max(0, start - 1):min(len(text), end + 1)]
            if any(ch.isdigit() for ch in around):
                continue
            seen.add(tok)
            warnings.append(f"Unknown abbreviation '{tok}' requires review")
        return warnings


_instance: DutchAbbreviationResolver | None = None


def get_abbreviation_resolver() -> DutchAbbreviationResolver:
    global _instance
    if _instance is None:
        _instance = DutchAbbreviationResolver()
    return _instance
