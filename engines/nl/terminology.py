"""Home24.nl terminology brain.

The single deterministic source of DE→NL terminology. Curated defaults below are
merged with the official DE→NL furniture glossary (imported via
``importers/glossary_importer.py`` into the ``glossary`` table,
``source_type='OFFICIAL_GLOSSARY'``) — the official glossary wins on conflict,
per the documented precedence: protected tokens > business rules > official
glossary > reviewed TM > these built-in rules > GPT > fallback.

Application order matters and is fixed:
  1. Phrase patterns   (decor combos, multi-word compounds)  — highest priority
  2. Colon labels      (Bezug: → Bekleding:)
  3. Product types     (Tischleuchte → Tafellamp)            — case-matched
  4. Function words / colors / materials / misc terms (+ official glossary)
  5. Dutch style normalization (slash spacing, IJ, whitespace)

Colors and materials always render lowercase (Home24.nl style); product types
match the source capitalization so "Tischleuchte Paku" → "Tafellamp Paku" but
"… tischleuchte" → "… tafellamp".

Layers 2–4 are matched with a tokenizer + dict lookup (unigram/bigram) rather
than one regex per term. The official glossary is ~14k entries — one
``pattern.subn()`` call per term (the original design) would mean thousands of
full-text scans per cell. Tokenizing once and doing O(1) dict lookups per
token/bigram keeps ``apply()`` fast regardless of glossary size, and naturally
prefers a 2-word match over a 1-word match (longest-match-first) without a
giant alternation regex, which has practical size/compile-time limits at this
scale.
"""

import re

from database.database import get_connection


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
    (r"\binkl(?:usive|\.)?\s+Montage\b", "incl. montage"),
    (r"\bexkl(?:usive|\.)?\s+Montage\b", "excl. montage"),
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


# ── tokenizer + dict-layer matching (scales to a 14k-term glossary) ────

# Word token = letters/digits, allowing interior hyphens/dots (compounds like
# "Eck-Wandregal"); everything else (spaces, punctuation) is its own token.
_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ0-9]+(?:[.\-][A-Za-zÀ-ÿ0-9]+)*|\s+|[^\sA-Za-zÀ-ÿ0-9]+")


class _DictLayer:
    """A case-insensitive DE→NL term layer matched by tokenizing the input and
    doing O(1) dict lookups (2-word bigram first, then 1-word), instead of one
    regex per term. Later-merged dicts win on key collision (used to let the
    official glossary override curated defaults)."""

    __slots__ = ("unigrams", "bigrams", "size")

    def __init__(self, *sources: dict):
        merged: dict[str, str] = {}
        for src in sources:
            merged.update(src)
        self.unigrams: dict[str, str] = {}
        self.bigrams: dict[str, str] = {}
        for de, nl in merged.items():
            key = de.strip().lower()
            if not key:
                continue
            if " " in key:
                self.bigrams[key] = nl
            else:
                self.unigrams[key] = nl
        self.size = len(self.unigrams) + len(self.bigrams)

    def apply(self, text: str) -> tuple[str, int]:
        if not text or self.size == 0:
            return text, 0
        tokens = _TOKEN_RE.findall(text)
        n = len(tokens)
        out: list[str] = []
        hits = 0
        i = 0
        while i < n:
            tok = tokens[i]
            if tok[:1].isalnum():
                if self.bigrams:
                    j = i + 1
                    if j < n and tokens[j].isspace():
                        j += 1
                    if j < n and tokens[j][:1].isalnum():
                        bigram_key = f"{tok} {tokens[j]}".lower()
                        repl = self.bigrams.get(bigram_key)
                        if repl is not None:
                            out.append(repl)
                            hits += 1
                            i = j + 1
                            continue
                repl = self.unigrams.get(tok.lower())
                if repl is not None:
                    out.append(repl)
                    hits += 1
                    i += 1
                    continue
            out.append(tok)
            i += 1
        return "".join(out), hits


class _ColonLabelLayer:
    """Matches a word/bigram token ONLY when immediately followed by ':' (optional
    whitespace in between) and replaces the whole "Label:" span with "NL:" —
    distinct from `_DictLayer` because it must not fire without the colon, and
    must consume the colon token so it isn't duplicated."""

    __slots__ = ("unigrams", "bigrams", "size")

    def __init__(self, pairs: dict[str, str]):
        # pairs: DE label -> NL label (no trailing colon)
        self.unigrams: dict[str, str] = {}
        self.bigrams: dict[str, str] = {}
        for de, nl in pairs.items():
            key = de.strip().lower()
            if not key:
                continue
            if " " in key:
                self.bigrams[key] = nl
            else:
                self.unigrams[key] = nl
        self.size = len(self.unigrams) + len(self.bigrams)

    def apply(self, text: str) -> tuple[str, int]:
        if not text or self.size == 0:
            return text, 0
        tokens = _TOKEN_RE.findall(text)
        n = len(tokens)
        out: list[str] = []
        hits = 0
        i = 0
        while i < n:
            tok = tokens[i]
            repl = None
            colon_idx = None
            if tok[:1].isalnum():
                if self.bigrams:
                    j = i + 1
                    if j < n and tokens[j].isspace():
                        j += 1
                    if j < n and tokens[j][:1].isalnum():
                        bigram_repl = self.bigrams.get(f"{tok} {tokens[j]}".lower())
                        if bigram_repl is not None:
                            k = j + 1
                            if k < n and tokens[k].isspace():
                                k += 1
                            if k < n and tokens[k][:1] == ":":
                                repl, colon_idx = bigram_repl, k
                if repl is None:
                    uni_repl = self.unigrams.get(tok.lower())
                    if uni_repl is not None:
                        k = i + 1
                        if k < n and tokens[k].isspace():
                            k += 1
                        if k < n and tokens[k][:1] == ":":
                            repl, colon_idx = uni_repl, k
            if repl is not None:
                tail = tokens[colon_idx][1:]  # anything after the colon in that punctuation run
                out.append(f"{repl}:{tail}")
                hits += 1
                i = colon_idx + 1
                continue
            out.append(tok)
            i += 1
        return "".join(out), hits


