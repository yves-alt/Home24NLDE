"""Home24.nl terminology brain.

The single deterministic source of DE→NL terminology. Everything here is
rule-based and explainable — no ML, no fuzzy guessing. Glossary and human
review (loaded from the database) override these defaults.

Application order matters and is fixed:
  1. Phrase patterns   (decor combos, multi-word compounds)  — highest priority
  2. Colon labels      (Bezug: → Bekleding:)
  3. Product types     (Tischleuchte → Tafellamp)            — case-matched
  4. Function words / colors / materials / misc terms
  5. Dutch style normalization (slash spacing, IJ, whitespace)

Colors and materials always render lowercase (Home24.nl style); product types
match the source capitalization so "Tischleuchte Paku" → "Tafellamp Paku" but
"… tischleuchte" → "… tafellamp".
"""

import re


# ── 1. Phrase patterns (multi-word, highest priority) ──────────────────
# Decor / wood-look combinations reorder and must run before single words.
_PHRASES: list[tuple[str, str]] = [
    # Wood-look with explicit style names (most specific first)
    (r"\bEiche\s+Sägerau\s+Dekor\b", "grof gezaagde eikenlook"),
    (r"\bEiche\s+Nordic\s+Dekor\b", "Nordic eikenlook"),
    (r"\bEiche\s+Hell\s+Dekor\b", "lichte eikenlook"),
    (r"\bEiche\s+Hellbraun\s+Dekor\b", "lichtbruine eikenlook"),
    (r"\bMarmor\s+Wei(?:ß|ss?)\s+Dekor\b", "witte marmerlook"),
    (r"\bMarmor\s+Schwarz\s+Dekor\b", "zwarte marmerlook"),
    (r"\bAltholz\s+Dekor\b", "oud-houtlook"),
    (r"\bNussbaum\s+Dekor\b", "notenlook"),
    (r"\bBeton\s+Dekor\b", "betonlook"),
    (r"\bEiche\s+Dekor\b", "eikenlook"),
    # Wood species without Dekor (standalone)
    (r"\bEiche\s+Sägerau\b", "grof gezaagde eiken"),
    (r"\bEiche\s+Nordic\b", "Nordic eiken"),
    (r"\bEiche\s+Hell\b", "lichte eiken"),
    # Compound product types — in _PHRASES so they override TM when clean.
    (r"\bEck-Wandregal\b", "open hoek-wandkast"),
    (r"\bSpülenunterschrank\b", "spoelkast"),
    (r"\bMineralite-Einbauspüle\b", "Mineralite-inbouwspoelbak"),
    (r"\bLED-Einbauleuchte\b", "LED-inbouwlamp"),
    (r"\bÜberlaufgarnitur\b", "overloopgarnituur"),
    # Structural phrases
    (r"\bset\s+bestehend\s+aus\b", "set bestaande uit"),
    (r"\bbestehend\s+aus\b", "bestaande uit"),
    (r"\bohne\s+Dekoration\b", "zonder decoratie"),
    (r"\bmit\s+Dekoration\b", "met decoratie"),
    (r"\bKombi\s+aus\b", "combinatie van"),
    (r"\binkl(?:usive)?\s+Montage\b", "incl. montage"),
    (r"\bexkl(?:usive)?\s+Montage\b", "excl. montage"),
    (r"\bPflegeleicht\s+und\s+wetterfest\b", "onderhoudsvriendelijk en weerbestendig"),
    (r"\bPflegeleicht\s+und\s+strapazierfähig\b", "onderhoudsvriendelijk en slijtvast"),
    (r"\bMaße\s*\(\s*B\s*[xX]\s*H\s*[xX]\s*T\s*\)", "afmetingen (B x H x D)"),
    (r"\bMaße\s*\(\s*B\s*[xX]\s*T\s*[xX]\s*H\s*\)", "afmetingen (B x D x H)"),
    (r"\baus\s+massivem\s+Holz\b", "van massief hout"),
    (r"\baus\s+Massivholz\b", "van massief hout"),
    (r"\bim\s+skandinavischen\s+Stil\b", "in Scandinavische stijl"),
    (r"\bim\s+Landhausstil\b", "in landelijke stijl"),
    (r"\bim\s+Industriestil\b", "in industriële stijl"),
    # n-flammig → n-lichts (lighting)
    (r"\b(\d+)\s*-?\s*flammig\b", r"\1-lichts"),
]

