# Consistency engine tests
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from engines.consistency_engine import DutchWorkbookConsistencyEngine


def test_consistency():
    engine = DutchWorkbookConsistencyEngine()

    pairs = [
        ("Duschmatte", "douchemat"),
        ("Sofatisch", "salontafel"),
        ("Duschmatte", "douchematje"),  # variant — should be resolved
        ("Mehrfarbig", "meerdere kleuren"),
        ("Sofatisch", "koffietafel"),   # variant — should be resolved
        ("Mehrfarbig", "veelkleurig"),  # variant — should be resolved
    ]

    print("=== Consistency Engine Test ===")
    resolved = engine.resolve_workbook(pairs)

    duschmatte_translations = set()
    sofatisch_translations = set()
    mehrfarbig_translations = set()

    for (src, _), tgt in zip(pairs, resolved):
        if src == "Duschmatte":
            duschmatte_translations.add(tgt)
        elif src == "Sofatisch":
            sofatisch_translations.add(tgt)
        elif src == "Mehrfarbig":
            mehrfarbig_translations.add(tgt)

    passed = 0
    for term, translations in [("Duschmatte", duschmatte_translations),
                                 ("Sofatisch", sofatisch_translations),
                                 ("Mehrfarbig", mehrfarbig_translations)]:
        if len(translations) == 1:
            print(f"  PASS  {term} → consistent: '{list(translations)[0]}'")
            passed += 1
        else:
            print(f"  FAIL  {term} → inconsistent: {translations}")

    print(f"\n{passed}/3 consistency checks passed")
    return passed


if __name__ == "__main__":
    test_consistency()
