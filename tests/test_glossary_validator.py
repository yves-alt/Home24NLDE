"""Tests for post-translation glossary compliance validation (PART 2 §15)."""

from database.database import get_connection
from engines.nl.terminology import get_terminology
from engines.nl.glossary_validator import get_glossary_validator


def _seed_official_term(source_term: str, target_term: str):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO glossary "
            "(source_term, target_term, category, frequency, confidence, source_type, active) "
            "VALUES (?,?,?,100,0.98,'OFFICIAL_GLOSSARY',1)",
            (source_term.lower(), target_term, "general"),
        )
    get_terminology().reload()


def test_untranslated_glossary_term_is_corrected():
    _seed_official_term("alabaster", "albast")
    v = get_glossary_validator()
    r = v.validate("Vase aus Alabaster", "Vaas van Alabaster")
    assert r.target == "Vaas van albast"
    assert r.events[0].action == "corrected"


def test_approved_term_already_present_is_untouched():
    _seed_official_term("alabaster", "albast")
    v = get_glossary_validator()
    r = v.validate("Vase aus Alabaster", "Vaas van albast")
    assert r.target == "Vaas van albast"
    assert r.events == []


def test_unapproved_synonym_is_flagged_not_guessed():
    _seed_official_term("alabaster", "albast")
    v = get_glossary_validator()
    r = v.validate("Vase aus Alabaster", "Vaas van kalksteen")  # GPT used a different word
    assert r.target == "Vaas van kalksteen"  # not blindly rewritten
    assert r.events[0].action == "flagged"


def test_short_term_does_not_corrupt_unrelated_word():
    # Regression: a short/degenerate glossary row ("t" -> "D", a real
    # dimension-label abbreviation) must never do a raw substring replace
    # inside an unrelated word like "Salontafel".
    _seed_official_term("t", "D")
    v = get_glossary_validator()
    r = v.validate("Tisch t Halburn", "Salontafel Halburn")
    assert "Salontafel" in r.target
    assert "SalonDafel" not in r.target


def test_word_boundary_prevents_compound_false_match():
    _seed_official_term("tisch", "Tafel")
    v = get_glossary_validator()
    # "tisch" is not a standalone word in "Tischleuchte" / "Klapptisch" —
    # matching must respect word boundaries, not substring containment.
    r = v.validate("Tischleuchte Paku", "Tafellamp Paku")
    assert r.events == []
