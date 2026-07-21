"""Tests for file-level consistency harmonization (PART 1 §18)."""

from engines.nl.types import CellResult
from engines.nl.consistency_engine import harmonize


def test_majority_target_wins():
    cells = [
        CellResult(row=1, column="colorDetail", source="Schwarz", target="zwart", origin="TERMINOLOGY"),
        CellResult(row=2, column="colorDetail", source="Schwarz", target="zwart", origin="TERMINOLOGY"),
        CellResult(row=3, column="colorDetail", source="Schwarz", target="zwartig", origin="GPT"),
    ]
    report = harmonize(cells)
    assert all(c.target == "zwart" for c in cells)
    assert report.cells_harmonized == 1
    assert len(report.rewrites) == 1


def test_already_consistent_cells_untouched():
    cells = [
        CellResult(row=1, column="materialDetail", source="Eiche", target="eikenhout", origin="TERMINOLOGY"),
        CellResult(row=2, column="materialDetail", source="Eiche", target="eikenhout", origin="TERMINOLOGY"),
    ]
    report = harmonize(cells)
    assert report.cells_harmonized == 0
    assert cells[0].target == cells[1].target == "eikenhout"


def test_different_columns_not_cross_harmonized():
    cells = [
        CellResult(row=1, column="colorDetail", source="Schwarz", target="zwart", origin="TERMINOLOGY"),
        CellResult(row=2, column="materialDetail", source="Schwarz", target="zwart-achtig", origin="GPT"),
    ]
    report = harmonize(cells)
    assert report.cells_harmonized == 0  # different column profiles — not the same group


def test_tie_break_prefers_higher_confidence_origin():
    cells = [
        CellResult(row=1, column="name", source="Tischleuchte Nova", target="Tafellamp Nova", origin="TM_EXACT"),
        CellResult(row=2, column="name", source="Tischleuchte Nova", target="Tafellamp Novaa", origin="GPT"),
    ]
    report = harmonize(cells)
    # 1-1 tie on frequency — TM_EXACT outranks GPT, so its target should win.
    assert all(c.target == "Tafellamp Nova" for c in cells)