def _build_phrase_entries() -> list[tuple[re.Pattern, object]]:
    return [(re.compile(pat, re.IGNORECASE), repl) for pat, repl in _PHRASES]


def _load_official_glossary() -> tuple[dict[str, str], dict[str, str]]:
    """Return (colon_labels, general_terms) sourced from the imported official
    glossary. Product+model rows never land in the glossary table — the
    importer routes those straight into translation_memory for AdaptiveTM's
    pattern extraction — so a simple colon-suffix split is sufficient here."""
    labels: dict[str, str] = {}
    general: dict[str, str] = {}
    try:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT source_term, target_term FROM glossary "
                "WHERE active=1 AND source_type='OFFICIAL_GLOSSARY' AND target_language='nl'"
            ).fetchall()
    except Exception:
        return labels, general
    for row in rows:
        src = (row["source_term"] or "").strip()
        tgt = (row["target_term"] or "").strip()
        if not src or not tgt:
            continue
        if src.endswith(":"):
            labels[src[:-1].strip()] = tgt[:-1].strip() if tgt.endswith(":") else tgt
        else:
            general[src] = tgt
    return labels, general


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
        self._phrase_entries = _build_phrase_entries()
        self._db_labels, self._db_general = _load_official_glossary()
        self._rebuild_layers()

    # product-type head-noun map (DE → NL, lowercase nl) for the name engine
    # and adaptive TM pattern extraction.
    PRODUCT_TYPE_MAP = {**_PRODUCT_TYPES}

    def _rebuild_layers(self):
        # Colon-label layer: hardcoded + official glossary (glossary wins on
        # collision — later dict in the merge takes precedence).
        label_pairs = {**_LABELS, **self._db_labels}
        self._label_colon = _ColonLabelLayer(label_pairs)
        self._label_standalone = _DictLayer({de: nl.lower() for de, nl in label_pairs.items()})
        # Product types stay curated-only — case-matching/name-engine head-noun
        # lookup depends on this staying a small, deliberately-chosen set.
        self._product_types = _DictLayer(_PRODUCT_TYPES)
        # Misc/colors/materials/function + official general vocabulary — the
        # bulk of the glossary lands here. Official entries win on collision.
        self._misc = _DictLayer(_COLORS, _MATERIALS, _MISC, _FUNCTION, self._db_general)
        # Kept for external callers (settings/QA pages) that inspect rule count.
        self._entries = (
            list(label_pairs.items())
            + list(_PRODUCT_TYPES.items())
            + list(_COLORS.items()) + list(_MATERIALS.items())
            + list(_MISC.items()) + list(_FUNCTION.items())
            + list(self._db_general.items())
        )

    def reload(self):
        """Reload official-glossary entries from the DB (call after an import)."""
        self._db_labels, self._db_general = _load_official_glossary()
        self._rebuild_layers()

    def apply(self, text: str) -> tuple[str, int]:
        """Apply all terminology rules. Returns (text, replacement_count)."""
        if not text:
            return text, 0
        result = text
        hits = 0
        for pat, repl in self._phrase_entries:
            result, n = pat.subn(repl, result)
            hits += n
        result, n = self._label_colon.apply(result)
        hits += n
        result, n = self._label_standalone.apply(result)
        hits += n
        result, n = self._product_types.apply(result)
        hits += n
        result, n = self._misc.apply(result)
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
        # IJ capitalization fix — Dutch always capitalizes the IJ digraph at a
        # word start, regardless of which layer (hardcoded or DB glossary)
        # produced the lowercase/mixed-case form.
        text = re.sub(r"\bijzer\b", "IJzer", text, flags=re.IGNORECASE)
        # Collapse accidental double periods — e.g. "inkl." (source abbreviation,
        # trailing "." kept as its own token) replaced with "incl." (a value
        # that already ends in ".") produces "incl..": a dict-layer token
        # replacement can't know the source token it's replacing was itself
        # followed by an abbreviation-period. Never occurs in genuine Dutch text.
        text = re.sub(r"\.\.+", ".", text)
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
