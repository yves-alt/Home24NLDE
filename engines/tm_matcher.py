import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

from rapidfuzz import fuzz, process
from database.database import get_connection


class MatchType(str, Enum):
    EXACT = "exact"
    FUZZY = "fuzzy"
    PATTERN = "pattern"
    NONE = "none"


@dataclass
class TMMatch:
    source: str
    target: str
    score: float
    match_type: MatchType
    frequency: int = 0
    category: str = "general"


def normalize(text: str) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s+", " ", text)
    return text


class TMatcher:
    def __init__(self, fuzzy_threshold: float = 0.75):
        self.fuzzy_threshold = fuzzy_threshold
        self._cache: dict[str, TMMatch | None] = {}
        self._tm_index: list[tuple[str, str, str, int, str]] | None = None

    def _load_index(self):
        if self._tm_index is not None:
            return
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT normalized_source, source_segment, target_segment, frequency, category "
                "FROM translation_memory ORDER BY frequency DESC"
            ).fetchall()
        self._tm_index = [
            (r["normalized_source"], r["source_segment"], r["target_segment"], r["frequency"], r["category"])
            for r in rows
        ]

    def reload(self):
        self._tm_index = None
        self._cache.clear()
        self._load_index()

    def match(self, source: str) -> TMMatch | None:
        norm = normalize(source)
        if norm in self._cache:
            return self._cache[norm]

        result = self._exact_match(norm) or self._fuzzy_match(norm, source) or self._pattern_match(source)
        self._cache[norm] = result
        return result

    def _exact_match(self, norm: str) -> TMMatch | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT source_segment, target_segment, frequency, category "
                "FROM translation_memory WHERE normalized_source=? ORDER BY frequency DESC LIMIT 1",
                (norm,),
            ).fetchone()
        if row:
            return TMMatch(
                source=row["source_segment"],
                target=row["target_segment"],
                score=1.0,
                match_type=MatchType.EXACT,
                frequency=row["frequency"],
                category=row["category"],
            )
        return None

    def _fuzzy_match(self, norm: str, original: str) -> TMMatch | None:
        self._load_index()
        if not self._tm_index:
            return None

        keys = [entry[0] for entry in self._tm_index]
        results = process.extract(norm, keys, scorer=fuzz.token_sort_ratio, limit=5, score_cutoff=int(self.fuzzy_threshold * 100))

        if not results:
            return None

        best_key, best_score, best_idx = results[0]
        best_score_norm = best_score / 100.0

        if best_score_norm < self.fuzzy_threshold:
            return None

        entry = self._tm_index[best_idx]
        return TMMatch(
            source=entry[1],
            target=entry[2],
            score=best_score_norm,
            match_type=MatchType.FUZZY,
            frequency=entry[3],
            category=entry[4],
        )

    def _pattern_match(self, source: str) -> TMMatch | None:
        patterns = [
            (r"^(\w+)\s+(\w+)\s+(\w+)$", self._match_product_name_pattern),
            (r"^(\w+)\s*/\s*(\w+)$", self._match_color_combination),
        ]
        for pattern, handler in patterns:
            m = re.match(pattern, source.strip())
            if m:
                result = handler(m, source)
                if result:
                    return result
        return None

    def _match_product_name_pattern(self, match, source: str) -> TMMatch | None:
        type_word = match.group(1)
        norm = normalize(type_word)
        with get_connection() as conn:
            row = conn.execute(
                "SELECT target_segment, frequency FROM translation_memory "
                "WHERE normalized_source=? ORDER BY frequency DESC LIMIT 1",
                (norm,),
            ).fetchone()
        if row:
            rest = source[len(type_word):].strip()
            target = f"{row['target_segment']} {rest}"
            return TMMatch(
                source=source,
                target=target,
                score=0.7,
                match_type=MatchType.PATTERN,
                frequency=row["frequency"],
            )
        return None

    def _match_color_combination(self, match, source: str) -> TMMatch | None:
        c1, c2 = match.group(1), match.group(2)
        t1 = self._exact_match(normalize(c1))
        t2 = self._exact_match(normalize(c2))
        if t1 and t2:
            return TMMatch(
                source=source,
                target=f"{t1.target}/{t2.target}",
                score=0.85,
                match_type=MatchType.PATTERN,
                frequency=min(t1.frequency, t2.frequency),
            )
        return None


_instance: TMatcher | None = None


def get_matcher(fuzzy_threshold: float = 0.75) -> TMatcher:
    global _instance
    if _instance is None:
        _instance = TMatcher(fuzzy_threshold=fuzzy_threshold)
    return _instance
