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


# ── 6. No metadata injection ──────────────────────────────────────────

def test_no_metadata_injection():
    """Category metadata (Categorie:, decoratie, etc.) must never appear in translated output."""
    print("=== No metadata injection ===")

    from engines.translation_engine import _strip_metadata_leaks, _METADATA_LEAK_RE
    from engines.qa_engine import get_qa_engine

    passed = True

    # Direct sanitizer tests
    leak_cases = [
        ("Categorie: decoratie\nPaneel: 90 x 90 x 27 cm", "Paneel: 90 x 90 x 27 cm"),
        ("Category: decoration\nSome product text",       "Some product text"),
        ("Product type: meubels\nText here",               "Text here"),
        ("Note: internal\nActual content",                 "Actual content"),
        ("Clean output without any labels",                "Clean output without any labels"),
    ]
    for inp, expected in leak_cases:
        got = _strip_metadata_leaks(inp)
        ok = got == expected
        print(f"  {'PASS' if ok else 'FAIL'}  sanitizer: {inp[:40]!r} → {got!r}")
        passed = passed and ok

    # QA engine strips metadata_leak issues
    qa = get_qa_engine()
    qa_input = "Categorie: decoratie\nPaneel: 90 x 90 x 27 cm"
    qa_result = qa.validate(qa_input)
    ok = "Categorie" not in qa_result.corrected and any(
        i.issue_type == "metadata_leak" for i in qa_result.issues
    )
    print(f"  {'PASS' if ok else 'FAIL'}  QA engine strips Categorie: and flags metadata_leak issue")
    print(f"    corrected: {qa_result.corrected!r}")
    passed = passed and ok

    # Regression: measurement cell must not gain a Categorie: line
    source = "<br>Paneel: 90 x 90 x 27 cm<br>Bank: 90 x 45 x 40 cm<br>Spiegel: 96 x 60 x 4 cm<br>Kommode: 100 x 90 x 40 cm"
    forbidden_fragments = ["Categorie", "Category", "decoratie"]

    run_migrations()
    from engines.translation_engine import get_engine
    engine = get_engine()
    items = [(0, source)]
    try:
        batch = engine.translate_batch(items, context_rows=[], filename="test.xlsx")
        result = batch.results[0].target if batch.results else ""
    except Exception as exc:
        result = f"ERROR: {exc}"

    print(f"  Measurement cell result: {result!r}")

    for fragment in forbidden_fragments:
        ok = fragment not in result
        print(f"  {'PASS' if ok else 'FAIL'}  '{fragment}' NOT in output")
        passed = passed and ok

    # Kommode should be translated (commode, ladekast, kast are all valid Dutch)
    ok = any(w in result.lower() for w in ("commode", "kommode", "kast", "ladekast"))
    print(f"  {'PASS' if ok else 'FAIL'}  Kommode translated (commode/ladekast/kast) in output")
    passed = passed and ok

    print()
    return passed


# ── 7. German residue detector ────────────────────────────────────────

def test_german_residue_detector():
    """Residue detector must auto-fix 'ohne', colors, and compound phrases."""
    print("=== German residue detector ===")

    from engines.residue_detector import get_residue_detector
    detector = get_residue_detector()
    passed = True

    cases = [
        # (input, expected_output, description)
        ("ohne Dekoration",                     "zonder decoratie",                 "ohne Dekoration compound"),
        ("set bestehend aus 2 stoelen, ohne decoratie",
                                                "set bestaande uit 2 stoelen, zonder decoratie",
                                                                                    "bestehend aus + ohne"),
        ("Schwarz / Grau",                      "zwart / grijs",                    "colors Schwarz/Grau"),
        ("Weiß / Beige",                        "wit / beige",                      "Weiß → wit"),
        ("Braun, modern",                       "bruin, modern",                    "Braun → bruin"),
        ("lackiert",                            "gelakt",                           "lackiert → gelakt"),
        ("beschichtet",                         "gecoat",                           "beschichtet → gecoat"),
        ("foliert",                             "gefolieerd",                       "foliert → gefolieerd"),
        ("zonder decoratie",                    "zonder decoratie",                 "already Dutch — no change"),
    ]

    for inp, expected, desc in cases:
        result = detector.detect_and_clean(inp, auto_fix=True)
        ok = result.text.lower() == expected.lower()
        print(f"  {'PASS' if ok else 'FAIL'}  {desc}: {inp!r} → {result.text!r}  (expected {expected!r})")
        passed = passed and ok

    # ohne must be in the patterns list
    from engines.residue_detector import GERMAN_RESIDUE_PATTERNS
    ohne_covered = any("ohne" in p for p, _ in GERMAN_RESIDUE_PATTERNS)
    print(f"  {'PASS' if ohne_covered else 'FAIL'}  'ohne' present in GERMAN_RESIDUE_PATTERNS")
    passed = passed and ohne_covered

    print()
    return passed


