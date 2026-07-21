"""Dynamic column classification (PART 1 §5/§7).

The workbook column set isn't fixed — Home24 exports can carry columns beyond
the curated `TRANSLATABLE_COLUMNS_NL` list (`careInstructions`,
`assemblyInformation`, …). Every non-empty column must get an explicit
classification and action; none may be silently skipped. Protected-header
matching normalizes whitespace/underscore/hyphen so "Jira Key" / "JiraKey" /
"jira_key" are recognized as the same column.
"""

import re
from dataclasses import dataclass, field
from enum import Enum

from engines.nl.terminology import GERMAN_MARKERS

# Columns with dedicated translation behavior today (name compression, delivery
# scope structure, etc.) — see localization_engine.COLUMN_RULES.
KNOWN_TRANSLATABLE_COLUMNS = frozenset({
    "name", "colorDetail", "deliveryScope", "otherMeasurements", "qualityDetail",
    "textileCompositionCover1", "variantName", "materialDetail", "textileComposition",
    "warningsAndSafetyInformation",
})

# Never translated, never sent to GPT, passed through unchanged.
PROTECTED_METADATA_COLUMNS = frozenset({
    "articleNumber", "Jira Key", "JiraKey", "SKU", "productId", "variantId", "ID",
    "EAN", "GTIN", "externalId", "URL", "imageUrl", "locale", "languageCode",
    "createdAt", "updatedAt", "sku", "id", "ean", "gtin",
})


class ColumnKind(str, Enum):
    PRODUCT_NAME = "PRODUCT_NAME"
    KNOWN_CONTENT = "KNOWN_CONTENT"
    UNKNOWN_CONTENT = "UNKNOWN_CONTENT"
    PROTECTED_METADATA = "PROTECTED_METADATA"
    TECHNICAL_DATA = "TECHNICAL_DATA"
    EMPTY = "EMPTY"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass
class ColumnClassification:
    header: str
    kind: ColumnKind
    sample_values: list = field(default_factory=list)
    reason: str = ""

    @property
    def translatable(self) -> bool:
        return self.kind in (ColumnKind.PRODUCT_NAME, ColumnKind.KNOWN_CONTENT, ColumnKind.UNKNOWN_CONTENT)


def normalize_header(h: str) -> str:
    """Lowercase and strip whitespace/zero-width/nbsp/_/- so header variants
    like 'Jira Key' / 'JiraKey' / 'jira_key' resolve to the same key."""
    h = (h or "").strip().replace("​", "").replace("\xa0", " ")
    return re.sub(r"[\s_\-]+", "", h.lower())


_KNOWN_NORM = {normalize_header(c): c for c in KNOWN_TRANSLATABLE_COLUMNS}
_PROTECTED_NORM = {normalize_header(c): c for c in PROTECTED_METADATA_COLUMNS}

_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DATE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?$|^\d{1,2}[./]\d{1,2}[./]\d{2,4}$"
)
_BOOL_RE = re.compile(r"^(true|false|ja|nein|yes|no)$", re.IGNORECASE)
_NUMERIC_RE = re.compile(r"^-?\d+([.,]\d+)?\s*(cm|mm|kg|g|%)?$", re.IGNORECASE)
_CODE_RE = re.compile(r"^[A-Za-z0-9]{2,}[-_][A-Za-z0-9-_]{1,}$|^[A-Z0-9]{6,}$")

_SAMPLE_SIZE = 20


def _is_technical_value(v: str) -> bool:
    v = v.strip()
    if not v:
        return False
    return bool(
        _URL_RE.match(v) or _EMAIL_RE.match(v) or _DATE_RE.match(v)
        or _BOOL_RE.match(v) or _NUMERIC_RE.match(v) or _CODE_RE.match(v)
    )


def _looks_translatable(v: str) -> bool:
    v = v.strip()
    if len(v) < 3:
        return False
    if GERMAN_MARKERS.search(v):
        return True
    # Prose heuristic: several space-separated alphabetic words.
    words = [w for w in re.split(r"\s+", v) if w.isalpha()]
    return len(words) >= 2


def classify_columns(headers: list, sample_rows: list) -> list:
    """Classify every header. `sample_rows` is a list of dicts keyed by header
    (as produced when parsing the workbook's data rows). No non-empty column
    is ever left unclassified."""
    results: list[ColumnClassification] = []
    for h in headers:
        if not h or not h.strip():
            continue
        norm = normalize_header(h)
        samples = [
            str(r.get(h)).strip() for r in sample_rows[:200]
            if r.get(h) is not None and str(r.get(h)).strip()
        ][:_SAMPLE_SIZE]

        if norm in _PROTECTED_NORM:
            results.append(ColumnClassification(h, ColumnKind.PROTECTED_METADATA, samples, "protected header"))
            continue
        if norm in _KNOWN_NORM:
            kind = ColumnKind.PRODUCT_NAME if norm == "name" else ColumnKind.KNOWN_CONTENT
            results.append(ColumnClassification(h, kind, samples, "known Home24 column"))
            continue
        if not samples:
            results.append(ColumnClassification(h, ColumnKind.EMPTY, samples, "no non-empty values"))
            continue

        technical_hits = sum(1 for v in samples if _is_technical_value(v))
        translatable_hits = sum(1 for v in samples if _looks_translatable(v))
        technical_score = technical_hits / len(samples)
        translatable_score = translatable_hits / len(samples)

        if technical_score >= 0.7 and translatable_score < 0.3:
            results.append(ColumnClassification(
                h, ColumnKind.TECHNICAL_DATA, samples,
                f"{technical_hits}/{len(samples)} sampled values look technical",
            ))
        elif translatable_score >= 0.3:
            results.append(ColumnClassification(
                h, ColumnKind.UNKNOWN_CONTENT, samples,
                f"{translatable_hits}/{len(samples)} sampled values look like German prose",
            ))
        else:
            results.append(ColumnClassification(
                h, ColumnKind.AMBIGUOUS, samples,
                "neither technical nor descriptive signal is strong enough — needs review",
            ))
    return results
