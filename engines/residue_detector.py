import re
from dataclasses import dataclass


# Compound phrases must appear BEFORE their component words to get priority
GERMAN_RESIDUE_PATTERNS = [
    # ── Dimension label conversions (must come first to avoid partial matches) ──
    (r"\bB\s*[x×]\s*H\s*[x×]\s*T\b",     "B x H x D"),
    (r"\bLiegehöhe\b",                     "lighoogte"),
    (r"\bSitzhöhe\b",                      "zithoogte"),
    (r"\bArmlehnenh(?:ö)he\b",            "armleuninghoogte"),

    # ── Compounds (specific, high-priority) ───────────────────────────
    (r"\bbestehend\s+aus\b",               "bestaande uit"),
    (r"\bohne\s+Dekoration\b",             "zonder decoratie"),
    (r"\bmit\s+Dekoration\b",              "met decoratie"),
    (r"\binkl(?:usive)?\s+Montage\b",      "incl. montage"),
    (r"\bexkl(?:usive)?\s+Montage\b",      "excl. montage"),

    # ── German function words ─────────────────────────────────────────
    (r"\bohne\b",                          "zonder"),
    (r"\bund\b",                           "en"),
    (r"\boder\b",                          "of"),
    (r"\bmit\b(?!\s+\w+look)",             "met"),
    (r"\bfür\b",                           "voor"),
    (r"\bvon\b",                           "van"),
    (r"\baus\b",                           "van"),
    (r"\bauf\b",                           "op"),
    (r"\bnach\b",                          "naar"),
    (r"\bzu\b(?!\s+\w+look)",              "naar"),
    (r"\bein(?:e|em|en|er|es)?\b",         "een"),
    (r"\bist\b",                           "is"),
    (r"\bnicht\b",                         "niet"),
    (r"\bkein(?:e|em|en|er|es)?\b",        "geen"),
    (r"\bsehr\b",                          "zeer"),
    (r"\bgut\b",                           "goed"),
    (r"\binkl(?:usive)?\b",                "incl."),
    (r"\bexkl(?:usive)?\b",                "excl."),

    # ── German adjectives ─────────────────────────────────────────────
    (r"\bgroß\b",                          "groot"),
    (r"\bklein\b",                         "klein"),
    (r"\bneu\b",                           "nieuw"),
    (r"\balt\b",                           "oud"),
    (r"\bhoch\b",                          "hoog"),
    (r"\bniedrig\b",                       "laag"),
    (r"\bbreit\b",                         "breed"),
    (r"\btief\b",                          "diep"),
    (r"\bpraktisch\b",                     "praktisch"),
    (r"\bmodern\b",                        "modern"),
    (r"\bstilvoll\b",                      "stijlvol"),
    (r"\belegan[tz]\b",                    "elegant"),
    (r"\brobust\b",                        "robuust"),
    (r"\bkomfortabel\b",                   "comfortabel"),
    (r"\bmontiert\b",                      "gemonteerd"),
    (r"\bgeliefert\b",                     "geleverd"),
    (r"\blackiert\b",                      "gelakt"),
    (r"\bbeschichtet\b",                   "gecoat"),
    (r"\bfoliert\b",                       "gefolieerd"),
    (r"\bpulverbeschichtet\b",             "poedergecoat"),

    # ── German material names ─────────────────────────────────────────
    (r"\bMetall\b",                        "metaal"),
    (r"\bHolz\b",                          "hout"),
    (r"\bLeder\b",                         "leer"),
    (r"\bKunststoff\b",                    "kunststof"),

    # ── German color names (clearly German, unambiguous) ─────────────
    # Note: IGNORECASE is used, so all-caps variants are caught too
    (r"\bSchwarz\b",                       "zwart"),
    (r"\bWei[ß|ss]\b",                     "wit"),       # Weiß or Weiss
    (r"\bHellgrau\b",                      "lichtgrijs"),
    (r"\bDunkelgrau\b",                    "donkergrijs"),
    (r"\bGrau\b",                          "grijs"),
    (r"\bBraun\b",                         "bruin"),
    (r"\bGrün\b",                          "groen"),
    (r"\bOliv(?:grün)?\b",                 "olijfgroen"),
    (r"\bGelb\b",                          "geel"),
    (r"\bBlau\b",                          "blauw"),
    (r"\bHellblau\b",                      "lichtblauw"),
    (r"\bDunkelblau\b",                    "donkerblauw"),
    (r"\bRot\b",                           "rood"),
    (r"\bOrange\b",                        "oranje"),
    (r"\bRosa\b",                          "roze"),
    (r"\bLila\b",                          "lila"),
    (r"\bViolett\b",                       "paars"),
    (r"\bTürki(?:s|sch)\b",               "turquoise"),
    (r"\bSilber\b",                        "zilver"),
    (r"\bGold\b",                          "goud"),
    (r"\bSand(?:farben)?\b",               "zand"),
    (r"\bBei(?:ge)?\b",                    "beige"),
    (r"\bAnthrazit\b",                     "antraciet"),
    (r"\bSchwarzbraun\b",                  "zwartbruin"),
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

# Words that are unambiguously German and must never appear in Dutch output
CRITICAL_GERMAN_WORDS = re.compile(
    r"\b(?:ohne|Schwarz|Wei[ßs]s?|Grau|Hellgrau|Dunkelgrau|Braun|Grün|Gelb|Blau|Rot|Dekor"
    r"|Metall|Holz|Leder|Kunststoff|pulverbeschichtet|lackiert|beschichtet|Eiche|Nussbaum)\b",
    re.IGNORECASE,
)


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

    def has_critical_residue(self, text: str) -> list[str]:
        """Return list of critical German words still present after auto-fix."""
        cleaned = self.detect_and_clean(text, auto_fix=True).text
        return CRITICAL_GERMAN_WORDS.findall(cleaned)


_instance: GermanResidueDetector | None = None


def get_residue_detector() -> GermanResidueDetector:
    global _instance
    if _instance is None:
        _instance = GermanResidueDetector()
    return _instance