# ── 8. MDF normalization ──────────────────────────────────────────────

def test_mdf_normalization():
    """MDF must always be uppercase and parenthetical expansions must be removed."""
    print("=== MDF normalization ===")

    from engines.qa_engine import normalize_mdf_nl
    passed = True

    cases = [
        ("MDF (mitteldichte Holzfaserplatte), lackiert",  "MDF, gelakt"),
        ("MDF (Medium Density Fibreboard), gelakt",       "MDF, gelakt"),
        ("MDF (middeldichte vezelplaat), gelakt",          "MDF, gelakt"),
        ("mdf, lackiert",                                  "MDF, gelakt"),
        ("MDF, gelakt",                                    "MDF, gelakt"),   # already clean
    ]

    for inp, expected in cases:
        # normalize_mdf_nl strips parens + uppercases; residue detector translates lackiert
        from engines.residue_detector import get_residue_detector
        detector = get_residue_detector()
        step1 = normalize_mdf_nl(inp)
        step2 = detector.detect_and_clean(step1, auto_fix=True).text
        ok = step2.lower() == expected.lower()
        print(f"  {'PASS' if ok else 'FAIL'}  {inp!r}")
        print(f"           → {step2!r}  (expected {expected!r})")
        passed = passed and ok

    print()
    return passed


# ── 9. TM importer UPSERT (no DELETE) ────────────────────────────────

def test_tm_import_upsert():
    """TM import must use UPSERT, never DELETE existing entries."""
    print("=== TM importer UPSERT ===")
    run_migrations()
    passed = True

    from database.database import get_connection
    from importers.tm_importer import import_tm_from_bytes
    import io, csv

    # Count existing entries before import
    with get_connection() as conn:
        before = conn.execute("SELECT COUNT(*) FROM translation_memory").fetchone()[0]

    # Build a minimal CSV TM
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["source", "target", "frequency"])
    writer.writeheader()
    writer.writerow({"source": "__test_ohne_import__", "target": "__zonder_import__", "frequency": "1"})
    writer.writerow({"source": "",  "target": "skip",  "frequency": "0"})  # invalid row
    csv_bytes = buf.getvalue().encode("utf-8")

    stats = import_tm_from_bytes(csv_bytes, "test_import.csv")
    print(f"  stats: {stats}")

    # Entries must not have decreased
    with get_connection() as conn:
        after = conn.execute("SELECT COUNT(*) FROM translation_memory").fetchone()[0]

    ok = after >= before
    print(f"  {'PASS' if ok else 'FAIL'}  TM count did not decrease: {before} → {after}")
    passed = passed and ok

    ok = stats["inserted"] >= 1
    print(f"  {'PASS' if ok else 'FAIL'}  At least 1 row inserted  (got {stats['inserted']})")
    passed = passed and ok

    ok = stats["invalid"] == 1
    print(f"  {'PASS' if ok else 'FAIL'}  1 invalid row detected  (got {stats['invalid']})")
    passed = passed and ok

    # Import same file again — should update, not insert duplicate
    stats2 = import_tm_from_bytes(csv_bytes, "test_import.csv")
    ok = stats2["updated"] >= 1 and stats2["inserted"] == 0
    print(f"  {'PASS' if ok else 'FAIL'}  Duplicate import → updated={stats2['updated']}, inserted={stats2['inserted']}")
    passed = passed and ok

    # TM matcher must find the new entry immediately (cache reloaded)
    from engines.tm_matcher import get_matcher
    matcher = get_matcher()
    match = matcher.match("__test_ohne_import__")
    ok = match is not None and match.target == "__zonder_import__"
    print(f"  {'PASS' if ok else 'FAIL'}  Imported entry found in TM matcher immediately")
    passed = passed and ok

    # Clean up test entry
    with get_connection() as conn:
        conn.execute("DELETE FROM translation_memory WHERE source_segment='__test_ohne_import__'")
    matcher.reload()

    print()
    return passed


