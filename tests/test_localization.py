"""Regression + component tests for the Home24.nl localization engine.

The deterministic pipeline (terminology + model protection + adaptive TM +
abbreviations) resolves the PART 17 acceptance cases without any API call, so
these tests run fully offline (GPT disabled).
"""

import csv
import io

import pytest

from engines.nl.localization_engine import DutchLocalizationEngine
from engines.nl.terminology import get_terminology
from engines.nl.model_protector import get_model_protector
from engines.nl.adaptive_tm import get_adaptive_tm, TMKind
from engines.nl.abbreviations import get_abbreviation_resolver
from engines.nl.product_name_engine import get_product_name_engine
from engines.nl.residue_gate import get_residue_gate
from engines.nl.info_preservation import get_info_validator
from engines.nl.quality_gate import get_quality_gate
from engines.nl import segmentation
from engines.nl.gpt_client import NLGptClient
from engines.nl.types import CellResult


@pytest.fixture(scope="module")
def engine():
    return DutchLocalizationEngine(use_gpt=False)


# ── PART 17 acceptance cases (deterministic) ───────────────────────────

PART17 = [
    ("name", "Tischleuchte Paku", "Tafellamp Paku"),
    ("name", "Steckerleuchte Pilo", "Stekkerlamp Pilo"),
    ("name", "Deckenleuchte Banyo", "Plafondlamp Banyo"),
    ("name", "Einbauleuchte Fit Move II 3er-Set", "Inbouwlamp Fit Move II set van 3"),
    ("colorDetail", "Milchglas / Eisen - 2-flammig", "melkglas/IJzer - 2-lichts"),
    ("name", "Singleküche Ingrid 180 cm mit Mikrowelle", "Mini keuken Ingrid 180 cm met magnetron"),
    ("name", "Singleküche Ingrid 150 cm + Bartisch", "Mini keuken Ingrid 150 cm + bartafel"),
    ("materialDetail", "Eiche Nordic Dekor", "Nordic eikenlook"),
    ("materialDetail", "Eiche Hell Dekor", "lichte eikenlook"),
    ("materialDetail", "Marmor Weiß Dekor", "witte marmerlook"),
    ("materialDetail", "Altholz Dekor", "oud-houtlook"),
    ("colorDetail", "Bezug: beige<br>Füße: schwarz", "Bekleding: beige<br>Poten: zwart"),
]

# Additional regression cases beyond Part 17.
EXTRA_CASES = [
    ("materialDetail", "Marmor Schwarz Dekor", "zwarte marmerlook"),
    ("materialDetail", "Eiche Sägerau Dekor", "grof gezaagde eikenlook"),
    ("materialDetail", "Nussbaum Dekor", "notenlook"),
    ("materialDetail", "Beton Dekor", "betonlook"),
    ("colorDetail", "Hellbraun", "lichtbruin"),
    ("colorDetail", "Schwarzbraun", "zwartbruin"),
    ("otherMeasurements", "Maße B x H x T", "Afmetingen B x H x D"),
    ("otherMeasurements", "Maße (B x H x T)", "afmetingen (B x H x D)"),
    ("name", "Eck-Wandregal Arik", "Open hoek-wandkast Arik"),
    ("name", "Wandregal Levin", "Open wandkast Levin"),
    ("deliveryScope", "Kombi aus Tisch und Stuhl", "combinatie van tafel en stoel"),
]


@pytest.mark.parametrize("column,source,expected", PART17)
def test_part17_cases(engine, column, source, expected):
    result = engine.translate_cell(1, column, source)
    assert result.target == expected
    # No German residue may remain.
    assert get_residue_gate().scan(result.target) == []


def test_part17_all_pass_quality_gate(engine):
    cells = [engine.translate_cell(i + 1, col, src) for i, (col, src, _) in enumerate(PART17)]
    report = get_quality_gate().evaluate(cells)
    assert report.passed, [(i.row, i.issue) for i in report.issues]


@pytest.mark.parametrize("column,source,expected", EXTRA_CASES)
def test_extra_regression_cases(engine, column, source, expected):
    result = engine.translate_cell(1, column, source)
    assert result.target.lower() == expected.lower(), (
        f"[{column}] '{source}' → got '{result.target}', expected '{expected}'"
    )
    assert get_residue_gate().scan(result.target) == []


