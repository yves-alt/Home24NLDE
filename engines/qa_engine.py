import re
from dataclasses import dataclass, field
from database.database import get_connection


_METADATA_LEAK_RE = re.compile(
    r"(?mi)^(?:Categorie|Category|Product\s*categor(?:y|ie)|Product\s*type|Product\s*soort"
    r"|Context|Note|Explanation|Toelichting)\s*:.*$\n?"
)

# Strips parenthetical expansion after MDF — both German and Dutch explanations
_MDF_PAREN_RE = re.compile(r"\bMDF\s*\([^)]*\)", re.IGNORECASE)

FORBIDDEN_PATTERNS: dict[str, str] = {
    r"\bKeukeninsel\b": "kookeiland",
    r"\bDouchematt(?!e)\b": "douchemat",
    r"\bKookfeld\b": "kookplaat",
    r"\bKookkom\b": "braadpan",
    r"\bNotelaar\s+Dekor\b": "notenlook",
    r"\bZaagruw\s*Decor\b": "grof gezaagde look",
    r"\bDecor\b(?!\s*\w)": "look",
    r"\bDekor\b(?!\s*\w)": "look",
    r"\bIjzer\b(?!\s*hout)": "IJzer",
    r"\bIJs\b(?!\s*(?:koud|thee|blok|kast|water))": "ijs",
    r"\bBadewanne\b": "bad",
    r"\bWandschrank\b": "wandkast",
    r"\bTreppe\b": "trap",
}

GERMAN_WORDS_IN_NL = [
    r"\bund\b", r"\boder\b", r"\bmit\b", r"\bfür\b", r"\bvon\b",
    r"\bein(?:e|em|en|er|es)?\b",
    r"\bist\b", r"\bgroß\b", r"\bneu\b", r"\bhoch\b", r"\bbreit\b", r"\btief\b",
    r"\binkl\.\s*MwSt\b", r"\bzzgl\b", r"\bzzgl\.\b",
    r"\bMontage\b", r"\bVerpackung\b", r"\bLieferung\b",
    r"\bohne\b",
    r"\bSchwarz\b", r"\bWei[ßs]s?\b", r"\bGrau\b", r"\bBraun\b",
    r"\bGrün\b", r"\bGelb\b", r"\bBlau\b", r"\bRot\b",
    r"\bDekor\b",
]

PLURAL_CORRECTIONS: dict[str, str] = {
    r"\bstoels\b": "stoelen",
    r"\btafels\b": "tafels",
    r"\blampes\b": "lampen",
    r"\bkasten\b(?!\s+\w)": "kasten",
    r"\bregels\b": "rekken",
}

CAPITALIZATION_RULES: list[tuple[str, str]] = [
    (r"\bIjzer\b", "IJzer"),
    (r"\bIjsland\b", "IJsland"),
    (r"\b(de|het|een|van|in|op|met|voor|bij|over|door)\s+([A-Z])(?=[a-z])", lambda m: m.group(0).lower()),
]

AUTO_CORRECT_MAP: dict[str, str] = {
    **{p: r for p, r in FORBIDDEN_PATTERNS.items()},
    **{p: r for p, r in PLURAL_CORRECTIONS.items()},
}


def normalize_mdf_nl(text: str) -> str:
    """Remove parenthetical expansion after MDF and ensure uppercase."""
    text = _MDF_PAREN_RE.sub("MDF", text)
    text = re.sub(r"\bmdf\b", "MDF", text, flags=re.IGNORECASE)
    return text


