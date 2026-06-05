# QA engine tests
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from engines.qa_engine import get_qa_engine
from engines.name_optimizer import get_name_optimizer


def test_qa_forbidden_patterns():
    qa = get_qa_engine()

    cases = [
        ("Keukeninsel", "kookeiland"),
        ("Douchematt", "douchemat"),
        ("Kookfeld", "kookplaat"),
        ("Notelaar Dekor", "notenlook"),
        ("Ijzer tafel", "IJzer tafel"),
    ]

    print("=== QA Forbidden Pattern Tests ===")
    passed = 0
    for text, expected_correction in cases:
        result = qa.validate(text)
        if result.issues:
            if expected_correction and result.corrected.lower() == expected_correction.lower():
                print(f"  PASS  '{text}' → '{result.corrected}'")
                passed += 1
            else:
                print(f"  WARN  '{text}' → '{result.corrected}' (expected '{expected_correction}') issues={[i.issue_type for i in result.issues]}")
        else:
            print(f"  NOTE  '{text}' → no issues detected")
    print(f"\n{passed}/{len(cases)} corrections matched")
    return passed


def test_name_optimizer():
    optimizer = get_name_optimizer()

    cases = [
        ("Pantrykeuken Levin met keramische", "Pantrykeuken Levin"),
        ("Sofa met", "Sofa"),
        ("Bureau Anika met houten", "Bureau Anika"),
        ("Kast Valeska", "Kast Valeska"),
    ]

    print("\n=== Name Optimizer Tests ===")
    passed = 0
    for name, expected in cases:
        optimized, actions = optimizer.optimize(name)
        if optimized.lower() == expected.lower():
            print(f"  PASS  '{name}' → '{optimized}'")
            passed += 1
        else:
            print(f"  FAIL  '{name}' → '{optimized}' (expected '{expected}')")
    print(f"\n{passed}/{len(cases)} passed")
    return passed


if __name__ == "__main__":
    test_qa_forbidden_patterns()
    test_name_optimizer()