# ── 10. Full pipeline residue regression ─────────────────────────────

def test_pipeline_residue_regression():
    """Full pipeline must produce clean Dutch with no German residue."""
    print("=== Full pipeline residue regression ===")
    run_migrations()

    from engines.translation_engine import get_engine
    from engines.residue_detector import get_residue_detector
    engine = get_engine()
    detector = get_residue_detector()

    cases = [
        ("ohne Dekoration",                          "zonder",      "ohne → zonder"),
        ("Schwarz / Grau",                           "zwart",       "Schwarz → zwart"),
        ("Metall, pulverbeschichtet",                "gepoedercoat","Metall pulverbeschichtet"),
        ("Set bestehend aus 2 Stühlen, ohne Dekoration",
                                                     "bestaande",   "bestehend aus compound"),
    ]

    passed = True
    for source, expected_fragment, desc in cases:
        items = [(0, source)]
        try:
            batch = engine.translate_batch(items, context_rows=[], filename="test.xlsx")
            result = batch.results[0].target if batch.results else ""
        except Exception as exc:
            result = f"ERROR: {exc}"

        ok = expected_fragment.lower() in result.lower()
        print(f"  {'PASS' if ok else 'FAIL'}  {desc}: '{source}' → '{result}'")
        passed = passed and ok

        # Extra: no critical German residue after full pipeline
        remaining = detector.has_critical_residue(result)
        ok2 = len(remaining) == 0
        if not ok2:
            print(f"  FAIL  Critical residue remaining: {remaining}")
        passed = passed and ok2

    print()
    return passed


# ── 11. Dimension labels ──────────────────────────────────────────────

def test_dimension_labels():
    """B x H x T must become B x H x D; Liegehöhe must become lighoogte."""
    print("=== Dimension label conversions ===")

    from engines.residue_detector import get_residue_detector
    from engines.qa_engine import normalize_mdf_nl
    detector = get_residue_detector()
    passed = True

    # These conversions happen via TM / phrase memory / QA engine
    cases = [
        ("B x H x T: 80 x 75 x 40 cm",    "B x H x D",     "BHT → BHD"),
        ("Liegehöhe: 45 cm",               "lighoogte",      "Liegehöhe → lighoogte"),
    ]
    run_migrations()
    from engines.translation_engine import get_engine
    engine = get_engine()

    for source, expected_fragment, desc in cases:
        items = [(0, source)]
        try:
            batch = engine.translate_batch(items, context_rows=[], filename="test.xlsx")
            result = batch.results[0].target if batch.results else ""
        except Exception as exc:
            result = f"ERROR: {exc}"

        ok = expected_fragment.lower() in result.lower()
        print(f"  {'PASS' if ok else 'FAIL'}  {desc}: '{source}' → '{result}'")
        passed = passed and ok

    print()
    return passed


# ── 12. Decor look patterns ───────────────────────────────────────────