# ── Home24 label normalizer ───────────────────────────────────────────
# Colon-form patterns FIRST so "Bezug: blau" doesn't partially match
# the standalone "Bezug" pattern.
_HOME24_LABEL_PATTERNS: list[tuple[re.Pattern, str]] = [
    # ── Label + colon (structural lines like "Bezug: beige<br>Füße: zwart") ──
    (re.compile(r"\bBezug\s*:",          re.IGNORECASE), "Bekleding:"),
    (re.compile(r"\bFüß(?:e|en)\s*:",   re.IGNORECASE), "Poten:"),
    (re.compile(r"\bFüss(?:e|en)\s*:",  re.IGNORECASE), "Poten:"),
    (re.compile(r"\bFuß\s*:",            re.IGNORECASE), "Poot:"),
    (re.compile(r"\bGestell\s*:",        re.IGNORECASE), "Frame:"),
    (re.compile(r"\bKorpus\s*:",         re.IGNORECASE), "Body:"),
    (re.compile(r"\bFarbe\s*:",          re.IGNORECASE), "Kleur:"),
    (re.compile(r"\bMaterial\s*:",       re.IGNORECASE), "Materiaal:"),
    (re.compile(r"\bArbeitsplatte\s*:",  re.IGNORECASE), "Werkblad:"),
    (re.compile(r"\bSitzfläche\s*:",     re.IGNORECASE), "Zitvlak:"),
    (re.compile(r"\bRückenlehne\s*:",    re.IGNORECASE), "Rugleuning:"),
    (re.compile(r"\bArmlehne\s*:",       re.IGNORECASE), "Armleuning:"),
    (re.compile(r"\bKopfteil\s*:",       re.IGNORECASE), "Hoofdeinde:"),
    (re.compile(r"\bMatratze\s*:",       re.IGNORECASE), "Matras:"),
    (re.compile(r"\bTischplatte\s*:",    re.IGNORECASE), "Tafelblad:"),
    (re.compile(r"\bSchubladen\s*:",     re.IGNORECASE), "Laden:"),
    (re.compile(r"\bSchublade\s*:",      re.IGNORECASE), "Lade:"),
    (re.compile(r"\bTüren\s*:",          re.IGNORECASE), "Deuren:"),
    (re.compile(r"\bTür\s*:",            re.IGNORECASE), "Deur:"),
    (re.compile(r"\bLieferumfang\s*:",   re.IGNORECASE), "Leveringsomvang:"),
    (re.compile(r"\bMaße\s*:",           re.IGNORECASE), "Afmetingen:"),
    (re.compile(r"\bBreite\s*:",         re.IGNORECASE), "Breedte:"),
    (re.compile(r"\bHöhe\s*:",           re.IGNORECASE), "Hoogte:"),
    (re.compile(r"\bTiefe\s*:",          re.IGNORECASE), "Diepte:"),
    # ── Standalone labels (without colon) ────────────────────────────
    (re.compile(r"\bBezug\b",            re.IGNORECASE), "bekleding"),
    (re.compile(r"\bFüße\b",             re.IGNORECASE), "poten"),
    (re.compile(r"\bFüsse\b",            re.IGNORECASE), "poten"),
    (re.compile(r"\bFuß\b",              re.IGNORECASE), "poot"),
    (re.compile(r"\bGestell\b",          re.IGNORECASE), "frame"),
    (re.compile(r"\bKorpus\b",           re.IGNORECASE), "body"),
    (re.compile(r"\bFarbe\b",            re.IGNORECASE), "kleur"),
    (re.compile(r"\bMaterial\b",         re.IGNORECASE), "materiaal"),
    (re.compile(r"\bArbeitsplatte\b",    re.IGNORECASE), "werkblad"),
    (re.compile(r"\bSitzfläche\b",       re.IGNORECASE), "zitvlak"),
    (re.compile(r"\bRückenlehne\b",      re.IGNORECASE), "rugleuning"),
    (re.compile(r"\bArmlehne\b",         re.IGNORECASE), "armleuning"),
    (re.compile(r"\bKopfteil\b",         re.IGNORECASE), "hoofdeinde"),
    (re.compile(r"\bMatratze\b",         re.IGNORECASE), "matras"),
    (re.compile(r"\bTischplatte\b",      re.IGNORECASE), "tafelblad"),
    (re.compile(r"\bSchubladen\b",       re.IGNORECASE), "laden"),
    (re.compile(r"\bSchublade\b",        re.IGNORECASE), "lade"),
    (re.compile(r"\bTüren\b",            re.IGNORECASE), "deuren"),
    (re.compile(r"\bTür\b",              re.IGNORECASE), "deur"),
    (re.compile(r"\bLieferumfang\b",     re.IGNORECASE), "leveringsomvang"),
    (re.compile(r"\bMaße\b",             re.IGNORECASE), "afmetingen"),
    (re.compile(r"\bBreite\b",           re.IGNORECASE), "breedte"),
    (re.compile(r"\bHöhe\b",             re.IGNORECASE), "hoogte"),
    (re.compile(r"\bTiefe\b",            re.IGNORECASE), "diepte"),
    # ── Material / textile terms ──────────────────────────────────────
    (re.compile(r"\bMicrofaser\b",       re.IGNORECASE), "microvezel"),
    (re.compile(r"\bVelours\b",          re.IGNORECASE), "velours"),
    (re.compile(r"\bSamtstoff\b",        re.IGNORECASE), "fluweel"),
    (re.compile(r"\bBaumwolle\b",        re.IGNORECASE), "katoen"),
    (re.compile(r"\bLeinen\b",           re.IGNORECASE), "linnen"),
    (re.compile(r"\bWolle\b",            re.IGNORECASE), "wol"),
    (re.compile(r"\bSeide\b",            re.IGNORECASE), "zijde"),
]

# German labels that must never appear in exported NL output
_CRITICAL_LABEL_RE = re.compile(
    r"\b(?:Bezug|Füße|Füsse|Fuß|Gestell|Korpus|Farbe|Microfaser"
    r"|Schublade|Schubladen|Lieferumfang|Maße|Breite|Höhe|Tiefe"
    r"|Arbeitsplatte|Sitzfläche|Rückenlehne|Armlehne|Kopfteil|Tischplatte"
    r"|Matratze|Baumwolle|Leinen|Wolle|Samtstoff)\b",
    re.IGNORECASE,
)


def normalize_home24_labels_nl(text: str) -> str:
    """Translate German product/furniture labels to Dutch deterministically.

    Handles both the colon-label form (Bezug: beige → Bekleding: beige)
    and standalone form (Bezug → bekleding).
    Preserves <br>, colons, dimensions, and overall structure.
    """
    if not text:
        return text
    result = text
    for pat, replacement in _HOME24_LABEL_PATTERNS:
        result = pat.sub(replacement, result)
    return result


