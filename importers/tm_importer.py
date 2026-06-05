import re
import unicodedata
from datetime import datetime
from pathlib import Path

import openpyxl

from database.database import get_connection


PRODUCT_NAME_PATTERNS = [
    r"^[A-Z][a-z]+\s+[A-Z][a-z]+$",
    r"^(Stuhl|Tisch|Schrank|Sofa|Bett|Lampe|Regal)\s+[A-Z]",
]

CATEGORY_KEYWORDS = {
    "kitchen": ["küche", "keuken", "herd", "spüle", "schrank"],
    "bathroom": ["bad", "dusche", "wanne", "waschbecken", "badezimmer"],
    "bedroom": ["bett", "schlaf", "matratze", "kissen", "decke"],
    "living": ["sofa", "couch", "wohnzimmer", "fernseher", "tisch"],
    "outdoor": ["garten", "terrasse", "outdoor", "balkon"],
    "textile": ["stoff", "textil", "kissen", "decke", "vorhang"],
    "lighting": ["lampe", "leuchte", "licht", "led", "pendel"],
    "storage": ["schrank", "regal", "kommode", "schublade"],
    "color": ["farb", "farbig", "bunt", "weiss", "schwarz", "blau"],
    "material": ["holz", "metall", "stoff", "leder", "glas", "eiche"],
}


def normalize_segment(text: str) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s+", " ", text)
    return text


def detect_category(source: str, target: str) -> str:
    combined = (source + " " + target).lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            return cat
    return "general"


def import_tm_from_excel(filepath: str, progress_callback=None) -> dict:
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)

    sheet = None
    for name in wb.sheetnames:
        if "translation unit" in name.lower() or "tu" in name.lower():
            sheet = wb[name]
            break
    if sheet is None:
        sheet = wb.active

    rows = list(sheet.iter_rows(values_only=True))
    header = [str(c).lower() if c else "" for c in rows[0]]

    source_col = _find_col(header, ["source", "de-de", "source (de-de)", "deutsch"])
    target_col = _find_col(header, ["target", "nl-nl", "target (nl-nl)", "dutch", "dutch (nl-nl)"])
    date_col = _find_col(header, ["creation date", "created", "date"])
    modified_col = _find_col(header, ["modification date", "modified"])
    usage_col = _find_col(header, ["usage count", "usage", "frequency"])
    created_by_col = _find_col(header, ["created by", "author"])
    id_col = _find_col(header, ["id"])

    if source_col is None or target_col is None:
        raise ValueError(f"Could not find source/target columns. Headers: {header}")

    inserted = 0
    skipped = 0
    batch = []
    total = len(rows) - 1

    with get_connection() as conn:
        conn.execute("DELETE FROM translation_memory")

        for i, row in enumerate(rows[1:], 1):
            source = row[source_col] if source_col is not None else None
            target = row[target_col] if target_col is not None else None

            if not source or not target:
                skipped += 1
                continue

            source = str(source).strip()
            target = str(target).strip()

            if not source or not target:
                skipped += 1
                continue

            norm_src = normalize_segment(source)
            norm_tgt = normalize_segment(target)
            freq = int(row[usage_col]) if usage_col is not None and row[usage_col] is not None else 0
            category = detect_category(source, target)
            created = str(row[date_col]) if date_col is not None and row[date_col] else None
            modified = str(row[modified_col]) if modified_col is not None and row[modified_col] else None
            creator = str(row[created_by_col]) if created_by_col is not None and row[created_by_col] else None
            src_id = int(row[id_col]) if id_col is not None and row[id_col] is not None else None

            batch.append((source, target, norm_src, norm_tgt, freq, category, 1.0, created, modified, creator, src_id))

            if len(batch) >= 1000:
                conn.executemany(
                    "INSERT INTO translation_memory "
                    "(source_segment, target_segment, normalized_source, normalized_target, "
                    "frequency, category, confidence, created_at, modified_at, created_by, source_id) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    batch,
                )
                inserted += len(batch)
                batch = []
                if progress_callback:
                    progress_callback(i / total)

        if batch:
            conn.executemany(
                "INSERT INTO translation_memory "
                "(source_segment, target_segment, normalized_source, normalized_target, "
                "frequency, category, confidence, created_at, modified_at, created_by, source_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                batch,
            )
            inserted += len(batch)

    return {"inserted": inserted, "skipped": skipped, "total": total}


def _find_col(header: list, candidates: list) -> int | None:
    for c in candidates:
        for i, h in enumerate(header):
            if c in h:
                return i
    return None