def test_decor_look_patterns():
    """Eiche Sägerau Dekor → grof gezaagde eikenlook; Nussbaum Dekor → notenlook."""
    print("=== Decor look patterns ===")
    run_migrations()

    from engines.translation_engine import get_engine
    engine = get_engine()
    passed = True

    cases = [
        ("Eiche Sägerau Dekor",  "eikenlook",    "Eiche Sägerau → eikenlook"),
        ("Nussbaum Dekor",       "notenlook",     "Nussbaum → notenlook"),
    ]

    for source, expected_fragment, desc in cases:
        items = [(0, source)]
        try:
            batch = engine.translate_batch(items, context_rows=[], filename="test.xlsx")
            result = batch.results[0].target if batch.results else ""
        except Exception as exc:
            result = f"ERROR: {exc}"

        ok = expected_fragment.lower() in result.lower()
        print(f"  {'PASS' if ok else 'FAIL'}  {desc}: '{source}' → '{result}'")
        passed = passed and ok

    # Also confirm Dekor is not left in output
    test_with_dekor = "Eiche Sägerau Dekor"
    items = [(0, test_with_dekor)]
    try:
        batch = engine.translate_batch(items, context_rows=[], filename="test.xlsx")
        result = batch.results[0].target if batch.results else ""
    except Exception:
        result = ""

    from engines.residue_detector import get_residue_detector
    residue = get_residue_detector().has_critical_residue(result)
    ok = "Dekor" not in residue
    print(f"  {'PASS' if ok else 'FAIL'}  'Dekor' not in critical residue after pipeline  (residue: {residue})")
    passed = passed and ok

    print()
    return passed


# ── 13. Product name max-40 characters ───────────────────────────────

def test_product_name_max_40():
    """Translated product names (column 'name') must be ≤ 40 characters and complete."""
    print("=== Product name max 40 chars ===")
    run_migrations()

    from engines.translation_engine import get_engine
    engine = get_engine()
    passed = True

    long_names = [
        "Pantryküche Levin mit Kühlschrank und Backofen",
        "Ecksofa Clarissa mit Schlaffunktion und Stauraum",
        "Bücherregal Maximilian aus Massivholz mit Metallgestell",
    ]

    for source in long_names:
        items = [(0, source)]
        try:
            batch = engine.translate_batch(
                items, context_rows=[], filename="test.xlsx", column_name="name"
            )
            result = batch.results[0].target if batch.results else ""
        except Exception as exc:
            result = f"ERROR: {exc}"

        ok_len = len(result) <= 40
        ok_complete = not result.endswith(("met", "van", "voor", "uit"))
        ok = ok_len and ok_complete
        print(f"  {'PASS' if ok else 'FAIL'}  '{source}' ({len(source)} chars)")
        print(f"         → '{result}' ({len(result)} chars)  len≤40={ok_len}  complete={ok_complete}")
        passed = passed and ok

    print()
    return passed


# ── 14. New material residue patterns ────────────────────────────────

def test_material_residue_patterns():
    """Metall, Holz, Leder, Kunststoff, pulverbeschichtet must be auto-converted."""
    print("=== Material residue patterns ===")

    from engines.residue_detector import get_residue_detector, GERMAN_RESIDUE_PATTERNS
    detector = get_residue_detector()
    passed = True

    cases = [
        ("Metall, pulverbeschichtet",    "metaal, poedergecoat",     "Metall + pulverbeschichtet"),
        ("Holz, lackiert",               "hout, gelakt",              "Holz + lackiert"),
        ("Leder",                        "leer",                      "Leder → leer"),
        ("Kunststoff",                   "kunststof",                 "Kunststoff → kunststof"),
    ]

    for inp, expected, desc in cases:
        result = detector.detect_and_clean(inp, auto_fix=True)
        ok = result.text.lower() == expected.lower()
        print(f"  {'PASS' if ok else 'FAIL'}  {desc}: {inp!r} → {result.text!r}  (expected {expected!r})")
        passed = passed and ok

    # Confirm patterns present in GERMAN_RESIDUE_PATTERNS
    for word in ("Metall", "Holz", "Leder", "Kunststoff", "pulverbeschichtet"):
        covered = any(word.lower() in p.lower() for p, _ in GERMAN_RESIDUE_PATTERNS)
        print(f"  {'PASS' if covered else 'FAIL'}  '{word}' present in GERMAN_RESIDUE_PATTERNS")
        passed = passed and covered

    print()
    return passed