# ── 2. Colon labels (structural "Label: value" lines) ──────────────────
# Canonical Dutch label (capitalized) — these only match the colon form.
_LABELS: dict[str, str] = {
    "Bezug": "Bekleding",
    "Füße": "Poten",
    "Füsse": "Poten",
    "Fuß": "Poot",
    "Gestell": "Frame",
    "Korpus": "Body",
    "Farbe": "Kleur",
    "Material": "Materiaal",
    "Arbeitsplatte": "Werkblad",
    "Sitzfläche": "Zitvlak",
    "Rückenlehne": "Rugleuning",
    "Armlehne": "Armleuning",
    "Kopfteil": "Hoofdeinde",
    "Matratze": "Matras",
    "Tischplatte": "Tafelblad",
    "Schubladen": "Laden",
    "Schublade": "Lade",
    "Türen": "Deuren",
    "Tür": "Deur",
    "Lieferumfang": "Leveringsomvang",
    "Maße": "Afmetingen",
    "Maß": "Afmeting",
    "Breite": "Breedte",
    "Höhe": "Hoogte",
    "Tiefe": "Diepte",
    "Frontblende": "Frontpaneel",
    "Front": "Voorkant",
    "Nische": "Nis",
}

# ── 3. Product types (case-matched) ────────────────────────────────────
# Used both for inline replacement and as head-noun lookup by the name
# engine and adaptive TM (see PRODUCT_TYPE_MAP below).
_PRODUCT_TYPES: dict[str, str] = {
    "Tischleuchte": "tafellamp",
    "Deckenleuchte": "plafondlamp",
    "Steckerleuchte": "stekkerlamp",
    "Stehleuchte": "vloerlamp",
    "Wandleuchte": "wandlamp",
    "Pendelleuchte": "hanglamp",
    "Hängeleuchte": "hanglamp",
    "LED-Einbauleuchte": "LED-inbouwlamp",
    "Einbauleuchte": "inbouwlamp",
    "Einbauspot": "inbouwspot",
    "Singleküche": "mini keuken",
    "Miniküche": "mini keuken",
    "Küchenzeile": "keukenblok",
    "Kücheninsel": "kookeiland",
    "Eck-Wandregal": "open hoek-wandkast",
    "Wandregal": "open wandkast",
    "Standregal": "open kast",
    "Bücherregal": "boekenkast",
    "Spülenunterschrank": "spoelkast",
    "Unterschrank": "onderkast",
    "Oberschrank": "bovenkast",
    "Hängeschrank": "hangkast",
    "Mineralite-Einbauspüle": "Mineralite-inbouwspoelbak",
    "Einbauspüle": "inbouwspoelbak",
    "Überlaufgarnitur": "overloopgarnituur",
    "Bartisch": "bartafel",
    "Beistelltisch": "bijzettafel",
    "Couchtisch": "salontafel",
    "Esstisch": "eettafel",
    "Schreibtisch": "bureau",
    "Herrendiener": "herenknecht",
    "Tellerstand": "bordenstandaard",
    "Duschmatte": "douchemat",
    # Basic furniture words (also in residue_detector, added here so no GPT needed)
    "Esstisch": "eettafel",
    "Couchtisch": "salontafel",
    "Beistelltisch": "bijzettafel",
    "Schreibtisch": "bureau",
    "Tisch": "tafel",
    "Stuhl": "stoel",
    "Sessel": "fauteuil",
    "Schrank": "kast",
    "Regal": "rek",
    "Bett": "bed",
    "Sofa": "bank",
    "Kleiderschrank": "kledingkast",
    "Nachttisch": "nachtkastje",
    "Kommode": "ladekast",
    "Badewanne": "bad",
    "Dusche": "douche",
    "Spiegel": "spiegel",
    "Teppich": "tapijt",
    "Kissen": "kussen",
    "Decke": "deken",
    "Lampe": "lamp",
    "Leuchte": "lamp",
}

