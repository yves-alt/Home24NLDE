# TF-IDF semantic similarity matcher against the Translation Memory
# No GPU required — fits in RAM for 40k+ entries
import re
import unicodedata
from dataclasses import dataclass

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from database.database import get_connection


@dataclass
class SemanticMatch:
    source: str
    target: str
    score: float
    index: int


class TFIDFSemanticMatcher:

    def __init__(self, min_score: float = 0.60):
        self.min_score = min_score
        self._vectorizer: TfidfVectorizer | None = None
        self._matrix = None
        self._sources: list[str] = []
        self._targets: list[str] = []
        self._loaded = False

    def build_index(self, progress_callback=None):
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT source_segment, target_segment FROM translation_memory ORDER BY frequency DESC"
            ).fetchall()

        self._sources = [r["source_segment"] for r in rows]
        self._targets = [r["target_segment"] for r in rows]

        corpus = [_preprocess(s) for s in self._sources]

        self._vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 4),
            min_df=1,
            max_features=50000,
            sublinear_tf=True,
        )
        self._matrix = self._vectorizer.fit_transform(corpus)
        self._loaded = True

        if progress_callback:
            progress_callback(1.0)

    def match(self, query: str, top_k: int = 3) -> list[SemanticMatch]:
        if not self._loaded:
            self.build_index()

        q = _preprocess(query)
        q_vec = self._vectorizer.transform([q])
        scores = cosine_similarity(q_vec, self._matrix).flatten()

        top_indices = scores.argsort()[::-1][:top_k]
        results = []
        for idx in top_indices:
            s = float(scores[idx])
            if s >= self.min_score:
                results.append(SemanticMatch(
                    source=self._sources[idx],
                    target=self._targets[idx],
                    score=s,
                    index=int(idx),
                ))
        return results

    def best_match(self, query: str) -> SemanticMatch | None:
        results = self.match(query, top_k=1)
        return results[0] if results else None

    def reload(self):
        self._loaded = False
        self._vectorizer = None
        self._matrix = None
        self._sources = []
        self._targets = []
        self.build_index()

    @property
    def is_ready(self) -> bool:
        return self._loaded


def _preprocess(text: str) -> str:
    text = text.lower().strip()
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s+", " ", text)
    return text


_instance: TFIDFSemanticMatcher | None = None


def get_semantic_matcher(min_score: float = 0.60) -> TFIDFSemanticMatcher:
    global _instance
    if _instance is None:
        _instance = TFIDFSemanticMatcher(min_score=min_score)
    return _instance
