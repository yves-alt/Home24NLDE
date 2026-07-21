"""Model / product-name protection (PART 4).

Detects likely product model names ("Paku", "Ingrid", "Fit Move II") and
masks them as ⟦M1⟧ placeholders before any TM or GPT step touches the text,
then restores the exact originals afterwards. No downstream step is allowed
to translate or alter a model name.

The protector is deliberately conservative: it masks a curated set of known
Home24 model names, clear product codes (mixed letters+digits, roman
numerals), and capitalized tokens that are not part of the known DE/NL
vocabulary. It never masks pure numbers, units, or known terminology words.
"""

import re
from dataclasses import dataclass, field

from engines.nl.terminology import _PRODUCT_TYPES, _COLORS, _MATERIALS, _MISC, _LABELS, _FUNCTION


# Curated, high-confidence model names seen in Home24 catalogs.
CURATED_MODELS = {
    "paku", "pilo", "banyo", "arik", "ingrid", "ledo", "malia", "levin",
    "baldo", "fit", "move", "nordic", "oslo", "alba", "luna", "rio",
    "vera", "kai", "nora", "felix", "aris", "solo", "duo", "trio",
}

# Words that look capitalized but are ordinary vocabulary — never masked.
# Built from the terminology brain plus common DE/NL function words.
_COMMON = {
    "de", "het", "een", "en", "of", "met", "voor", "van", "uit", "op", "in",
    "bij", "naar", "tot", "per", "als", "set", "incl", "excl", "inclusief",
    "exclusief", "combinatie", "zonder", "der", "die", "das", "und", "oder",
    "mit", "ohne", "aus", "für", "cm", "mm", "kg", "led", "mdf", "rvs",
}


def _build_vocab() -> set[str]:
    vocab: set[str] = set(_COMMON)
    for mapping in (_PRODUCT_TYPES, _COLORS, _MATERIALS, _MISC, _LABELS, _FUNCTION):
        for de, nl in mapping.items():
            vocab.add(de.lower())
            for w in re.split(r"[\s/\-]+", str(nl).lower()):
                if w:
                    vocab.add(w)
    return vocab


_VOCAB = _build_vocab()


def _load_glossary_product_types() -> set[str]:
    """Product-type nouns discovered from the official glossary's imported
    "ProductType ModelName" pairs (the first word of each 2-word TM source
    segment). Without this, a product type outside the small hardcoded
    _PRODUCT_TYPES dict — e.g. "Klapptisch", which only exists via the
    imported glossary — looks like an unknown capitalized word and gets
    merged into the model-name placeholder run alongside the real model name
    (producing a false "model name lost" quality-gate failure once the
    product type is correctly translated and the model name isn't)."""
    try:
        from database.database import get_connection
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT source_segment FROM translation_memory "
                "WHERE created_by='OFFICIAL_GLOSSARY'"
            ).fetchall()
    except Exception:
        return set()
    extra: set[str] = set()
    for r in rows:
        words = (r["source_segment"] or "").split()
        if len(words) == 2:
            extra.add(words[0].lower())
    return extra


_PLACEHOLDER = "⟦M{}⟧"
_PLACEHOLDER_RE = re.compile(r"⟦M\d+⟧")

# Token = word (letters, digits, hyphens, dots) — punctuation handled separately.
_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ0-9]+(?:[.\-][A-Za-zÀ-ÿ0-9]+)*|\s+|[^\sA-Za-zÀ-ÿ0-9]")
_ROMAN_RE = re.compile(r"^(?:II|III|IV|V|VI|VII|VIII|IX|X)$")


@dataclass
class ProtectedText:
    text: str                                  # masked text
    mapping: dict[str, str] = field(default_factory=dict)  # placeholder -> original

    @property
    def model_names(self) -> list[str]:
        return list(self.mapping.values())