# ── terminology brain ───────────────────────────────────────────────────

def test_terminology_colon_vs_standalone_label():
    t = get_terminology()
    assert t.apply("Bezug: beige")[0] == "Bekleding: beige"
    assert t.apply("bekleding van Bezug")[0] == "bekleding van bekleding"


def test_terminology_flags_remaining_german():
    t = get_terminology()
    assert "Bezug" in get_terminology().remaining_german("dit is Bezug")


def test_terminology_critical_german_new_words():
    t = get_terminology()
    # New additions to CRITICAL_GERMAN must be detected.
    for word in ("Altholz", "Eisen", "Marmor", "Stahl", "Seide", "Violett",
                 "Schwarzbraun", "Mehrfarbig", "Hell", "Dunkel", "Anthrazit"):
        found = t.remaining_german(f"stoel {word} tafel")
        assert word in found or word.lower() in [w.lower() for w in found], (
            f"'{word}' not detected as German residue"
        )


def test_terminology_phrase_marmor_variants():
    t = get_terminology()
    assert t.apply("Marmor Weiß Dekor")[0] == "witte marmerlook"
    assert t.apply("Marmor Weiss Dekor")[0] == "witte marmerlook"
    assert t.apply("Marmor Schwarz Dekor")[0] == "zwarte marmerlook"
    assert t.apply("Altholz Dekor")[0] == "oud-houtlook"
    assert t.apply("Eiche Sägerau Dekor")[0] == "grof gezaagde eikenlook"


def test_terminology_flammig_conversion():
    t = get_terminology()
    assert t.apply("1-flammig")[0] == "1-lichts"
    assert t.apply("3-flammig")[0] == "3-lichts"
    assert t.apply("Deckenleuchte 5-flammig")[0] == "plafondlamp 5-lichts"


# ── model protector ─────────────────────────────────────────────────────

def test_model_protector_roundtrip_and_preservation():
    p = get_model_protector()
    src = "Mini keuken Ingrid 180 cm met magnetron"
    prot = p.protect(src)
    assert prot.model_names == ["Ingrid"]
    assert p.restore(prot.text, prot.mapping) == src


def test_model_protector_digit_first_not_a_model():
    p = get_model_protector()
    prot = p.protect("Einbauleuchte Fit Move II 3er-Set")
    assert prot.model_names == ["Fit Move II"]   # "3er-Set" left for the abbrev resolver


def test_model_protector_does_not_mask_prose_nouns():
    # German prose capitalizes every noun; these must NOT be treated as models
    # (otherwise GPT can't translate them).
    p = get_model_protector()
    prot = p.protect("Dieser elegante Esstisch bietet viel Stauraum und Atmosphäre im Wohnzimmer.")
    assert prot.model_names == []


# ── adaptive TM ──────────────────────────────────────────────────────────

def test_adaptive_tm_preserves_current_model():
    tm = get_adaptive_tm()
    res = tm.lookup("Tischleuchte Paku")
    if res.kind == TMKind.ADAPTED:               # depends on TM contents
        assert res.target.endswith("Paku")
        assert "Ledo" not in res.target and "Baldo" not in res.target


def test_adaptive_tm_no_blind_copy_on_unknown():
    tm = get_adaptive_tm()
    assert tm.lookup("volledig onbekende zin zonder match").kind == TMKind.NONE


# ── abbreviations ────────────────────────────────────────────────────────

def test_abbreviations():
    ab = get_abbreviation_resolver()
    assert ab.resolve("3er-Set").text == "set van 3"
    assert ab.resolve("Maße B x H x T").text == "Maße B x H x D"
    assert ab.resolve("Küche mit MW").text == "Küche mit magnetron"


def test_abbreviations_flags_unknown():
    ab = get_abbreviation_resolver()
    assert any("requires review" in w for w in ab.resolve("Stoel XYZ").warnings)
    assert ab.resolve("Lamp II").warnings == []   # roman numeral, not flagged


# ── product name engine ──────────────────────────────────────────────────

def test_name_engine_enforces_limit_and_endings():
    ne = get_product_name_engine()
    r = ne.optimize("tafellamp Paku met")
    assert r.name == "Tafellamp Paku"
    long = ne.optimize("Mini keuken Ingrid 300 cm met magnetron en vaatwasser en koelkast extra")
    assert len(long.name) <= 40
    assert long.was_shortened


