"""Tests for the rebuilt product-name compression engine (PART 2 §1-9, §26 C)."""

import pytest

from engines.nl.product_name_engine import get_product_name_engine, MAX_NAME_LENGTH
from engines.nl.types import Severity


@pytest.fixture
def engine():
    return get_product_name_engine()


def test_under_limit_untouched(engine):
    res = engine.optimize("Tafellamp Paku", model_names=["Paku"])
    assert res.name == "Tafellamp Paku"
    assert not res.was_shortened


def test_exactly_40_chars_untouched(engine):
    name = "A" * 39 + "B"  # exactly 40
    assert len(name) == 40
    res = engine.optimize(name)
    assert res.name == name
    assert not res.was_shortened


def test_over_limit_compresses_to_valid_length(engine):
    res = engine.optimize(
        "Salontafel Halburn van massief eikenhout met opbergruimte en wielen",
        source="Couchtisch Halburn aus massivem Eichenholz mit Stauraum und Rollen",
        model_names=["Halburn"], row=1,
    )
    assert len(res.name) <= MAX_NAME_LENGTH
    assert res.was_shortened
    assert "Halburn" in res.name


def test_several_accessories_drops_lowest_priority_first(engine):
    res = engine.optimize(
        "Hoogslaper Sam met ladekast en open kast en extra lattenbodem en led verlichting",
        model_names=["Sam"], row=1,
    )
    assert len(res.name) <= MAX_NAME_LENGTH
    assert "Sam" in res.name
    assert res.compression_event is not None
    assert res.compression_event.strategy != "emergency word-boundary truncation"


def test_long_model_name_preserved(engine):
    res = engine.optimize(
        "Inbouwlamp Fit Move II set van 3 met dimmer en afstandsbediening en montageset",
        model_names=["Fit Move II"], row=1,
    )
    assert "Fit Move II" in res.name
    assert len(res.name) <= MAX_NAME_LENGTH


def test_opt_preserved_when_room_exists(engine):
    res = engine.optimize(
        "Bureau Halburn met lade en wielen opt.",
        source="Schreibtisch Halburn mit Lade und Rollen opt.",
        model_names=["Halburn"], row=1,
    )
    assert "opt." in res.name


def test_opt_loss_escalates_to_critical_when_no_room(engine):
    res = engine.optimize(
        "Salontafel Halburn van massief eikenhout met opbergruimte en wielen opt.",
        source="Couchtisch Halburn aus massivem Eichenholz mit Stauraum und Rollen opt.",
        model_names=["Halburn"], row=1,
    )
    assert "opt." not in res.name
    assert any("opt." in w for w in res.warnings)
    assert res.compression_event.severity == Severity.CRITICAL


@pytest.mark.parametrize("bad_name,expected_issue_substring", [
    ("Tafel met", "forbidden word"),
    ("Tafel  Dubbel", "doubled spaces"),
    ("Tafel (test", "unmatched brackets"),
    ("Tafel/", "dangling slash"),
    ("Tafel...", "trailing ellipsis"),
    ("A" * 41, "exceeds 40"),
])
def test_invalid_endings_and_malformation_detected(engine, bad_name, expected_issue_substring):
    issues = engine.validate(bad_name)
    assert any(expected_issue_substring in i for i in issues)


def test_opt_never_stripped_as_forbidden_ending(engine):
    assert engine.validate("Tafellamp Paku opt.") == []


def test_no_recognized_product_type_still_bounded(engine):
    res = engine.optimize(
        "Onbekend artikel zonder herkenbaar producttype en zonder duidelijk model hier",
        model_names=[], row=1,
    )
    assert len(res.name) <= MAX_NAME_LENGTH


def test_no_model_name_still_compresses(engine):
    res = engine.optimize(
        "Salontafel van massief eikenhout met opbergruimte en decoratieve poten opt.",
        model_names=[], row=1,
    )
    assert len(res.name) <= MAX_NAME_LENGTH
    assert res.was_shortened


def test_quantity_preserved_when_possible(engine):
    res = engine.optimize(
        "Inbouwlamp Fit Move II set van 3 met accessoirepakket en montagehandleiding",
        model_names=["Fit Move II"], row=1,
    )
    assert "3" in res.name


def test_never_picks_shortest_candidate_blindly(engine):
    # 44 chars — fits once the single lowest-priority clause is dropped. The
    # engine must not jump straight to the head-only candidate ("Eettafel
    # Nova") when a less destructive drop already gets it under the limit.
    source = "Eettafel Nova van eikenhout met opbergruimte"
    assert len(source) > MAX_NAME_LENGTH
    res = engine.optimize(source, model_names=["Nova"], row=1)
    assert len(res.name) <= MAX_NAME_LENGTH
    assert res.name == "Eettafel Nova van eikenhout"
    assert "eikenhout" in res.name  # principal material kept, only the accessory dropped