class ModelNameProtector:

    def __init__(self):
        self._vocab = set(_VOCAB) | _load_glossary_product_types()

    def reload(self):
        """Refresh the glossary-sourced part of the vocabulary (call after a
        glossary import)."""
        self._vocab = set(_VOCAB) | _load_glossary_product_types()

    def _is_model_token(self, tok: str, aggressive: bool) -> bool:
        low = tok.lower()
        if low in CURATED_MODELS:
            return True
        if low in self._vocab:
            return False
        if tok.isdigit():
            return False
        if _ROMAN_RE.match(tok):
            return True
        # Letter-first mixed alphanumerics → product code (e.g. "X200", "T4", "S2").
        # Digit-first tokens ("3er-Set", "2er") are quantities/abbreviations, not
        # model names — left for the abbreviation resolver.
        if tok[:1].isalpha() and re.search(r"\d", tok):
            return True
        # Capitalized non-vocabulary word → likely a model name, BUT only in short
        # catalog-style segments. German prose capitalizes every noun, so applying
        # this in long text would mask real nouns and stop GPT translating them.
        if aggressive and tok[:1].isupper() and tok[1:].islower() and tok.isalpha() and len(tok) >= 2:
            return True
        return False

    # Segments with more word-tokens than this are treated as prose: the
    # capitalized-word heuristic is disabled so German nouns reach GPT.
    _SHORT_SEGMENT_WORDS = 5

    def protect(self, text: str, aggressive: bool | None = None) -> ProtectedText:
        if not text:
            return ProtectedText(text, {})

        tokens = _TOKEN_RE.findall(text)
        if aggressive is None:
            word_count = sum(1 for t in tokens if re.match(r"[A-Za-zÀ-ÿ0-9]", t))
            aggressive = word_count <= self._SHORT_SEGMENT_WORDS
        out: list[str] = []
        mapping: dict[str, str] = {}
        counter = 1
        run: list[str] = []  # consecutive model tokens + the spaces between them

        def _flush():
            nonlocal counter, run
            if not run:
                return
            # Trailing whitespace belongs after the placeholder, not inside it.
            trailing: list[str] = []
            while run and run[-1].isspace():
                trailing.insert(0, run.pop())
            if run:
                original = "".join(run)
                ph = _PLACEHOLDER.format(counter)
                mapping[ph] = original
                out.append(ph)
                counter += 1
            out.extend(trailing)
            run = []

        for tok in tokens:
            if tok.isspace():
                if run:
                    run.append(tok)  # may be interior (kept) or trailing (re-emitted)
                else:
                    out.append(tok)
            elif re.fullmatch(r"[A-Za-zÀ-ÿ0-9.\-]+", tok) and self._is_model_token(tok, aggressive):
                run.append(tok)
            else:
                _flush()
                out.append(tok)
        _flush()

        return ProtectedText("".join(out), mapping)

    def protect_name(self, text: str) -> ProtectedText:
        """Name-column-specific masking. Home24 names follow "ProductType
        Model [connector accessories...]" — the model name lives in the head,
        before the first connector. Forcing aggressive mode over the WHOLE
        string (needed so a model isn't missed just because a long list of
        accessories pushes the segment past the short-segment word-count
        cutoff) would also sweep up ordinary German nouns in later
        accessory/material clauses as fake "models", leaving them permanently
        untranslated. So: aggressive only in the head; conservative
        (vocab-aware) for the rest."""
        m = re.search(r"\b(mit|met|und|en|aus|von|inkl\.|incl\.)\b|[+&,]", text)
        if not m:
            return self.protect(text, aggressive=True)
        split_at = m.end()
        head, tail = text[:split_at], text[split_at:]
        head_p = self.protect(head, aggressive=True)
        tail_p = self.protect(tail, aggressive=False)
        merged_mapping = dict(head_p.mapping)
        tail_text = tail_p.text
        for i, (ph, original) in enumerate(tail_p.mapping.items(), start=1):
            new_ph = _PLACEHOLDER.format(len(head_p.mapping) + i)
            tail_text = tail_text.replace(ph, new_ph)
            merged_mapping[new_ph] = original
        return ProtectedText(head_p.text + tail_text, merged_mapping)

    def restore(self, text: str, mapping: dict[str, str]) -> str:
        for ph, original in mapping.items():
            text = text.replace(ph, original)
        return text

    def validate(self, mapping: dict[str, str], final_text: str) -> list[str]:
        """Return error strings for any model name that disappeared from output."""
        errors = []
        for original in mapping.values():
            if original not in final_text:
                errors.append(f"model name '{original}' lost in output")
        return errors

    @staticmethod
    def has_placeholders(text: str) -> bool:
        return bool(_PLACEHOLDER_RE.search(text))


_instance: ModelNameProtector | None = None


def get_model_protector() -> ModelNameProtector:
    global _instance
    if _instance is None:
        _instance = ModelNameProtector()
    return _instance
