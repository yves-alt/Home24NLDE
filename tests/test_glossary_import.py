"""Tests for the official DE→NL glossary import pipeline (PART 1 §9)."""

import io

import openpyxl
import pytest

from importers.glossary_importer import import_official_glossary, _looks_like_product_model
from database.database import get_connection


def _build_fixture_bytes(rows: list[tuple[str, str]]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Clean Technical Glossary"
    ws.append(["German term", "Dutch term"])
    for de, nl in rows:
        ws.append([de, nl])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


FIXTURE_ROWS = [
    ("Länge Haken:", "Lengte haken:"),        # colon label
    ("Klapptisch Raza", "Klaptafel Raza"),    # product + preserved model name
    ("Akazie Hell", "licht acaciahout"),      # ordinary 2-word phrase, not a model pair
    ("Ottomane", "Ottomane"),                 # DE == NL, no information
    ("Alabaster", "albast"),                  # general single-word vocabulary
    ("Bronze", "brons"),                      # duplicate source term (kept)
    ("Bronze", "bronskleurig"),               # duplicate source term (dropped, logged as conflict)
]


@pytest.fixture
def imported_stats():
    return import_official_glossary(_build_fixture_bytes(FIXTURE_ROWS))


def test_looks_like_product_model_uses_preserved_last_word():
    assert _looks_like_product_model("Klapptisch Raza", "Klaptafel Raza") is True
    assert _looks_like_product_model("Akazie Hell", "licht acaciahout") is False
    assert _looks_like_product_model("Beleuchteter Spiegel", "spiegel met verlichting") is False


def test_import_classification_counts(imported_stats):
    assert imported_stats["total"] == len(FIXTURE_ROWS)
    assert imported_stats["de_eq_nl_skipped"] == 1
    assert imported_stats["duplicates_skipped"] == 1
    assert imported_stats["labels_inserted"] == 1
    assert imported_stats["general_inserted"] == 3  # Akazie Hell, Alabaster, and the kept Bronze entry
    assert imported_stats["tm_pairs_inserted"] == 1


def test_conflicts_report_first_kept_and_dropped(imported_stats):
    conflicts = imported_stats["conflicts"]
    assert len(conflicts) == 1
    source, kept, dropped = conflicts[0]
    assert source == "Bronze"
    assert kept == "brons"
    assert dropped == "bronskleurig"


def test_colon_label_lands_in_glossary_table(imported_stats):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT target_term, category FROM glossary WHERE source_term='länge haken:'"
        ).fetchone()
    assert row is not None
    assert row["target_term"] == "Lengte haken:"
    assert row["category"] == "label"


def test_product_model_pair_lands_in_translation_memory(imported_stats):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT target_segment FROM translation_memory WHERE normalized_source='klapptisch raza'"
        ).fetchone()
    assert row is not None
    assert row["target_segment"] == "Klaptafel Raza"


def test_reimport_is_idempotent(imported_stats):
    with get_connection() as conn:
        before = conn.execute("SELECT COUNT(*) FROM glossary WHERE source_type='OFFICIAL_GLOSSARY'").fetchone()[0]
    import_official_glossary(_build_fixture_bytes(FIXTURE_ROWS))
    with get_connection() as conn:
        after = conn.execute("SELECT COUNT(*) FROM glossary WHERE source_type='OFFICIAL_GLOSSARY'").fetchone()[0]
    assert before == after
