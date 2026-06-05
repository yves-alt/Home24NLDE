import re

# Material translations that depend on context / product category
MATERIAL_RULES: list[tuple[str, str, set[str], str]] = [
    # (german_term, dutch_term, applicable_categories, notes)
    # Korpus — keep as-is in kitchen context, translate to "frame" elsewhere
    ("korpus", "korpus", {"kitchen"}, ""),
    ("korpus", "frame", set(), ""),  # fallback for non-kitchen

    # Dekor suffix handling
    ("beton dekor", "betonlook", set(), ""),
    ("eiche sägerau dekor", "grof gezaagde eikenlook", set(), ""),
    ("eiche dekor", "eikenlook", set(), ""),
    ("holzdekor", "houtlook", set(), ""),
    ("steindekor", "steenlook", set(), ""),
    ("betondekor", "betonlook", set(), ""),

    # Material finishes
    ("hochglanz", "hoogglans", set(), ""),
    ("matt", "mat", set(), ""),
    ("gebürstet", "geborsteld", set(), ""),
    ("poliert", "gepolijst", set(), ""),
    ("lackiert", "gelakt", set(), ""),
    ("geölt", "geolied", set(), ""),
    ("gewachst", "gewaxed", set(), ""),
    ("beschichtet", "gecoat", set(), ""),
    ("melamin", "melamine", set(), ""),
    ("laminat", "laminaat", set(), ""),

    # Wood types
    ("massivholz", "massief hout", set(), ""),
    ("spanplatte", "spaanplaat", set(), ""),
    ("mdf", "mdf", set(), ""),
    ("sperrholz", "multiplex", set(), ""),
    ("bambus", "bamboe", set(), ""),
    ("eiche massiv", "massief eiken", set(), ""),
    ("buche massiv", "massief beuken", set(), ""),

    # Metal
    ("edelstahl", "roestvrij staal", set(), ""),
    ("chromstahl", "verchroomd staal", set(), ""),
    ("pulverbeschichtet", "poedergelakt", set(), ""),
    ("verzinkt", "verzinkt", set(), ""),
    ("messing", "messing", set(), ""),
    ("kupfer", "koper", set(), ""),

    # Fabric / upholstery
    ("baumwolle", "katoen", set(), ""),
    ("polyester", "polyester", set(), ""),
    ("polypropylen", "polypropyleen", set(), ""),
    ("viskose", "viscose", set(), ""),
    ("leinen", "linnen", set(), ""),
    ("wolle", "wol", set(), ""),
    ("acryl", "acryl", set(), ""),
    ("mikrofaser", "microvezel", set(), ""),
    ("velours", "velours", set(), ""),
    ("frottee", "badstof", {"bathroom"}, ""),
    ("frottee", "badstof", set(), ""),

    # Glass / stone
    ("sicherheitsglas", "veiligheidsglas", set(), ""),
    ("hartglas", "gehard glas", set(), ""),
    ("glas", "glas", set(), ""),
    ("marmor", "marmer", set(), ""),
    ("granit", "graniet", set(), ""),
    ("kunststein", "kunststeen", set(), ""),
    ("keramik", "keramiek", set(), ""),

    # Synthetic
    ("kunststoff", "kunststof", set(), ""),
    ("polyethylen", "polyethyleen", set(), ""),
    ("abs", "abs", set(), ""),
    ("pvc", "pvc", set(), ""),
    ("polyrattan", "polyrattan", set(), ""),
    ("aluminium", "aluminium", set(), ""),
    ("eisen", "ijzer", set(), ""),
    ("stahl", "staal", set(), ""),
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


class MaterialContextEngine:

    def __init__(self):
        # Build lookup: (normalized_term, frozenset_categories) → dutch
        self._rules: list[tuple[str, frozenset, str]] = [
            (_normalize(de), frozenset(cats), nl)
            for de, nl, cats, _ in MATERIAL_RULES
        ]

    def apply(self, text: str, category: str = "general") -> tuple[str, list[str]]:
        result = text
        applied: list[str] = []
        lower_cat = category.lower()

        # Sort by specificity: category-specific rules first, then by length
        category_rules = [
            (de, cats, nl) for de, cats, nl in self._rules if lower_cat in cats
        ]
        general_rules = [
            (de, cats, nl) for de, cats, nl in self._rules if not cats
        ]

        for de_norm, _, nl in category_rules + general_rules:
            pattern = re.compile(r'\b' + re.escape(de_norm) + r'\b', re.IGNORECASE)
            new_result, n = pattern.subn(nl, result)
            if n:
                result = new_result
                applied.append(de_norm)

        return result, applied

    def translate_term(self, term: str, category: str = "general") -> str | None:
        norm = _normalize(term)
        lower_cat = category.lower()

        # Category-specific match first
        for de_norm, cats, nl in self._rules:
            if de_norm == norm and lower_cat in cats:
                return nl

        # General match
        for de_norm, cats, nl in self._rules:
            if de_norm == norm and not cats:
                return nl

        return None


_instance: MaterialContextEngine | None = None


def get_material_engine() -> MaterialContextEngine:
    global _instance
    if _instance is None:
        _instance = MaterialContextEngine()
    return _instance
