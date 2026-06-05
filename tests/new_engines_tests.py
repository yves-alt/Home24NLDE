import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_product_classifier():
    from engines.product_classifier import get_classifier

    clf = get_classifier()

    r = clf.classify("Singleküche Kinneloa Variante A")
    assert r.product_type == "kitchen", f"Expected kitchen, got {r.product_type}"
    assert r.confidence >= 0.50

    r = clf.classify("Duschmatte Cubano 50x80 cm")
    assert r.product_type == "bathroom", f"Expected bathroom, got {r.product_type}"

    r = clf.classify("Ecksofa Valencia mit Schlaffunktion")
    assert r.product_type == "sofa", f"Expected sofa, got {r.product_type}"

    r = clf.classify("Pendelleuchte Marta schwarz")
    assert r.product_type == "lighting", f"Expected lighting, got {r.product_type}"

    print("ProductTypeClassifier: all cases PASS")
    return 0


def test_category_glossary():
    from engines.category_glossary import get_category_glossary

    cg = get_category_glossary()

    assert cg.lookup("duschmatte", "bathroom") == "douchemat"
    assert cg.lookup("kücheninsel", "kitchen") == "kookeiland"
    assert cg.lookup("lowboard", "storage") == "tv-meubel"
    assert cg.lookup("ecksofa", "sofa") == "hoekbank"

    text, applied = cg.apply("Duschmatte mit Antirutsch", "bathroom")
    assert "douchemat" in text.lower(), f"Expected douchemat in '{text}'"

    print("CategoryGlossaryManager: all cases PASS")
    return 0


def test_product_name_generator():
    from engines.product_name_generator import get_name_generator

    gen = get_name_generator()

    result = gen.generate("Singleküche Kinneloa Variante A")
    assert result is not None
    assert "mini keuken" in result.lower() or "Mini keuken" in result, f"Got: {result}"

    result = gen.generate("TV-Lowboard Milano")
    assert result is not None
    assert "tv-meubel" in result.lower() or "Tv-meubel" in result, f"Got: {result}"

    result = gen.generate("Duschmatte Cubano")
    assert result is not None
    assert "douchemat" in result.lower() or "Douchemat" in result, f"Got: {result}"

    print("DutchProductNameGenerator: all cases PASS")
    return 0


def test_material_context():
    from engines.material_context import get_material_engine

    eng = get_material_engine()

    result, _ = eng.apply("Tisch aus Massivholz", "dining")
    assert "massief hout" in result.lower(), f"Expected 'massief hout' in '{result}'"

    result, _ = eng.apply("Hochglanz weiß lackiert", "storage")
    assert "hoogglans" in result.lower(), f"Expected 'hoogglans' in '{result}'"

    # Corpus-aware: Korpus stays as korpus in kitchen context
    term = eng.translate_term("korpus", "kitchen")
    assert term == "korpus", f"Expected 'korpus' in kitchen context, got '{term}'"

    term = eng.translate_term("edelstahl", "general")
    assert term == "roestvrij staal", f"Expected 'roestvrij staal', got '{term}'"

    print("MaterialContextEngine: all cases PASS")
    return 0


def test_phrase_memory_in_memory():
    from engines.phrase_memory import PhraseMemory, SEED_PHRASES, _normalize

    pm = PhraseMemory()

    # Test substring matching logic directly (without DB)
    class _FakePM(PhraseMemory):
        def lookup(self, text, category="general"):
            norm = _normalize(text)
            for src, tgt, cat, conf in SEED_PHRASES:
                if _normalize(src) in norm:
                    return tgt
            return None

    fake = _FakePM()
    result = fake.lookup("Pflegeleicht und wetterfest beschichtet")
    assert result == "onderhoudsvriendelijk en weerbestendig", f"Got: {result}"

    result = fake.lookup("Einfache Montage inklusive Montagematerial")
    assert result is not None

    print("PhraseMemory (in-memory): all cases PASS")
    return 0


def test_confidence_scorer_new_labels():
    from engines.confidence_scorer import score_translation, ConfidenceLabel

    c = score_translation("test", "test", "PHRASE_MEMORY", 0.97)
    assert c.label == ConfidenceLabel.PHRASE_MEMORY
    assert c.score >= 0.90
    assert c.warning_level == "ok"

    c = score_translation("test", "test", "CORPUS", 0.80)
    assert c.label == ConfidenceLabel.CORPUS
    assert c.warning_level in ("ok", "warning")

    c = score_translation("test", "test", "CATEGORY_GLOSSARY", 0.93)
    assert c.label == ConfidenceLabel.CATEGORY_GLOSSARY
    assert c.warning_level == "ok"

    # Critical threshold test
    c = score_translation("test", "t", "GPT", 0.0, qa_issue_count=3)
    assert c.warning_level == "critical"

    print("ConfidenceScorer (new labels): all cases PASS")
    return 0