# ── 4a. Misc terms (canonical, lowercase unless special) ───────────────
_MISC: dict[str, str] = {
    "Milchglas": "melkglas",
    "Mikrowelle": "magnetron",
    "Beleuchtung": "verlichting",
    "Dekor": "look",
    "Decor": "look",
    "Eisen": "IJzer",          # special: capital IJ always
    "Edelstahl": "rvs",
    "Bettwäsche": "beddengoed",
    "Rollen": "rollen",
    "Liegehöhe": "lighoogte",
    "Sitzhöhe": "zithoogte",
    "Armlehnenhoehe": "armleuninghoogte",
    "Armlehnnhöhe": "armleuninghoogte",
    "Pflegeleicht": "onderhoudsvriendelijk",
    "platzsparend": "ruimtebesparend",
    "multifunktional": "multifunctioneel",
    "Softclose": "soft-close",
    "TÜV-geprüft": "TÜV-gecertificeerd",
    "FSC-zertifiziert": "FSC-gecertificeerd",
    "modernes Design": "modern design",
    "Lederoptik": "lederimitatie",
}

# ── 4b. Colors (always lowercase) ──────────────────────────────────────
_COLORS: dict[str, str] = {
    "Schwarz": "zwart",
    "Schwarzbraun": "zwartbruin",
    "Weiß": "wit",
    "Weiss": "wit",
    "Hellgrau": "lichtgrijs",
    "Dunkelgrau": "donkergrijs",
    "Grau": "grijs",
    "Hellbraun": "lichtbruin",
    "Dunkelbraun": "donkerbruin",
    "Braun": "bruin",
    "Hellblau": "lichtblauw",
    "Dunkelblau": "donkerblauw",
    "Blau": "blauw",
    "Grün": "groen",
    "Olivgrün": "olijfgroen",
    "Oliv": "olijfgroen",
    "Gelb": "geel",
    "Rot": "rood",
    "Orange": "oranje",
    "Rosa": "roze",
    "Lila": "lila",
    "Violett": "paars",
    "Türkis": "turquoise",
    "Silber": "zilver",
    "Gold": "goud",
    "Sandfarben": "zand",
    "Sand": "zand",
    "Beige": "beige",
    "Anthrazit": "antraciet",
    "Schwarzbraun": "zwartbruin",
    "Hellblau": "lichtblauw",
    "Dunkelblau": "donkerblauw",
    "Olivgrün": "olijfgroen",
    "Oliv": "olijfgroen",
    "Hell": "licht",
    "Dunkel": "donker",
    "Mehrfarbig": "meerkleurig",
    "Violett": "paars",
    "Türkis": "turquoise",
    "Silber": "zilver",
}

# ── 4c. Materials / textiles (always lowercase) ────────────────────────
_MATERIALS: dict[str, str] = {
    "Metall": "metaal",
    "Holz": "hout",
    "Massivholz": "massief hout",
    "Leder": "leer",
    "Kunststoff": "kunststof",
    "Glas": "glas",
    "Stahl": "staal",
    "Aluminium": "aluminium",
    "Microfaser": "microvezel",
    "Mikrofaser": "microvezel",
    "Samtstoff": "fluweel",
    "Samt": "fluweel",
    "Velours": "velours",
    "Baumwolle": "katoen",
    "Leinen": "linnen",
    "Wolle": "wol",
    "Seide": "zijde",
    "Eiche": "eikenhout",
    "Marmor": "marmer",
    "Altholz": "oud hout",
    "Beton": "beton",
    "Nussbaum": "notenhout",
    "Buche": "beukenhout",
    "Kiefer": "grenenhout",
    "Fichte": "vurenhout",
    "Akazie": "acaciahout",
    "Esche": "essenhout",
    "Stahl": "staal",
    "Seide": "zijde",
    "Eisen": "IJzer",          # duplicate of _MISC; longest-first ordering handles both
    "lackiert": "gelakt",
    "beschichtet": "gecoat",
    "foliert": "gefolieerd",
    "pulverbeschichtet": "poedergecoat",
    "massiv": "massief",
    "handgemacht": "handgemaakt",
    "handgefertigt": "handgemaakt",
    "nachhaltig": "duurzaam",
    "umweltfreundlich": "milieuvriendelijk",
}

