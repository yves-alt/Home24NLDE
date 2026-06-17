"""Adaptive Translation Memory (PART 3).

The old engine copied a fuzzy TM target verbatim, so "Tischleuchte Paku"
matched "Tischleuchte Ledo" and shipped the wrong model ("Baldo"). This engine
refuses to do that.

Two safe modes only:

* EXACT   — the source is byte-for-byte identical (after normalization) to a
            stored TM source. The stored target is trustworthy → use it.
* ADAPTED — after masking model names in BOTH the current source and a TM
            candidate, the *structure* is identical (same words, same numbers,
            same colors — differing only in the model name). The TM target,
            with its model placeholder refilled by the CURRENT model, is then a
            correct translation pattern. "Tischleuchte Ledo → Tafellamp Baldo"
            applied to "Tischleuchte Paku" yields "Tafellamp Paku".

If neither holds, AdaptiveTM returns NONE — it never guesses a full target.
"""

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

from rapidfuzz import fuzz, process

from database.database import get_connection
from engines.nl.model_protector import get_model_protector, _PLACEHOLDER_RE


class TMKind(str, Enum):
    EXACT = "TM_EXACT"
    ADAPTED = "TM_ADAPTED"
    NONE = "NONE"


@dataclass
class AdaptiveResult:
    kind: TMKind
    target: str | None
    score: float
    note: str = ""


def normalize(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text.lower().strip())
    return re.sub(r"\s+", " ", text)


def _placeholders(text: str) -> list[str]:
    return _PLACEHOLDER_RE.findall(text)


class AdaptiveTranslationMemoryEngine:
    def __init__(self, fuzzy_threshold: float = 0.82):
        self.fuzzy_threshold = fuzzy_threshold
        self._protector = get_model_protector()
        self._exact: dict[str, str] | None = None        # norm source -> target
        self._index: list[tuple[str, str, str]] | None = None  # (norm, source, target)

    def _load(self):
        if self._exact is not None:
            return
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT normalized_source, source_segment, target_segment "
                "FROM translation_memory WHERE target_segment IS NOT NULL "
                "ORDER BY frequency DESC"
            ).fetchall()
        exact: dict[str, str] = {}
        index: list[tuple[str, str, str]] = []
        for r in rows:
            src = r["source_segment"] or ""
            tgt = r["target_segment"] or ""
            norm = r["normalized_source"] or normalize(src)
            if not src or not tgt:
                continue
            # Skip degenerate/noise rows where source == target (header imports).
            if normalize(src) == normalize(tgt):
                continue
            exact.setdefault(norm, tgt)
            index.append((norm, src, tgt))
        self._exact = exact
        self._index = index

    def reload(self):
        self._exact = None
        self._index = None
        self._load()

    def lookup(self, source: str) -> AdaptiveResult:
        if not source or not source.strip():
            return AdaptiveResult(TMKind.NONE, None, 0.0)
        self._load()

        norm = normalize(source)

        # 1. Exact, truly-identical source.
        if norm in self._exact:
            return AdaptiveResult(TMKind.EXACT, self._exact[norm], 1.0, "exact source")

        # 2. Adapted: structure identical after masking models.
        return self._adapt(source)

    def _adapt(self, source: str) -> AdaptiveResult:
        cur = self._protector.protect(source)
        cur_masked_norm = normalize(cur.text)
        cur_phs = _placeholders(cur.text)

        if not cur_phs:
            # No model to swap → adaptation can't help; avoid blind fuzzy copy.
            return AdaptiveResult(TMKind.NONE, None, 0.0)

        # Fuzzy-shortlist candidate TM sources (these differ from `source` mainly
        # in the model name, so similarity is high).
        norm = normalize(source)
        keys = [entry[0] for entry in self._index]
        candidates = process.extract(
            norm, keys, scorer=fuzz.token_sort_ratio, limit=8,
            score_cutoff=int(self.fuzzy_threshold * 100),
        )

        for _key, score, idx in candidates:
            _n, cand_src, cand_tgt = self._index[idx]
            t_src = self._protector.protect(cand_src)
            t_tgt = self._protector.protect(cand_tgt)

            # Structure must be identical once models are masked.
            if normalize(t_src.text) != cur_masked_norm:
                continue
            src_phs = _placeholders(t_src.text)
            tgt_phs = _placeholders(t_tgt.text)
            # Same models must appear in source and target, and align 1:1 with
            # the current source's models.
            if not src_phs or set(src_phs) != set(tgt_phs):
                continue
            if len(src_phs) != len(cur_phs):
                continue

            # Refill the target's placeholders with the CURRENT model names,
            # mapping by placeholder order (M1→M1, M2→M2…).
            adapted = t_tgt.text
            ok = True
            for ph in set(tgt_phs):
                if ph not in cur.mapping:
                    ok = False
                    break
                adapted = adapted.replace(ph, cur.mapping[ph])
            if not ok or _PLACEHOLDER_RE.search(adapted):
                continue

            return AdaptiveResult(
                TMKind.ADAPTED, adapted, score / 100.0,
                f"adapted from TM '{cand_src}' → '{cand_tgt}'",
            )

        return AdaptiveResult(TMKind.NONE, None, 0.0)


_instance: AdaptiveTranslationMemoryEngine | None = None


def get_adaptive_tm() -> AdaptiveTranslationMemoryEngine:
    global _instance
    if _instance is None:
        _instance = AdaptiveTranslationMemoryEngine()
    return _instance
