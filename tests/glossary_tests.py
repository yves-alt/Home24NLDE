# Glossary engine tests — run after TM import and glossary build
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.migrations import run_migrations
from engines.glossary_engine import get_glossary_manager


def test_glossary_lookups():
    run_migrations()
    gm = get_glossary_manager()

    cases = [
        "duschmatte",
        "mehrfarbig",
        "badewannenmatte",
    ]

    print("=== Glossary Lookup Tests ===")
    found = 0
    for term in cases:
        hit = gm.lookup(term)
        if hit:
            print(f"  FOUND  {term} → {hit.target_term} (conf={hit.confidence:.2f}, cat={hit.category})")
            found += 1
        else:
            print(f"  MISS   {term} → not in glossary")

    stats = gm.get_stats()
    print(f"\nGlossary stats: {stats['total']} total, {stats['active']} active")
    print(f"By type: {stats['by_type']}")
    return found


if __name__ == "__main__":
    test_glossary_lookups()
