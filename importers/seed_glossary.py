# Seed the glossary with known DE→NL Home24 furniture vocabulary
from database.database import get_connection

SEED_TERMS = [
    # Bathroom / textile
    ("duschmatte", "douchemat", "bathroom", 0.95),
    ("badewannenmatte", "badkuipmat", "bathroom", 0.95),
    ("bügelbrettbezug", "strijkplankhoes", "textile", 0.95),
    ("handtuchhalter", "handdoekhouder", "bathroom", 0.95),
    ("seifenspender", "zeepdispenser", "bathroom", 0.90),
    ("duschvorhang", "douchegordijn", "bathroom", 0.95),
    ("badezimmerspiegel", "badkamerspiegel", "bathroom", 0.90),
    # Kitchen
    ("singleküche", "mini keuken", "kitchen", 0.95),
    ("kücheninsel", "kookeiland", "kitchen", 0.95),
    ("pantryküche", "pantry keuken", "kitchen", 0.95),
    ("einbauküche", "inbouwkeuken", "kitchen", 0.95),
    ("küchenzeile", "keukenblok", "kitchen", 0.90),
    ("küchenwagen", "keukentrolley", "kitchen", 0.90),
    # Colors
    ("mehrfarbig", "meerdere kleuren", "color", 0.95),
    ("einfarbig", "eenkleurig", "color", 0.90),
    ("zweifarbig", "tweekleurig", "color", 0.90),
    # Decors / materials
    ("eiche sägerau dekor", "grof gezaagde eikenlook", "material", 0.95),
    ("nussbaum dekor", "notenlook", "material", 0.95),
    ("beton dekor", "betonlook", "material", 0.95),
    ("marmor dekor", "marmereffect", "material", 0.90),
    ("walnuss dekor", "walnotenlook", "material", 0.90),
    ("eiche artisan dekor", "artisan eikenlook", "material", 0.90),
    # Furniture
    ("wohnlandschaft", "hoekbank", "living", 0.90),
    ("ottomane", "ottomane", "living", 1.0),
    ("chaiselongue", "chaise longue", "living", 1.0),
    ("couchtisch", "salontafel", "living", 0.95),
    ("beistelltisch", "bijzettafel", "living", 0.95),
    ("nachttisch", "nachtkastje", "bedroom", 0.95),
    ("bettgestell", "bedframe", "bedroom", 0.95),
    ("kopfteil", "hoofdeinde", "bedroom", 0.95),
    ("lattenrost", "lattenbodem", "bedroom", 0.95),
    # Storage
    ("lowboard", "tv-meubel", "storage", 0.90),
    ("sideboard", "dressoir", "storage", 0.90),
    ("highboard", "hoge kast", "storage", 0.85),
    ("vitrine", "vitrinekast", "storage", 0.90),
    ("kleiderschrank", "kledingkast", "storage", 0.95),
    # Lighting
    ("pendelleuchte", "hanglamp", "lighting", 0.95),
    ("stehleuchte", "vloerlamp", "lighting", 0.95),
    ("wandleuchte", "wandlamp", "lighting", 0.95),
    ("tischleuchte", "tafellamp", "lighting", 0.95),
    ("deckenleuchte", "plafondlamp", "lighting", 0.95),
    # Outdoor
    ("gartenbank", "tuinbank", "outdoor", 0.95),
    ("gartentisch", "tuintafel", "outdoor", 0.95),
    ("sonnenschirm", "parasol", "outdoor", 0.95),
    # Misc
    ("kaminset", "haardset", "general", 0.95),
    ("tablett", "dienblad", "general", 0.95),
    ("tellerstand", "bordenstandaard", "general", 0.90),
    ("eisen", "ijzer", "material", 0.95),
]


def seed_glossary() -> int:
    inserted = 0
    with get_connection() as conn:
        for source, target, category, confidence in SEED_TERMS:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO glossary "
                    "(source_term, target_term, category, frequency, confidence, source_type, active) "
                    "VALUES (?,?,?,100,?,'MANUAL',1)",
                    (source, target, category, confidence),
                )
                inserted += 1
            except Exception:
                pass
    return inserted