# ── 4d. Function / connector words (lowercase) ─────────────────────────
_FUNCTION: dict[str, str] = {
    "ohne": "zonder",
    "mit": "met",
    "und": "en",
    "oder": "of",
    "für": "voor",
    "von": "van",
    "aus": "van",
    "auf": "op",
    "nach": "naar",
    "inklusive": "inclusief",
    "inkl": "incl.",
    "exklusive": "exclusief",
    "exkl": "excl.",
    "Eck": "hoek",
}


# ── compile ─────────────────────────────────────────────────────────────

def _build_phrase_entries() -> list[tuple[re.Pattern, object]]:
    return [(re.compile(pat, re.IGNORECASE), repl) for pat, repl in _PHRASES]


def _build_entries() -> list[tuple[re.Pattern, object]]:
    entries: list[tuple[re.Pattern, object]] = []

    # 1. phrases
    entries.extend(_build_phrase_entries())

    # 2a. colon labels — "Bezug:" → "Bekleding:" (must precede standalone form)
    for de, nl in sorted(_LABELS.items(), key=lambda kv: -len(kv[0])):
        entries.append((re.compile(rf"\b{re.escape(de)}\s*:", re.IGNORECASE), f"{nl}:"))

    # 2b. standalone labels — "Bezug" → "bekleding" (lowercase, no colon)
    for de, nl in sorted(_LABELS.items(), key=lambda kv: -len(kv[0])):
        entries.append((re.compile(rf"\b{re.escape(de)}\b", re.IGNORECASE), nl.lower()))

    # 3. product types (longest first so "Eck-Wandregal" beats "Wandregal").
    #    Rendered lowercase (canonical) — casing is column-dependent, so the
    #    name engine title-cases the `name` column while other columns stay
    #    lowercase. This keeps "Milchglas → melkglas" (material) and
    #    "Singleküche → mini keuken → Mini keuken" (name) both correct.
    for de, nl in sorted(_PRODUCT_TYPES.items(), key=lambda kv: -len(kv[0])):
        entries.append((re.compile(rf"\b{re.escape(de)}\b", re.IGNORECASE), nl))

    # 4. misc / colors / materials / function words.
    #    Colors & materials are fixed-case (lowercase / IJzer); misc & function
    #    keep their canonical case as written.
    fixed_case = {**_COLORS, **_MATERIALS}
    case_special = {**_MISC, **_FUNCTION}
    combined = sorted(
        list(fixed_case.items()) + list(case_special.items()),
        key=lambda kv: -len(kv[0]),
    )
    for de, nl in combined:
        entries.append((re.compile(rf"\b{re.escape(de)}\b", re.IGNORECASE), nl))

    return entries


# Critical German tokens that must NEVER survive to export. Used by the
# residue gate as the hard blocker list (auto-fix is attempted first).
CRITICAL_GERMAN = re.compile(
    r"\b(?:ohne|mit|und|oder|für|von|aus|inkl|inklusive|exkl|exklusive|Kombi"
    # Colors — German-only, unambiguous
    r"|Schwarz|Schwarzbraun|Wei(?:ß|ss?)|Grau|Hellgrau|Dunkelgrau"
    r"|Braun|Hellbraun|Dunkelbraun|Grün|Olivgrün|Oliv|Gelb"
    r"|Blau|Hellblau|Dunkelblau|Rot|Violett|Türkis|Silber|Anthrazit"
    r"|Mehrfarbig|Sandfarben|Hell|Dunkel|Dekor|Decor"
    # Materials — German-only
    r"|Metall|Holz|Leder|Kunststoff|Eiche|Nussbaum|Buche|Edelstahl|Altholz"
    r"|Marmor|Stahl|Seide|Eisen"
    r"|pulverbeschichtet|lackiert|beschichtet|foliert|massiv"
    # Labels / furniture terms
    r"|Bezug|Füße|Füsse|Fuß|Gestell|Korpus|Farbe|Microfaser|Mikrofaser|Samtstoff|Baumwolle|Leinen|Wolle"
    r"|Schublade|Schubladen|Lieferumfang|Maße|Breite|Höhe|Tiefe"
    r"|Arbeitsplatte|Sitzfläche|Rückenlehne|Armlehne|Kopfteil|Tischplatte|Matratze"
    # Lighting / kitchen / storage
    r"|Tischleuchte|Deckenleuchte|Steckerleuchte|Einbauleuchte|Wandleuchte|Stehleuchte"
    r"|Singleküche|Miniküche|Unterschrank|Oberschrank|Hängeschrank|Wandregal|Bartisch"
    r"|Milchglas|Mikrowelle|Beleuchtung|Nische|Frontblende|Spülenunterschrank|Überlaufgarnitur"
    r"|Türen|Tür|Eck|Beistelltisch|Couchtisch|Esstisch)\b",
    re.IGNORECASE,
)

