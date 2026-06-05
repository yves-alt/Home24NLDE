import re


NATURALNESS_MAP: dict[str, str] = {
    # Furniture categories
    "kaminset": "haardset",
    "kaminbesteck": "haardset",
    "kaminzubehör": "haardaccessoires",
    "kaminrost": "haardraster",
    "kaminschirm": "haardscherm",
    "kaminholzkorb": "haardhoutmand",
    "tablett": "dienblad",
    "tellerstand": "bordenstandaard",
    "kücheninsel": "kookeiland",
    "küchenwagen": "keukentrolley",
    "küchenregal": "keukenrek",
    "küchenbank": "keukenbank",
    "küchenhocker": "keukenbarhocker",
    "küchenstuhl": "keukenstoel",
    "küchenschrank": "keukenkast",
    # Bathroom
    "duschmatte": "douchemat",
    "badewannenmatte": "badkuipmat",
    "bügelbrettbezug": "strijkplankhoes",
    "duschvorhang": "douchegordijn",
    "duschstange": "douchestang",
    "duschregal": "doucherek",
    "badhocker": "badkrukje",
    "badregal": "badkamerrek",
    "badschrank": "badkamerkast",
    "badtisch": "badkamertafel",
    "badteppich": "badmat",
    # Living room
    "sofatisch": "salontafel",
    "couchtisch": "salontafel",
    "wohnzimmertisch": "woonkamertafel",
    "bücherregal": "boekenkast",
    "tv-möbel": "tv-meubel",
    "tv-board": "tv-meubel",
    "fernsehschrank": "tv-kast",
    "hängeregal": "wandplank",
    "wandregal": "wandplank",
    "standregal": "staand rek",
    # Bedroom
    "nachttisch": "nachtkastje",
    "nachtkommode": "nachtkastje",
    "betttisch": "bedtafel",
    "kleiderhaken": "kledinghaak",
    "kleiderständer": "kledingrek",
    "kleiderstange": "kledingroede",
    "wäschekorb": "wasmand",
    "wäscheständer": "droogrek",
    # Outdoor
    "gartentisch": "tuintafel",
    "gartenstuhl": "tuinstoel",
    "gartenbank": "tuinbank",
    "gartenregal": "tuinrek",
    "blumentopf": "bloempot",
    "pflanzenkübel": "plantenbak",
    "pflanzentopf": "bloempot",
    # Materials / decors
    "sägerau dekor": "grof gezaagde look",
    "eiche sägerau dekor": "grof gezaagde eikenlook",
    "nussbaum dekor": "notenlook",
    "notelaar dekor": "notenlook",
    "beton dekor": "betonlook",
    "marmor dekor": "marmereffect",
    "walnuss dekor": "walnotenlook",
    "akazien dekor": "acacialook",
    "kastanie dekor": "kastanjelook",
    # Colors (common corrections)
    "mehrfarbig": "meerdere kleuren",
    "einfarbig": "eenkleurig",
    "zweifarbig": "tweekleurig",
    "dreifaribg": "driekleurig",
    # Common wrongly-kept German words
    "kaminbesteck-set": "haardset",
    "stövchen": "theelichthouder",
    "brotkorb": "broodmand",
    "schüssel": "schaal",
    "schüsseln": "schalen",
    "grillrost": "grillrooster",
}


class DutchNaturalnessRewriter:

    def rewrite(self, text: str) -> tuple[str, list[str]]:
        if not text:
            return text, []

        applied = []
        result = text

        for german, dutch in sorted(NATURALNESS_MAP.items(), key=lambda x: -len(x[0])):
            pattern = re.compile(re.escape(german), re.IGNORECASE)
            if pattern.search(result):
                result = pattern.sub(dutch, result)
                applied.append(f"{german} → {dutch}")

        return result, applied

    def add_rule(self, german: str, dutch: str):
        NATURALNESS_MAP[german.lower()] = dutch

    def get_rules(self) -> dict[str, str]:
        return dict(NATURALNESS_MAP)


_instance: DutchNaturalnessRewriter | None = None


def get_rewriter() -> DutchNaturalnessRewriter:
    global _instance
    if _instance is None:
        _instance = DutchNaturalnessRewriter()
    return _instance