def has_critical_label_residue(text: str) -> list[str]:
    """Return list of critical German labels still present in text."""
    return _CRITICAL_LABEL_RE.findall(text)


@dataclass
class QAIssue:
    issue_type: str
    original: str
    suggestion: str
    position: int = 0
    auto_fixable: bool = False


@dataclass
class QAResult:
    original: str
    corrected: str
    issues: list[QAIssue] = field(default_factory=list)
    was_modified: bool = False

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def has_critical(self) -> bool:
        return any(i.issue_type in ("german_residue", "forbidden_pattern", "hybrid", "metadata_leak") for i in self.issues)


class DutchQAEngine:

    def validate(self, translation: str, source: str = "") -> QAResult:
        if not translation:
            return QAResult(translation, translation)

        result = translation
        issues: list[QAIssue] = []

        # Must run first — strips injected metadata before other checks see it
        result, new_issues = self._check_metadata_leaks(result)
        issues.extend(new_issues)

        result, new_issues = self._check_mdf(result)
        issues.extend(new_issues)

        result, new_issues = self._check_forbidden(result)
        issues.extend(new_issues)

        result, new_issues = self._check_german_residue(result)
        issues.extend(new_issues)

        result, new_issues = self._check_capitalization(result)
        issues.extend(new_issues)

        result, new_issues = self._check_pluralization(result)
        issues.extend(new_issues)

        was_modified = result != translation
        return QAResult(translation, result, issues, was_modified)

    def _check_metadata_leaks(self, text: str) -> tuple[str, list[QAIssue]]:
        issues = []
        for m in _METADATA_LEAK_RE.finditer(text):
            issues.append(QAIssue("metadata_leak", m.group(0).strip(), "", m.start(), True))
        cleaned = _METADATA_LEAK_RE.sub("", text).strip()
        return cleaned, issues

    def _check_mdf(self, text: str) -> tuple[str, list[QAIssue]]:
        issues = []
        cleaned = normalize_mdf_nl(text)
        if cleaned != text:
            issues.append(QAIssue("mdf_normalization", text, cleaned, 0, True))
        return cleaned, issues

    def _check_forbidden(self, text: str) -> tuple[str, list[QAIssue]]:
        issues = []
        for pattern, correction in FORBIDDEN_PATTERNS.items():
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                issues.append(QAIssue("forbidden_pattern", m.group(0), correction, m.start(), True))
                text = re.sub(pattern, correction, text, flags=re.IGNORECASE)
        return text, issues

    def _check_german_residue(self, text: str) -> tuple[str, list[QAIssue]]:
        issues = []
        for pattern in GERMAN_WORDS_IN_NL:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                issues.append(QAIssue("german_residue", m.group(0), "", m.start(), False))
        return text, issues

    def _check_capitalization(self, text: str) -> tuple[str, list[QAIssue]]:
        issues = []
        for pattern, correction in CAPITALIZATION_RULES:
            if callable(correction):
                new = re.sub(pattern, correction, text)
            else:
                new = re.sub(pattern, correction, text)
            if new != text:
                issues.append(QAIssue("capitalization", text, new, 0, True))
                text = new
        return text, issues

    def _check_pluralization(self, text: str) -> tuple[str, list[QAIssue]]:
        issues = []
        for pattern, correction in PLURAL_CORRECTIONS.items():
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                issues.append(QAIssue("pluralization", m.group(0), correction, m.start(), True))
                text = re.sub(pattern, correction, text, flags=re.IGNORECASE)
        return text, issues

    def validate_batch(self, pairs: list[tuple[str, str]]) -> list[QAResult]:
        return [self.validate(t, s) for s, t in pairs]

    def log_issues(self, filename: str, row_num: int, result: QAResult):
        for issue in result.issues:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO qa_log (filename, row_num, issue_type, original, corrected, auto_fixed) VALUES (?,?,?,?,?,?)",
                    (filename, row_num, issue.issue_type, issue.original, issue.suggestion, 1 if issue.auto_fixable else 0),
                )


def run_final_quality_gate(dutch: str, source: str = "") -> list[str]:
    """Run all QA checks on a final Dutch translation. Returns list of issue descriptions."""
    if not dutch:
        return []
    from engines.residue_detector import get_residue_detector
    detector = get_residue_detector()
    residue = detector.detect_and_clean(dutch, auto_fix=False)
    issues = []
    if residue.german_residues:
        for w in residue.german_residues:
            issues.append(f"German residue '{w}'")
    if residue.hybrids:
        for w in residue.hybrids:
            issues.append(f"Hybrid form '{w}'")
    qa = get_qa_engine()
    result = qa.validate(dutch, source)
    for issue in result.issues:
        if issue.issue_type in ("german_residue", "forbidden_pattern", "metadata_leak", "mdf_normalization"):
            issues.append(f"{issue.issue_type}: '{issue.original}'")
    return issues


_instance: DutchQAEngine | None = None


def get_qa_engine() -> DutchQAEngine:
    global _instance
    if _instance is None:
        _instance = DutchQAEngine()
    return _instance
