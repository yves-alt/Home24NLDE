# Cluster Excel rows by product category using TF-IDF + KMeans
# Groups kitchen, bathroom, textile, sofa, lighting, etc. before translation
import re
from dataclasses import dataclass, field

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import MiniBatchKMeans
from sklearn.preprocessing import normalize


CATEGORY_LABEL_MAP = {
    0: "kitchen",
    1: "bathroom",
    2: "bedroom",
    3: "living",
    4: "lighting",
    5: "storage",
    6: "outdoor",
    7: "textile",
    8: "dining",
    9: "general",
}

KEYWORD_OVERRIDE: dict[str, str] = {
    "küche": "kitchen", "herd": "kitchen", "spüle": "kitchen", "kochen": "kitchen",
    "backofen": "kitchen", "singleküche": "kitchen", "pantryküche": "kitchen",
    "bad": "bathroom", "dusch": "bathroom", "wanne": "bathroom", "sanitär": "bathroom",
    "waschbecken": "bathroom", "badezimmer": "bathroom", "matte": "bathroom",
    "bett": "bedroom", "schlaf": "bedroom", "matratze": "bedroom", "kissen": "bedroom",
    "sofa": "living", "couch": "living", "wohnlandschaft": "living", "sessel": "living",
    "lampe": "lighting", "leuchte": "lighting", "led": "lighting", "pendel": "lighting",
    "schrank": "storage", "regal": "storage", "kommode": "storage", "lowboard": "storage",
    "garten": "outdoor", "terrasse": "outdoor", "balkon": "outdoor",
    "teppich": "textile", "vorhang": "textile", "decke": "textile", "kissen": "textile",
    "esstisch": "dining", "esszimmer": "dining", "stuhl": "dining",
}

N_CLUSTERS = 10
MAX_FEATURES = 5000


@dataclass
class RowCluster:
    category: str
    label: int
    indices: list[int] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)


class MLRowClusterer:

    def __init__(self, n_clusters: int = N_CLUSTERS):
        self.n_clusters = n_clusters
        self._vectorizer: TfidfVectorizer | None = None
        self._kmeans: MiniBatchKMeans | None = None

    def cluster_rows(self, texts: list[str]) -> list[RowCluster]:
        if not texts:
            return []

        # Keyword override for short / clear-cut texts
        labels = [_keyword_category(t) for t in texts]
        needs_ml = [i for i, l in enumerate(labels) if l is None]

        if len(needs_ml) >= self.n_clusters:
            ml_texts = [texts[i] for i in needs_ml]
            ml_labels = self._ml_cluster(ml_texts)
            for cluster_idx, original_idx in enumerate(needs_ml):
                numeric_label = ml_labels[cluster_idx]
                labels[original_idx] = CATEGORY_LABEL_MAP.get(numeric_label % N_CLUSTERS, "general")

        clusters: dict[str, RowCluster] = {}
        for i, (text, label) in enumerate(zip(texts, labels)):
            cat = label or "general"
            if cat not in clusters:
                clusters[cat] = RowCluster(category=cat, label=list(CATEGORY_LABEL_MAP.values()).index(cat) if cat in CATEGORY_LABEL_MAP.values() else 9)
            clusters[cat].indices.append(i)
            clusters[cat].texts.append(text)

        return list(clusters.values())

    def cluster_to_batches(self, texts: list[str], batch_size: int = 50) -> list[list[tuple[int, str]]]:
        clusters = self.cluster_rows(texts)
        batches = []
        for cluster in clusters:
            for start in range(0, len(cluster.indices), batch_size):
                batch = list(zip(
                    cluster.indices[start:start + batch_size],
                    cluster.texts[start:start + batch_size],
                ))
                batches.append(batch)
        return batches

    def _ml_cluster(self, texts: list[str]) -> list[int]:
        if not self._vectorizer:
            self._vectorizer = TfidfVectorizer(
                analyzer="char_wb",
                ngram_range=(2, 3),
                max_features=MAX_FEATURES,
                sublinear_tf=True,
            )

        corpus = [_clean(t) for t in texts]
        X = self._vectorizer.fit_transform(corpus)
        X = normalize(X)

        k = min(self.n_clusters, len(texts))
        km = MiniBatchKMeans(n_clusters=k, random_state=42, n_init=3)
        km.fit(X)
        return km.labels_.tolist()

    def detect_category(self, text: str) -> str:
        cat = _keyword_category(text)
        return cat or "general"


def _keyword_category(text: str) -> str | None:
    t = text.lower()
    for kw, cat in KEYWORD_OVERRIDE.items():
        if kw in t:
            return cat
    return None


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


_instance: MLRowClusterer | None = None


def get_row_clusterer() -> MLRowClusterer:
    global _instance
    if _instance is None:
        _instance = MLRowClusterer()
    return _instance