# Broad German-prose markers for catching freeform German that the curated
# catalog list misses. These are German-ONLY words — none is a valid Dutch
# word (Dutch shares "die"/"in"/"een"/"met", so those are deliberately
# excluded to avoid false positives on real Dutch output).
GERMAN_MARKERS = re.compile(
    r"\b(?:und|mit|für|von|aus|ist|sind|wird|werden|das|dieser|diese|dieses"
    r"|ein|eine|einen|einem|einer|eines|auch|sehr|durch|sowie|sowohl|nicht|kein|keine"
    r"|oder|ohne|im|zum|zur|beim|bietet|sorgt|sorgen|verfügt|ermöglicht|bestehen"
    r"|gemütlich|gemütliche|hochwertig|hochwertige|jeden|jede|jedes|wodurch|dabei"
    r"|Stauraum|Wohnzimmer|Schlafzimmer|Esszimmer|Kinderzimmer|Lieferung|Verpackung)\b",
    re.IGNORECASE,
)

# ä/ö/ü/ß do not occur in Dutch — any survivor signals untranslated German.
_UMLAUT_WORD = re.compile(r"\b\w*[äöüßÄÖÜ]\w*\b")


class Home24TerminologyBrain:
    """Deterministic DE→NL terminology engine."""

    def __init__(self):
        self._entries = _build_entries()
        self._phrase_entries = _build_phrase_entries()

    # product-type head-noun map (DE → NL, lowercase nl) for the name engine
    # and adaptive TM pattern extraction.
    PRODUCT_TYPE_MAP = {**_PRODUCT_TYPES}

    def apply(self, text: str) -> tuple[str, int]:
        """Apply all terminology rules. Returns (text, replacement_count)."""
        if not text:
            return text, 0
        result = text
        hits = 0
        for pat, repl in self._entries:
            result, n = pat.subn(repl, result)
            hits += n
        result = self._normalize_style(result)
        return result, hits

    def apply_phrases(self, text: str) -> tuple[str, int]:
        """Apply only the high-priority spec phrase patterns (decor combos,
        multi-word compounds). Returns (text, match_count). Used to give these
        spec-canonical forms authority over generic TM entries."""
        if not text:
            return text, 0
        result = text
        hits = 0
        for pat, repl in self._phrase_entries:
            result, n = pat.subn(repl, result)
            hits += n
        return result, hits

    def _normalize_style(self, text: str) -> str:
        # Color/material combinations use a slash without surrounding spaces:
        # "melkglas / IJzer" → "melkglas/IJzer".
        text = re.sub(r"\s+/\s+", "/", text)
        # IJ capitalization fix.
        text = re.sub(r"\bIjzer\b", "IJzer", text)
        # Collapse accidental double spaces (but keep <br> intact).
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()

    def remaining_german(self, text: str) -> list[str]:
        """Return German tokens still present (dedup, order-preserving).

        Combines the curated catalog list, broad German-prose markers, and the
        ä/ö/ü/ß orthographic signal so freeform German cannot pass as clean.
        """
        if not text:
            return []
        found = CRITICAL_GERMAN.findall(text)
        found += GERMAN_MARKERS.findall(text)
        found += _UMLAUT_WORD.findall(text)
        return list(dict.fromkeys(found))

    def product_type_nl(self, de_word: str) -> str | None:
        """Look up the NL head noun for a German product-type word."""
        return self.PRODUCT_TYPE_MAP.get(de_word) or self.PRODUCT_TYPE_MAP.get(de_word.capitalize())


_instance: Home24TerminologyBrain | None = None


def get_terminology() -> Home24TerminologyBrain:
    global _instance
    if _instance is None:
        _instance = Home24TerminologyBrain()
    return _instance
