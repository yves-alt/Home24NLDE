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

    def _is_model_token(self, tok: str, aggressive: bool) -> bool:
        low = tok.lower()
        if low in CURATED_MODELS:
            return True
        if low in _VOCAB:
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