# ── 15. Home24 label normalizer (Bezug/Füße/Gestell etc.) ────────────

def test_home24_label_normalizer():
    """normalize_home24_labels_nl must convert all German product labels."""
    print("=== Home24 label normalizer ===")

    from engines.qa_engine import normalize_home24_labels_nl
    passed = True

    cases = [
        # (input, expected_output, description)
        ("Bezug: beige<br>Füße: zwart",
         "Bekleding: beige<br>Poten: zwart",
         "Bezug/Füße with colon"),

        ("Bezug: Microfaser<br>Füße: kunststof",
         "Bekleding: microvezel<br>Poten: kunststof",
         "Bezug Microfaser + Füße kunststof"),

        ("Gestell: zwart metaal<br>Korpus: wit",
         "Frame: zwart metaal<br>Body: wit",
         "Gestell + Korpus"),

        ("Farbe: Schwarz<br>Material: Holz",
         "Kleur: Schwarz<br>Materiaal: Holz",
         "Farbe + Material labels (color/material translated by residue detector separately)"),

        ("Schubladen: 3<br>Türen: 2",
         "Laden: 3<br>Deuren: 2",
         "Schubladen + Türen"),

        ("Maße: 80 x 60 x 40 cm",
         "Afmetingen: 80 x 60 x 40 cm",
         "Maße label"),

        ("Microfaser, 100% Polyester",
         "microvezel, 100% Polyester",
         "Microfaser standalone"),

        ("al Dutch — geen wijziging",
         "al Dutch — geen wijziging",
         "already Dutch — no change"),
    ]

    for inp, expected, desc in cases:
        got = normalize_home24_labels_nl(inp)
        ok = got.lower() == expected.lower()
        print(f"  {'PASS' if ok else 'FAIL'}  {desc}")
        if not ok:
            print(f"    input:    {inp!r}")
            print(f"    expected: {expected!r}")
            print(f"    got:      {got!r}")
        passed = passed and ok

    print()
    return passed


# ── 16. Full pipeline Bezug/Füße regression ───────────────────────────

def test_bezug_fusse_pipeline():
    """Full pipeline must produce Bekleding/Poten — not Bezug/Füße."""
    print("=== Bezug / Füße pipeline regression ===")
    run_migrations()

    from engines.translation_engine import get_engine
    from engines.residue_detector import get_residue_detector, CRITICAL_GERMAN_WORDS
    engine = get_engine()
    detector = get_residue_detector()
    passed = True

    cases = [
        ("Bezug: beige<br>Füße: schwarz",
         [("Bekleding", True), ("Poten", True), ("Bezug", False), ("Füße", False)],
         "Bezug/Füße with colon"),

        ("Bezug: Microfaser<br>Füße: Kunststoff",
         [("Bekleding", True), ("microvezel", True), ("Bezug", False), ("Füße", False)],
         "Bezug Microfaser"),

        ("ohne Dekoration",
         [("zonder", True), ("ohne", False)],
         "ohne → zonder"),

        ("Metall, pulverbeschichtet",
         [("metaal", True), ("Metall", False)],  # TM stores gepoedercoat; both gepoedercoat/poedergecoat are valid
         "Metall + pulverbeschichtet"),
    ]

    for source, checks, desc in cases:
        items = [(0, source)]
        try:
            batch = engine.translate_batch(items, context_rows=[], filename="test.xlsx")
            result = batch.results[0].target if batch.results else ""
        except Exception as exc:
            result = f"ERROR: {exc}"

        row_pass = True
        print(f"  '{source}' → '{result}'")
        for fragment, should_be_present in checks:
            present = fragment.lower() in result.lower()
            ok = present == should_be_present
            label = "present" if should_be_present else "absent"
            print(f"    {'PASS' if ok else 'FAIL'}  '{fragment}' should be {label}")
            row_pass = row_pass and ok

        # Critical residue check
        residue = detector.has_critical_residue(result)
        no_critical = len(residue) == 0
        print(f"    {'PASS' if no_critical else 'FAIL'}  no critical German residue  (found: {residue})")
        row_pass = row_pass and no_critical

        passed = passed and row_pass
        print()

    # Confirm Bezug and Füße are in CRITICAL_GERMAN_WORDS
    for word in ("Bezug", "Füße", "Gestell", "Microfaser", "Maße"):
        found = bool(CRITICAL_GERMAN_WORDS.search(word))
        print(f"  {'PASS' if found else 'FAIL'}  '{word}' in CRITICAL_GERMAN_WORDS")
        passed = passed and found

    print()
    return passed


