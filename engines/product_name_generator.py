import re

FORBIDDEN_ENDINGS = {
    "de", "en", "er", "e", "es", "el", "ung", "heit", "keit",
    "schaft", "tum", "nis", "sal", "ig", "isch", "lich", "sam",
}

NAME_TEMPLATES: dict[str, str] = {
    "singleküche": "Mini keuken",
    "pantryküche": "Pantrykeuken",
    "einbauküche": "Inbouwkeuken",
    "kücheninsel": "Kookeiland",
    "küchenzeile": "Keukenblok",
    "tv-lowboard": "Tv-meubel",
    "tv lowboard": "Tv-meubel",
    "lowboard": "Tv-meubel",
    "highboard": "Hoge kast",
    "sideboard": "Dressoir",
    "wohnlandschaft": "Woonlandschap",
    "ecksofa": "Hoekbank",
    "schlafsofa": "Slaapbank",
    "relaxsessel": "Relaxfauteuil",
    "chaiselongue": "Chaise longue",
    "ottomane": "Chaise longue",
    "badset": "Badkamerset",
    "badezimmerset": "Badkamerset",
    "badematte": "Badmat",
    "duschmatte": "Douchemat",
    "badewannenmatte": "Badkuipmat",
    "pendelleuchte": "Hanglamp",
    "hängeleuchte": "Hanglamp",
    "stehleuchte": "Vloerlamp",
    "tischleuchte": "Tafellamp",
    "wandleuchte": "Wandlamp",
    "deckenleuchte": "Plafondlamp",
    "kleiderschrank": "Kledingkast",
    "schwebetürenschrank": "Schuifdeurkast",
    "drehtürenschrank": "Draaideuren kledingkast",
    "vitrine": "Vitrinekast",
    "kommode": "Ladekast",
    "bücherregal": "Boekenkast",
    "wandregal": "Wandplank",
    "esstisch": "Eettafel",
    "esstischstuhl": "Eetkamerstoel",
    "barhocker": "Barkruk",
    "bartisch": "Bartafel",
    "gartenbank": "Tuinbank",
    "gartenstuhl": "Tuinstoel",
    "gartentisch": "Tuintafel",
    "liegestuhl": "Ligstoel",
    "sonnenschirm": "Parasol",
    "pflanzenkübel": "Plantenbak",
    "schreibtisch": "Bureau",
    "bürostuhl": "Bureaustoel",
    "matratze": "Matras",
    "lattenrost": "Lattenbodem",
    "kopfkissen": "Hoofdkussen",
    "bettbezug": "Dekbedovertrek",
    "bettwäsche": "Beddengoed",
    "bügelbrett": "Strijkplank",
    "bügelbrettbezug": "Strijkplankhoes",
    "teppich": "Tapijt",
    "teppichläufer": "Loper",
    "vorhang": "Gordijn",
    "gardine": "Vitrage",
}

# Word-level replacements applied to the remainder of the product name
WORD_REPLACEMENTS: dict[str, str] = {
    "variante": "Variant",
    "kollektion": "Collectie",
    "serie": "Serie",
    "set": "Set",
    "grau": "grijs",
    "schwarz": "zwart",
    "weiß": "wit",
    "beige": "beige",
    "braun": "bruin",
    "blau": "blauw",
    "grün": "groen",
    "rot": "rood",
    "gelb": "geel",
    "orange": "oranje",
    "lila": "paars",
    "pink": "roze",
    "natur": "naturel",
    "anthrazit": "antraciet",
    "dunkelgrau": "donkergrijs",
    "hellgrau": "lichtgrijs",
    "dunkelbraun": "donkerbruin",
    "eiche": "eiken",
    "buche": "beuken",
    "kiefer": "den",
    "birke": "berk",
    "nussbaum": "walnoot",
    "mango": "mango",
    "massiv": "massief",
}

# Suffix patterns to strip from German product names
_STRIP_SUFFIXES = re.compile(
    r'\s+(Variante\s+[A-Z]|Modell\s+\w+|in\s+\w+|mit\s+\w+)'
    r'$', re.IGNORECASE
)


def _apply_word_replacements(text: str) -> str:
    result = text
    for de_word, nl_word in sorted(WORD_REPLACEMENTS.items(), key=lambda x: len(x[0]), reverse=True):
        result = re.sub(r'\b' + re.escape(de_word) + r'\b', nl_word, result, flags=re.IGNORECASE)
    return result


def _ends_with_forbidden(text: str) -> bool:
    last = text.strip().rstrip(".,;:!?").lower().split()[-1] if text.strip() else ""
    return last in FORBIDDEN_ENDINGS


class DutchProductNameGenerator:

    def generate(self, source_name: str) -> str | None:
        if not source_name or not source_name.strip():
            return None

        lower = source_name.strip().lower()

        # Try full-name template lookup first
        for de_pattern, nl_base in sorted(NAME_TEMPLATES.items(), key=lambda x: len(x[0]), reverse=True):
            if de_pattern in lower:
                # Extract the part after the matched pattern (suffix/variant)
                idx = lower.find(de_pattern) + len(de_pattern)
                suffix = source_name[idx:].strip()
                suffix = _apply_word_replacements(suffix)

                result = nl_base
                if suffix:
                    # Append cleaned suffix
                    result = f"{nl_base} {suffix}".strip()

                if _ends_with_forbidden(result):
                    return nl_base  # fall back to base without problematic suffix
                return result

        return None

    def translate_or_passthrough(self, source_name: str) -> tuple[str, bool]:
        generated = self.generate(source_name)
        if generated:
            return generated, True
        return source_name, False


_instance: DutchProductNameGenerator | None = None


def get_name_generator() -> DutchProductNameGenerator:
    global _instance
    if _instance is None:
        _instance = DutchProductNameGenerator()
    return _instance
