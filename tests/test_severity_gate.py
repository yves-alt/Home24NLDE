"""Tests for severity-classified quality gate status (PART 2 §12, §20)."""

from engines.nl.quality_gate import get_quality_gate
from engines.nl.types import CellResult


def _cell(**kwargs):
    defaults = dict(row=1, column="materialDetail", source="Gestell aus Metall",
                    target="frame uit metaal", origin="TERMINOLOGY", model_names=[], warnings=[])
    defaults.update(kwargs)
    return CellResult(**defaults)


def test_clean_cell_passes():
    gate = get_quality_gate()
    report = gate.evaluate([_cell()])
    assert report.status == "PASSED"
    assert report.passed


def test_residue_is_critical_and_blocks():
    gate = get_quality_gate()
    report = gate.evaluate([_cell(target="frame uit Metall")])
    assert report.status == "FAILED_CRITICAL"
    assert not report.passed
    assert any(i.severity.value == "CRITICAL" for i in report.issues)


def test_unresolved_review_warning_does_not_block():
    gate = get_quality_gate()
    report = gate.evaluate([_cell(warnings=["glossary: expected 'X' for 'y' — requires review"])])
    assert report.status == "PASSED_WITH_WARNINGS"
    assert report.passed  # warnings are visible but non-blocking


def test_coverage_error_is_always_critical():
    gate = get_quality_gate()
    report = gate.evaluate([_cell()], coverage_errors=["'name': 3 translated, 5 expected"])
    assert report.status == "FAILED_CRITICAL"
    assert not report.passed


def test_gpt_failed_cell_is_critical():
    gate = get_quality_gate()
    report = gate.evaluate([_cell(gpt_failed=True)])
    assert report.status == "FAILED_CRITICAL"


def test_suspicious_identical_output_is_warning_only():
    gate = get_quality_gate()
    report = gate.evaluate([_cell(
        source="Nicht in der Spülmaschine reinigen", target="Nicht in der Spülmaschine reinigen",
    )])
    # Same text un-translated AND containing German markers -> also residue (critical);
    # the identical-output classification itself is a warning-severity check.
    identical_issues = [i for i in report.issues if "identical" in i.issue]
    assert identical_issues and identical_issues[0].severity.value == "WARNING"


def test_info_events_never_block():
    from engines.nl.types import NameCompressionEvent, Severity
    gate = get_quality_gate()
    cell = _cell(column="name", source="Tafellamp Paku", target="Tafellamp Paku", model_names=["Paku"])
    cell.compression_event = NameCompressionEvent(severity=Severity.INFO)
    report = gate.evaluate([cell])
    assert report.status == "PASSED"
    assert report.info_events  # visible in the review panel, but not an "issue"
