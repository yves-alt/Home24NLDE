import re
from dataclasses import dataclass


PRODUCT_TYPES = [
    "sofa", "kitchen", "bathroom", "bedroom", "textile",
    "outdoor", "lighting", "decoration", "storage", "dining", "office",
]

# Keyword → product type, ordered most-specific first
CLASSIFIER_RULES: list[tuple[str, str]] = [
    # Sofa / seating
    ("wohnlandschaft", "sofa"), ("sofa", "sofa"), ("couch", "sofa"),
    ("sessel", "sofa"), ("hocker", "sofa"), ("ottomane", "sofa"),
    ("chaiselongue", "sofa"), ("relaxsessel", "sofa"), ("schlafsofa", "sofa"),
    ("ecksofa", "sofa"), ("polstergarnitur", "sofa"),
    # Kitchen
    ("küche", "kitchen"), ("herd", "kitchen"), ("spüle", "kitchen"),
    ("backofen", "kitchen"), ("kühlschrank", "kitchen"), ("mikrowelle", "kitchen"),
    ("singleküche", "kitchen"), ("pantryküche", "kitchen"), ("einbauküche", "kitchen"),
    ("kücheninsel", "kitchen"), ("kochfeld", "kitchen"), ("dunstabzug", "kitchen"),
    ("geschirrspüler", "kitchen"), ("spülbecken", "kitchen"),
    # Bathroom
    ("bad", "bathroom"), ("dusch", "bathroom"), ("wanne", "bathroom"),
    ("waschbecken", "bathroom"), ("sanitär", "bathroom"), ("badezimmer", "bathroom"),
    ("handtuch", "bathroom"), ("seife", "bathroom"), ("badset", "bathroom"),
    ("badmöbel", "bathroom"), ("waschtisch", "bathroom"), ("spiegelschrank", "bathroom"),
    # Bedroom
    ("bett", "bedroom"), ("matratze", "bedroom"), ("kissen", "bedroom"),
    ("bettgestell", "bedroom"), ("kopfteil", "bedroom"), ("lattenrost", "bedroom"),
    ("bettkasten", "bedroom"), ("schlafzimmer", "bedroom"), ("bettwäsche", "bedroom"),
    # Textile
    ("teppich", "textile"), ("vorhang", "textile"), ("gardine", "textile"),
    ("bettwäsche", "textile"), ("decke", "textile"), ("kissen", "textile"),
    ("tischdecke", "textile"), ("stuhlkissen", "textile"), ("bügelbrett", "textile"),
    ("wäsche", "textile"),
    # Outdoor
    ("garten", "outdoor"), ("terrasse", "outdoor"), ("outdoor", "outdoor"),
    ("balkon", "outdoor"), ("außen", "outdoor"), ("gartenbank", "outdoor"),
    ("liegestuhl", "outdoor"), ("sonnenschirm", "outdoor"), ("pflanzenkübel", "outdoor"),
    # Lighting
    ("lampe", "lighting"), ("leuchte", "lighting"), ("led", "lighting"),
    ("pendel", "lighting"), ("spot", "lighting"), ("strahler", "lighting"),
    ("lichterkette", "lighting"), ("tischlampe", "lighting"), ("wandlampe", "lighting"),
    # Decoration
    ("deko", "decoration"), ("vase", "decoration"), ("bild", "decoration"),
    ("spiegel", "decoration"), ("kerze", "decoration"), ("uhr", "decoration"),
    ("blumentopf", "decoration"), ("skulptur", "decoration"), ("rahmen", "decoration"),
    # Storage
    ("schrank", "storage"), ("regal", "storage"), ("kommode", "storage"),
    ("lowboard", "storage"), ("sideboard", "storage"), ("vitrine", "storage"),
    ("highboard", "storage"), ("aufbewahrung", "storage"), ("kleiderschrank", "storage"),
    # Dining
    ("esstisch", "dining"), ("esszimmer", "dining"), ("essstuhl", "dining"),
    ("esstischstuhl", "dining"), ("bank", "dining"), ("barhocker", "dining"),
    ("stuhl", "dining"), ("tischset", "dining"),
    # Office
    ("schreibtisch", "office"), ("büro", "office"), ("arbeitszimmer", "office"),
    ("bürostuhl", "office"), ("aktenschrank", "office"), ("regal", "office"),
    ("computertisch", "office"),
]


@dataclass
class ClassificationResult:
    product_type: str
    confidence: float
    matched_keywords: list[str]


class ProductTypeClassifier:

    def classify(self, *text_fields: str) -> ClassificationResult:
        combined = " ".join(str(f) for f in text_fields if f).lower()
        scores: dict[str, float] = {}
        matched: dict[str, list[str]] = {}

        for keyword, ptype in CLASSIFIER_RULES:
            if keyword in combined:
                scores[ptype] = scores.get(ptype, 0) + _keyword_weight(keyword)
                matched.setdefault(ptype, []).append(keyword)

        if not scores:
            return ClassificationResult("general", 0.40, [])

        best = max(scores, key=scores.get)
        total = sum(scores.values())
        confidence = min(scores[best] / max(total, 1), 1.0)
        confidence = 0.50 + confidence * 0.50  # scale to 50–100%

        return ClassificationResult(best, round(confidence, 3), matched.get(best, []))

    def classify_row(self, row: dict, source_col: str | int | None = None) -> ClassificationResult:
        fields = list(row.values())
        if source_col is not None:
            if isinstance(source_col, int) and source_col < len(fields):
                primary = str(fields[source_col])
            elif isinstance(source_col, str):
                primary = str(row.get(source_col, ""))
            else:
                primary = ""
            return self.classify(primary, *[str(v) for v in fields])
        return self.classify(*[str(v) for v in fields])


def _keyword_weight(keyword: str) -> float:
    # Longer, more specific keywords get higher weight
    return 1.0 + len(keyword) * 0.05


_instance: ProductTypeClassifier | None = None


def get_classifier() -> ProductTypeClassifier:
    global _instance
    if _instance is None:
        _instance = ProductTypeClassifier()
    return _instance