def test_name_engine_no_brackets_or_commas():
    ne = get_product_name_engine()
    r = ne.optimize("Bank Oslo (3-zits), grijs")
    assert "(" not in r.name and "," not in r.name


# ── residue gate ─────────────────────────────────────────────────────────

def test_residue_gate_autofix_and_block():
    gate = get_residue_gate()
    report = gate.autofix("Tischleuchte mit Milchglas ohne Dekor")
    assert report.is_clean
    assert report.text == "tafellamp met melkglas zonder look"
    # A word the brain cannot fix stays flagged.
    assert gate.scan("Sofa Bezug") == ["Bezug"]


# ── information preservation ──────────────────────────────────────────────

def test_info_preservation_numbers_colors_models():
    iv = get_info_validator()
    assert iv.validate("Tafel 85 cm", "Tafel breed").issues  # number lost
    assert iv.validate("Tafel 85 cm", "Tafel 85 cm").ok
    assert iv.validate("Stoel Hellbraun", "Stoel groen").issues  # wrong color
    assert iv.validate("Stoel Hellbraun", "Stoel lichtbruin").ok   # correct color
    assert iv.validate("Lamp Paku", "Lamp", model_names=["Paku"]).issues  # model lost


def test_info_preservation_dimension_label():
    iv = get_info_validator()
    assert iv.validate("Maße B x H x T: 80 x 60 x 40 cm", "Afmetingen B x H x D: 80 x 60 x 40 cm").ok
    assert iv.validate("Maße B x H x T: 80 x 60 x 40 cm", "Afmetingen B x H x T: 80 x 60 x 40 cm").issues


def test_info_preservation_appliance_abbrev():
    iv = get_info_validator()
    assert iv.validate("Küche mit MW und GSP", "Keuken met magnetron en vaatwasser").ok
    assert iv.validate("Küche mit MW", "Keuken met koelkast").issues  # MW not expanded


# ── quality gate ─────────────────────────────────────────────────────────

def test_quality_gate_blocks_residue_and_name_violation():
    qg = get_quality_gate()
    bad = [
        CellResult(1, "name", "Tischleuchte Paku", "tafellamp Paku met", model_names=["Paku"]),
        CellResult(2, "colorDetail", "Bezug: beige", "Bezug: beige"),
    ]
    report = qg.evaluate(bad)
    assert not report.passed
    assert report.issue_count >= 2


def test_quality_gate_passes_clean_cell():
    qg = get_quality_gate()
    good = [CellResult(1, "name", "Tischleuchte Paku", "Tafellamp Paku", model_names=["Paku"])]
    assert qg.evaluate(good).passed


# ── segmentation ─────────────────────────────────────────────────────────

def test_segmentation_preserves_br():
    parts = segmentation.split("a<br>b")
    assert [p.kind for p in parts] == ["text", "sep", "text"]
    assert segmentation.join(parts) == "a<br>b"


# ── GPT client never returns German on failure ───────────────────────────

def test_gpt_client_failure_is_explicit_not_german():
    client = NLGptClient()
    client.set_key("")          # force unavailable
    assert not client.available
    res = client.translate("Tischleuchte mit Milchglas")
    assert res.ok is False
    assert res.text is None     # never the German source


# ── CSV export integrity ──────────────────────────────────────────────────

def test_csv_export_columns_and_exclude_name():
    from exporters.csv_export import generate_csv_bytes
    headers = ["articleNumber", "name", "colorDetail"]
    data_rows = [{"articleNumber": "A1", "name": "Tafel, groot", "colorDetail": "rot"}]
    tmap = {0: {"name": "Mini keuken\nIngrid", "colorDetail": "rood"}}

    raw = generate_csv_bytes(headers, data_rows, tmap).decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(raw)))
    assert rows[0]["articleNumber"] == "A1"
    assert rows[0]["colorDetail"] == "rood"
    assert rows[0]["name"] == "Mini keuken\nIngrid"   # multiline field intact

    no_name = generate_csv_bytes(headers, data_rows, tmap, exclude_columns=["name"]).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(no_name))
    assert "name" not in reader.fieldnames
    assert "colorDetail" in reader.fieldnames
