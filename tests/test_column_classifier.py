"""Tests for the dynamic column classifier (PART 1 §5/§7)."""

from engines.nl.column_classifier import ColumnKind, classify_columns, normalize_header


def test_protected_header_variants_all_match():
    # "Jira Key" / "JiraKey" / "jira_key" must resolve to the same protected key.
    assert normalize_header("Jira Key") == normalize_header("JiraKey") == normalize_header("jira_key")


def test_known_column_classified_directly():
    rows = [{"materialDetail": "Gestell aus Metall"}]
    result = classify_columns(["materialDetail"], rows)
    assert result[0].kind == ColumnKind.KNOWN_CONTENT


def test_name_column_is_product_name():
    rows = [{"name": "Tischleuchte Paku"}]
    result = classify_columns(["name"], rows)
    assert result[0].kind == ColumnKind.PRODUCT_NAME


def test_protected_metadata_never_reclassified():
    rows = [{"Jira Key": "HOME-123"}]
    result = classify_columns(["Jira Key"], rows)
    assert result[0].kind == ColumnKind.PROTECTED_METADATA


def test_unknown_german_prose_column_is_translatable():
    rows = [
        {"careInstructions": "Nicht in der Spülmaschine reinigen, nur mit einem feuchten Tuch abwischen."},
        {"careInstructions": "Regelmäßig abstauben und trocken lagern."},
    ]
    result = classify_columns(["careInstructions"], rows)
    assert result[0].kind == ColumnKind.UNKNOWN_CONTENT


def test_technical_column_not_translated():
    rows = [{"createdAt": "2024-01-01T00:00:00Z"}, {"createdAt": "2024-01-02T00:00:00Z"}]
    result = classify_columns(["createdAt"], rows)
    assert result[0].kind in (ColumnKind.PROTECTED_METADATA, ColumnKind.TECHNICAL_DATA)


def test_url_column_is_technical():
    rows = [{"imageUrlThumb": "https://cdn.example.com/a.jpg"}, {"imageUrlThumb": "https://cdn.example.com/b.jpg"}]
    result = classify_columns(["imageUrlThumb"], rows)
    assert result[0].kind == ColumnKind.TECHNICAL_DATA


def test_genuinely_ambiguous_column_is_flagged_not_dropped():
    rows = [{"mysteryColumn": "xJ29Q"}, {"mysteryColumn": "aQ88Z"}]
    result = classify_columns(["mysteryColumn"], rows)
    assert result[0].kind == ColumnKind.AMBIGUOUS


def test_empty_column_classified_empty():
    rows = [{"unused": None}, {"unused": ""}]
    result = classify_columns(["unused"], rows)
    assert result[0].kind == ColumnKind.EMPTY


def test_no_non_empty_column_is_dropped():
    headers = ["name", "Jira Key", "careInstructions", "createdAt", "mysteryColumn"]
    rows = [{
        "name": "Tischleuchte Paku", "Jira Key": "HOME-1",
        "careInstructions": "Nicht in der Spülmaschine reinigen.",
        "createdAt": "2024-01-01", "mysteryColumn": "xJ29Q",
    }]
    result = classify_columns(headers, rows)
    assert {c.header for c in result} == set(headers)
    assert all(c.kind != ColumnKind.EMPTY for c in result)
