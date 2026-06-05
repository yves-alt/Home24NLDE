import re
from dataclasses import dataclass, field


CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "kitchen": ["küche", "herd", "spüle", "kochen", "backofen", "kühlschrank", "mikrowelle",
                "keuken", "pantrykeuken", "einbauküche", "singleküche"],
    "bathroom": ["bad", "dusche", "wanne", "waschbecken", "badezimmer", "sanitär",
                 "badkamer", "douche", "badkuip"],
    "bedroom": ["bett", "schlaf", "matratze", "kissen", "bettwäsche", "bettgestell",
                "slaap", "matras"],
    "living": ["sofa", "couch", "wohnlandschaft", "sessel", "wohnzimmer",
               "bank", "hoekbank", "fauteuil"],
    "outdoor": ["garten", "terrasse", "outdoor", "balkon", "außen",
                "tuin", "terras", "buiten"],
    "lighting": ["lampe", "leuchte", "licht", "led", "pendel", "spot",
                 "lamp", "hanglamp", "vloerlamp"],
    "storage": ["schrank", "regal", "kommode", "schublade", "lowboard",
                "kast", "rek", "dressoir"],
    "textile": ["kissen", "decke", "vorhang", "teppich", "bettwäsche",
                "kussen", "deken", "gordijn", "tapijt"],
    "dining": ["esstisch", "esszimmer", "stuhl", "bank", "esszimmerstuhl",
               "eetkamer", "eettafel", "eetkamerstoel"],
}

MAX_CLUSTER_SIZE = 50


@dataclass
class Cluster:
    category: str
    rows: list[dict] = field(default_factory=list)
    indices: list[int] = field(default_factory=list)


class SemanticRowClusterer:

    def cluster(self, rows: list[dict], source_col: str | int) -> list[Cluster]:
        clusters: dict[str, Cluster] = {}

        for i, row in enumerate(rows):
            source = self._get_source(row, source_col)
            if not source:
                category = "general"
            else:
                category = self._detect_category(source)

            if category not in clusters:
                clusters[category] = Cluster(category=category)

            clusters[category].rows.append(row)
            clusters[category].indices.append(i)

        return list(clusters.values())

    def cluster_to_batches(self, rows: list[dict], source_col: str | int, batch_size: int = MAX_CLUSTER_SIZE) -> list[list[tuple[int, dict]]]:
        clusters = self.cluster(rows, source_col)
        batches = []

        for cluster in clusters:
            for start in range(0, len(cluster.rows), batch_size):
                batch_rows = cluster.rows[start:start + batch_size]
                batch_indices = cluster.indices[start:start + batch_size]
                batches.append(list(zip(batch_indices, batch_rows)))

        return batches

    def _get_source(self, row: dict, source_col: str | int) -> str:
        if isinstance(source_col, int):
            values = list(row.values())
            return str(values[source_col]) if source_col < len(values) else ""
        return str(row.get(source_col, ""))

    def _detect_category(self, text: str) -> str:
        text_lower = text.lower()
        scores: dict[str, int] = {}

        for cat, keywords in CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[cat] = score

        if not scores:
            return "general"

        return max(scores, key=scores.get)


_instance: SemanticRowClusterer | None = None


def get_clusterer() -> SemanticRowClusterer:
    global _instance
    if _instance is None:
        _instance = SemanticRowClusterer()
    return _instance
