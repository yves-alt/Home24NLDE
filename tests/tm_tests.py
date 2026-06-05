# Full pipeline tests — TM, glossary, naturalness rules
# Run after TM import and glossary seed
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.migrations import run_migrations
from engines.tm_matcher import get_matcher, MatchType
from engines.glossary_engine import get_glossary_manager
from engines.naturalness_rewriter import get_rewriter


def test_tm_direct_matches():
    """Terms that should resolve via direct TM lookup."""
    run_migrations()
    matcher = get_matcher()
    matcher.reload()

    cases = [
        ("Mehrfarbig", "meerdere kleuren"),
        ("Eiche Sägerau Dekor", "grof gezaagde eikenlook"),
        ("Nussbaum Dekor", "notenlook"),
        ("Spanplatte, foliert", "gefolieerde spaanplaat"),
        ("Weiß / Schwarz", "wit/zwart"),
    ]

    print("=== TM Direct Match Tests ===")
    passed = 0
    for source, expected in cases:
        match = matcher.match(source)
        if match and match.target.lower() == expected.lower():
            print(f"  PASS  [{match.match_type.value}] {source} → {match.target}")
            passed += 1
        elif match:
            print(f"  WARN  [{match.match_type.value}] {source} → '{match.target}' (expected '{expected}', score={match.score:.2f})")
        else:
            print(f"  MISS  {source} → no match (expected '{expected}')")

    print(f"\n{passed}/{len(cases)} direct TM matches\n")
    return passed


def test_glossary_coverage():
    """Critical Home24 NL terms must be resolvable via glossary."""
    gm = get_glossary_manager()

    cases = [
        ("duschmatte", "douchemat"),
        ("badewannenmatte", "badkuipmat"),
        ("bügelbrettbezug", "strijkplankhoes"),
        ("singleküche", "mini keuken"),
        ("kücheninsel", "kookeiland"),
        ("mehrfarbig", "meerdere kleuren"),
        ("eisen", "ijzer"),
        ("eiche sägerau dekor", "grof gezaagde eikenlook"),
        ("nussbaum dekor", "notenlook"),
    ]

    print("=== Glossary Coverage Tests ===")
    passed = 0
    for source, expected in cases:
        hit = gm.lookup(source)
        if hit and hit.target_term.lower() == expected.lower():
            print(f"  PASS  {source} → {hit.target_term} (conf={hit.confidence:.2f})")
            passed += 1
        elif hit:
            print(f"  WARN  {source} → '{hit.target_term}' (expected '{expected}')")
        else:
            print(f"  MISS  {source} → not in glossary")

    print(f"\n{passed}/{len(cases)} glossary terms found\n")
    return passed


def test_naturalness_rules():
    """Naturalness rewriter must produce native Dutch for key terms."""
    rewriter = get_rewriter()

    cases = [
        ("Kaminset", "haardset"),
        ("Tablett", "dienblad"),
        ("Tellerstand", "bordenstandaard"),
        ("Kücheninsel", "kookeiland"),
        ("Duschmatte", "douchemat"),
    ]

    print("=== Naturalness Rewriter Tests ===")
    passed = 0
    for source, expected in cases:
        result, rules = rewriter.rewrite(source)
        if result.lower() == expected.lower():
            print(f"  PASS  {source} → {result}")
            passed += 1
        else:
            print(f"  FAIL  {source} → '{result}' (expected '{expected}')")

    print(f"\n{passed}/{len(cases)} naturalness rules matched\n")
    return passed


if __name__ == "__main__":
    tm_passed, _ = test_tm_direct_matches(), None
    g_passed = test_glossary_coverage()
    n_passed = test_naturalness_rules()
    total = 5 + 9 + 5
    achieved = (tm_passed if isinstance(tm_passed, int) else 0) + g_passed + n_passed
    print(f"=== TOTAL: {achieved}/{total} tests passed ===")
