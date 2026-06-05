import re
from collections import defaultdict, Counter
from datetime import datetime

from database.database import get_connection
from importers.tm_importer import normalize_segment


BRAND_PATTERNS = [
    r"^[A-Z][a-z]+[A-Z]",
    r"\b(IKEA|Home24|Wayfair|Amazon)\b",
]

COLLECTION_SUFFIXES = [r"\b\w+ (Serie|Collection|Kollektion|Line)\b"]

MIN_TERM_LENGTH = 3
MIN_FREQUENCY = 2


def build_glossary_from_tm(progress_callback=None) -> dict:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT source_segment, target_segment, frequency FROM translation_memory"
        ).fetchall()

    term_pairs: dict[str, Counter] = defaultdict(Counter)

    for i, row in enumerate(rows):
        source = row["source_segment"]
        target = row["target_segment"]
        freq = row["frequency"] or 1

        src_parts = _split_segment(source)
        tgt_parts = _split_segment(target)

        if len(src_parts) == 1 and len(tgt_parts) == 1:
            src_term = src_parts[0].strip()
            tgt_term = tgt_parts[0].strip()
            if _is_valid_term(src_term) and _is_valid_term(tgt_term):
                term_pairs[src_term.lower()][tgt_term] += freq

        if progress_callback and i % 5000 == 0:
            progress_callback(i / len(rows))

    inserted = 0
    skipped = 0

    with get_connection() as conn:
        for src_lower, target_counter in term_pairs.items():
            if sum(target_counter.values()) < MIN_FREQUENCY:
                skipped += 1
                continue

            best_target, best_freq = target_counter.most_common(1)[0]
            category = _detect_term_category(src_lower)
            confidence = min(1.0, best_freq / max(sum(target_counter.values()), 1))

            try:
                conn.execute(
                    "INSERT OR IGNORE INTO glossary "
                    "(source_term, target_term, category, frequency, confidence, source_type) "
                    "VALUES (?,?,?,?,?,'TM')",
                    (src_lower, best_target, category, best_freq, confidence),
                )
                inserted += 1
            except Exception:
                skipped += 1

    return {"inserted": inserted, "skipped": skipped}


def _split_segment(text: str) -> list[str]:
    parts = re.split(r"<br\s*/?>|,\s*(?=[A-ZÜÄÖ])|/(?=[A-ZÜÄÖ])|(?<=\w)\s+-\s+(?=\w)", text)
    return [p.strip() for p in parts if p.strip()]


def _is_valid_term(term: str) -> bool:
    if len(term) < MIN_TERM_LENGTH:
        return False
    if re.match(r"^\d+$", term):
        return False
    for pattern in BRAND_PATTERNS:
        if re.search(pattern, term):
            return False
    for pattern in COLLECTION_SUFFIXES:
        if re.search(pattern, term, re.IGNORECASE):
            return False
    if re.match(r"^[A-Z][a-z]+ [A-Z][a-z]+$", term):
        return False
    return True


TERM_CATEGORIES = {
    "kitchen": ["küche", "keuken", "herd", "kochen"],
    "bathroom": ["bad", "dusch", "wanne", "sanitär"],
    "bedroom": ["bett", "schlaf", "matratze"],
    "color": ["farb", "weiss", "schwarz", "blau", "rot", "grün", "grau", "braun", "beige"],
    "material": ["holz", "metall", "stoff", "leder", "glas", "eiche", "buche", "kiefer", "mdf"],
    "furniture": ["sofa", "tisch", "stuhl", "schrank", "regal", "kommode"],
    "lighting": ["lampe", "leuchte", "licht", "led"],
    "textile": ["kissen", "decke", "vorhang", "teppich"],
}


def _detect_term_category(term: str) -> str:
    t = term.lower()
    for cat, kws in TERM_CATEGORIES.items():
        if any(kw in t for kw in kws):
            return cat
    return "general"


def import_glossary_from_excel(filepath: str) -> dict:
    import openpyxl
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    header = [str(c).lower() if c else "" for c in rows[0]]

    src_col = next((i for i, h in enumerate(header) if "source" in h or "de" in h or "german" in h), 0)
    tgt_col = next((i for i, h in enumerate(header) if "target" in h or "nl" in h or "dutch" in h), 1)
    cat_col = next((i for i, h in enumerate(header) if "cat" in h), None)

    inserted = 0
    with get_connection() as conn:
        for row in rows[1:]:
            src = str(row[src_col]).strip() if row[src_col] else None
            tgt = str(row[tgt_col]).strip() if row[tgt_col] else None
            cat = str(row[cat_col]).strip() if cat_col is not None and row[cat_col] else "general"
            if not src or not tgt:
                continue
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO glossary (source_term, target_term, category, source_type) VALUES (?,?,?,'IMPORTED')",
                    (src.lower(), tgt, cat),
                )
                inserted += 1
            except Exception:
                pass

    return {"inserted": inserted}
