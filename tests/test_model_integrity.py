"""Tests for the Model Name Integrity Validator (PART 2 §10)."""

from engines.nl.model_integrity import get_model_integrity_validator


def test_model_preserved():
    v = get_model_integrity_validator()
    r = v.validate("Klaptafel Sola", ["Sola"])
    assert r.ok


def test_model_missing_is_flagged():
    v = get_model_integrity_validator()
    r = v.validate("Klaptafel", ["Sola"])
    assert not r.ok
    assert any("missing" in i for i in r.issues)


def test_model_substitution_paku_to_baldo_is_flagged():
    v = get_model_integrity_validator()
    r = v.validate("Tafellamp Baldo", ["Paku"])
    assert not r.ok
    assert any("missing" in i for i in r.issues)
    assert any("baldo" in i.lower() and "substitution" in i for i in r.issues)


def test_multiword_model_words_not_flagged_as_substitution():
    # "Fit"/"Move" are curated model tokens used to compose "Fit Move II" —
    # they must not be flagged as unexpected substitutions when they're part
    # of the cell's OWN expected multi-word model.
    v = get_model_integrity_validator()
    r = v.validate("Inbouwlamp Fit Move II set van 3", ["Fit Move II"])
    assert r.ok


def test_duplicated_model_occurrence_flagged():
    v = get_model_integrity_validator()
    r = v.validate("Sola Sola tafel", ["Sola"])
    assert not r.ok
    assert any("duplication" in i for i in r.issues)


def test_no_models_is_trivially_ok():
    v = get_model_integrity_validator()
    r = v.validate("Salontafel van massief eikenhout", [])
    assert r.ok
