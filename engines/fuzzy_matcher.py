from rapidfuzz import fuzz
from database.database import get_connection


class FuzzyMatcher:

    def __init__(self, threshold: float = 0.75):
        self.threshold = threshold
        self._index: list[tuple[str, str, str, int]] | None = None

    def _load(self):
        if self._index is not None:
            return
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT normalized_source, source_segment, target_segment, frequency "
                "FROM translation_memory ORDER BY frequency DESC LIMIT 20000"
            ).fetchall()
        self._index = [(r[0], r[1], r[2], r[3]) for r in rows]

    def reload(self):
        self._index = None
        self._load()

    def match(self, query: str, limit: int = 3) -> list[dict]:
        self._load()
        if not self._index:
            return []

        q = query.lower().strip()
        results = []

        for norm, src, tgt, freq in self._index:
            score = fuzz.token_sort_ratio(q, norm) / 100.0
            if score >= self.threshold:
                results.append({"source": src, "target": tgt, "score": score, "frequency": freq})

        results.sort(key=lambda x: (-x["score"], -x["frequency"]))
        return results[:limit]
