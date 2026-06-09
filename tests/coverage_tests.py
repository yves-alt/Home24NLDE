"""Coverage and column-resolution tests for the single-source-of-truth column constants.

Run: python tests/coverage_tests.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.migrations import run_migrations
from ui.pages.translate_page import (
    TRANSLATABLE_COLUMNS_NL,
    PROTECTED_COLUMNS,
    HOME24_DETECTION_COLUMNS,
    _norm,
    _resolve_columns,
    _build_coverage,
    _validate_coverage,
)


# ── 1. Column-set membership ──────────────────────────────────────────

def test_column_membership():
    """materialDetail and textileComposition must be in TRANSLATABLE_COLUMNS_NL."""
    print("=== Column membership ===")
    must_have = [
        "materialDetail", "textileComposition",
        "name", "colorDetail", "deliveryScope", "otherMeasurements",
        "qualityDetail", "textileCompositionCover1", "variantName",
    ]
    passed = True
    for col in must_have:
        ok = col in TRANSLATABLE_COLUMNS_NL
        print(f"  {'PASS' if ok else 'FAIL'}  {col} in TRANSLATABLE_COLUMNS_NL")
        passed = passed and ok

    # articleNumber must NOT be translatable
    ok = "articleNumber" not in TRANSLATABLE_COLUMNS_NL
    print(f"  {'PASS' if ok else 'FAIL'}  articleNumber NOT in TRANSLATABLE_COLUMNS_NL")
    passed = passed and ok

    ok = "articleNumber" in PROTECTED_COLUMNS
    print(f"  {'PASS' if ok else 'FAIL'}  articleNumber in PROTECTED_COLUMNS")
    passed = passed and ok

    # Detection set must be a superset of both translatable and protected
    for col in TRANSLATABLE_COLUMNS_NL:
        ok = col in HOME24_DETECTION_COLUMNS
        if not ok:
            print(f"  FAIL  {col} missing from HOME24_DETECTION_COLUMNS")
            passed = False

    print(f"  TRANSLATABLE_COLUMNS_NL = {sorted(TRANSLATABLE_COLUMNS_NL)}")
    print()
    return passed


# ── 2. Header normalization ───────────────────────────────────────────

def test_norm():
    """_norm should strip, lowercase, and remove hidden chars."""
    print("=== Header normalization ===")
    cases = [
        ("materialDetail", "materialdetail"),
        ("  materialDetail  ", "materialdetail"),
        ("MaterialDetail", "materialdetail"),
        ("​materialDetail", "materialdetail"),     # zero-width space
        ("material\xa0Detail", "material detail"),     # non-breaking space
    ]
    passed = True
    for inp, expected in cases:
        got = _norm(inp)
        ok = got == expected
        print(f"  {'PASS' if ok else 'FAIL'}  _norm({inp!r}) → {got!r}  (expected {expected!r})")
        passed = passed and ok
    print()
    return passed


# ── 3. _resolve_columns — case-insensitive matching ───────────────────

def test_resolve_columns():
    """_resolve_columns must match headers regardless of capitalisation or whitespace."""
    print("=== _resolve_columns case-insensitive ===")
    raw_headers = [
        "articleNumber",       # protected (exact)
        "MaterialDetail",      # translatable (capital M)
        "materialdetail",      # translatable (all lowercase)
        " materialDetail ",    # translatable (padded)
        "VARIANTNAME",         # translatable (all caps)
        "colorDetail",         # translatable (exact)
        "unknownColumn",       # neither — should be ignored
        "weightNetto",         # detection-only col, not translatable
    ]

    translatable, protected = _resolve_columns(raw_headers)

    # materialDetail appears three times — all three should be in translatable
    print(f"  translatable: {translatable}")
    print(f"  protected: {protected}")

    passed = True

    # articleNumber → protected
    ok = "articleNumber" in protected
    print(f"  {'PASS' if ok else 'FAIL'}  articleNumber in protected")
    passed = passed and ok

    # All three materialDetail variants and variantName and colorDetail
    for h in ["MaterialDetail", "materialdetail", " materialDetail ", "VARIANTNAME", "colorDetail"]:
        ok = h in translatable
        print(f"  {'PASS' if ok else 'FAIL'}  {h!r} in translatable")
        passed = passed and ok

    # unknownColumn and weightNetto must not appear in either list
    for h in ["unknownColumn", "weightNetto"]:
        ok = h not in translatable and h not in protected
        print(f"  {'PASS' if ok else 'FAIL'}  {h!r} ignored (not translatable or protected)")
        passed = passed and ok

    print()
    return passed


# ── 4. Coverage validation logic ──────────────────────────────────────

def test_coverage_validation():
    """Coverage check must block export when translations are missing."""
    print("=== Coverage validation ===")
    passed = True

    data_rows = [
        {"materialDetail": "Metall, pulverbeschichtet", "colorDetail": "Schwarz"},
        {"materialDetail": "Kunststoff",                "colorDetail": "Weiß"},
    ]

    # Full coverage — no errors expected
    preview_full = [
        {"Row": 1, "Column": "materialDetail",  "German source": "Metall, pulverbeschichtet",  "Dutch translation": "gepoedercoat metaal",  "Confidence": "HIGH",   "Origin": "TM_EXACT"},
        {"Row": 1, "Column": "colorDetail",      "German source": "Schwarz",                    "Dutch translation": "zwart",                "Confidence": "HIGH",   "Origin": "TM_EXACT"},
        {"Row": 2, "Column": "materialDetail",   "German source": "Kunststoff",                 "Dutch translation": "kunststof",            "Confidence": "MEDIUM", "Origin": "AI"},
        {"Row": 2, "Column": "colorDetail",      "German source": "Weiß",                       "Dutch translation": "wit",                  "Confidence": "HIGH",   "Origin": "TM_EXACT"},
    ]
    errors = _validate_coverage(preview_full, data_rows, ["materialDetail", "colorDetail"])
    ok = len(errors) == 0
    print(f"  {'PASS' if ok else 'FAIL'}  Full coverage → no errors  (got {errors})")
    passed = passed and ok

    # Missing one materialDetail translation — should fail
    preview_gap = [
        {"Row": 1, "Column": "materialDetail",  "German source": "Metall, pulverbeschichtet",  "Dutch translation": "gepoedercoat metaal",  "Confidence": "HIGH",   "Origin": "TM_EXACT"},
        {"Row": 1, "Column": "colorDetail",      "German source": "Schwarz",                    "Dutch translation": "zwart",                "Confidence": "HIGH",   "Origin": "TM_EXACT"},
        # Row 2 materialDetail deliberately absent
        {"Row": 2, "Column": "colorDetail",      "German source": "Weiß",                       "Dutch translation": "wit",                  "Confidence": "HIGH",   "Origin": "TM_EXACT"},
    ]
    errors = _validate_coverage(preview_gap, data_rows, ["materialDetail", "colorDetail"])
    ok = any("materialDetail" in e for e in errors)
    print(f"  {'PASS' if ok else 'FAIL'}  Missing materialDetail row → error raised  (errors: {errors})")
    passed = passed and ok

    print()
    return passed


# ── 5. Integration: canonical translations ────────────────────────────

def test_canonical_translations():
    """Spot-check key German→Dutch translations via the full engine pipeline."""
    print("=== Canonical translation spot-checks ===")
    run_migrations()

    from engines.translation_engine import get_engine
    engine = get_engine()

    cases = [
        ("Metall, pulverbeschichtet",                     "gepoedercoat",           "materialDetail"),
        ("Polyester - Mehrfarbig - 53 x 53 cm",           "polyester",              "textileCompositionCover1"),
        ("meerdere kleuren",                              "meerdere kleuren",        None),   # Dutch passthrough
    ]

    passed = True
    for source, expected_fragment, col in cases:
        items = [(0, source)]
        try:
            batch = engine.translate_batch(items, context_rows=[], filename="test.xlsx")
            result = batch.results[0].target if batch.results else ""
        except Exception as exc:
            result = f"ERROR: {exc}"

        ok = expected_fragment.lower() in result.lower()
        label = f"'{source}' → '{result}'"
        print(f"  {'PASS' if ok else 'FAIL'}  {label}  (expected fragment: '{expected_fragment}')")
        passed = passed and ok

    # Verify "Mehrfarbig" → "meerdere kleuren" (crucial phrase-memory entry)
    items = [(0, "Mehrfarbig")]
    try:
        batch = engine.translate_batch(items, context_rows=[], filename="test.xlsx")
        result = batch.results[0].target if batch.results else ""
    except Exception as exc:
        result = f"ERROR: {exc}"
    ok = "meerdere kleuren" in result.lower()
    print(f"  {'PASS' if ok else 'FAIL'}  'Mehrfarbig' → '{result}'  (expected 'meerdere kleuren')")
    passed = passed and ok

    print()
    return passed


# ── Runner ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    results = [
        test_column_membership(),
        test_norm(),
        test_resolve_columns(),
        test_coverage_validation(),
        test_canonical_translations(),
    ]

    total = len(results)
    n_pass = sum(results)
    print("=" * 50)
    print(f"Coverage tests: {n_pass}/{total} passed")
    if n_pass < total:
        sys.exit(1)