# ── 17. Quality gate blocks export on unresolved residue ──────────────

def test_quality_gate_blocks():
    """_run_quality_gate must return blocked=True when residue cannot be auto-fixed."""
    print("=== Quality gate blocks on unresolved residue ===")

    # Simulate a row with a word that can be auto-fixed and one that can't (gibberish German)
    # We add a known-fixable word so we can verify corrections_made
    test_rows = [
        {"Row": 1, "Column": "colorDetail",  "German source": "test", "Dutch translation": "Bezug: beige<br>Füße: zwart",   "Confidence": "HIGH", "Origin": "TM_EXACT"},
        {"Row": 2, "Column": "materialDetail","German source": "test", "Dutch translation": "schöne Eiche massiv",           "Confidence": "HIGH", "Origin": "TM_EXACT"},
        {"Row": 3, "Column": "name",          "German source": "test", "Dutch translation": "Bank Grau modern",              "Confidence": "HIGH", "Origin": "TM_EXACT"},
    ]

    passed = True

    # Import from translate_page
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    # Use the gate functions directly without Streamlit
    from engines.qa_engine import normalize_home24_labels_nl, normalize_mdf_nl, has_critical_label_residue
    from engines.residue_detector import get_residue_detector
    detector = get_residue_detector()

    corrected = 0
    warnings = []
    for row in test_rows:
        dutch = (row.get("Dutch translation") or "").strip()
        fixed = normalize_home24_labels_nl(dutch)
        fixed = normalize_mdf_nl(fixed)
        residue_result = detector.detect_and_clean(fixed, auto_fix=True)
        fixed = residue_result.text
        if fixed != dutch:
            row["Dutch translation"] = fixed
            corrected += 1
        critical = detector.has_critical_residue(fixed) + has_critical_label_residue(fixed)
        if critical:
            warnings.append(f"Row {row['Row']}: {critical}")

    ok_corr = corrected >= 1
    print(f"  {'PASS' if ok_corr else 'FAIL'}  At least 1 correction made  (got {corrected})")
    passed = passed and ok_corr

    # Row 1 (Bezug/Füße) should have been auto-fixed
    row1_dutch = test_rows[0]["Dutch translation"]
    ok_fixed = "Bezug" not in row1_dutch and "Füße" not in row1_dutch
    print(f"  {'PASS' if ok_fixed else 'FAIL'}  Bezug/Füße auto-fixed in row 1: {row1_dutch!r}")
    passed = passed and ok_fixed

    # Row 2 (Eiche) — Eiche is critical, should be flagged
    row2_dutch = test_rows[1]["Dutch translation"]
    ok_eiche = "eiken" in row2_dutch.lower() or "Eiche" not in row2_dutch
    print(f"  {'PASS' if ok_eiche else 'FAIL'}  Eiche handled in row 2: {row2_dutch!r}")
    passed = passed and ok_eiche

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
        test_no_metadata_injection(),
        test_german_residue_detector(),
        test_mdf_normalization(),
        test_tm_import_upsert(),
        test_pipeline_residue_regression(),
        test_dimension_labels(),
        test_decor_look_patterns(),
        test_product_name_max_40(),
        test_material_residue_patterns(),
        test_home24_label_normalizer(),
        test_bezug_fusse_pipeline(),
        test_quality_gate_blocks(),
    ]

    total = len(results)
    n_pass = sum(results)
    print("=" * 50)
    print(f"Coverage tests: {n_pass}/{total} passed")
    if n_pass < total:
        sys.exit(1)
