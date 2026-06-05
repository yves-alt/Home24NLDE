import re
from dataclasses import dataclass


@dataclass
class ContextSignal:
    category: str
    confidence: float
    signals: list[str]


CONTEXT_RULES: dict[str, dict] = {
    "kitchen": {
        "keywords": ["küche", "herd", "spüle", "kochen", "backofen", "kühlschrank", "mikrowelle"],
        "translations": {
            "kücheninsel": "kookeiland",
            "küchenzeile": "keukenblok",
            "singleküche": "mini keuken",
            "pantryküche": "pantry keuken",
            "einbauküche": "inbouwkeuken",
        },
    },
    "bathroom": {
        "keywords": ["bad", "dusche", "wanne", "waschbecken", "badezimmer", "sanitär"],
        "translations": {
            "duschmatte": "douchemat",
            "badewannenmatte": "badkuipmat",
            "handtuchhalter": "handdoekhouder",
            "seifenspender": "zeepdispenser",
        },
    },
    "living": {
        "keywords": ["wohnzimmer", "sofa", "couch", "wohnlandschaft", "sessel"],
        "translations": {
            "wohnlandschaft": "hoekbank",
            "ottomane": "ottomane",
            "hocker": "hocker",
            "chaiselongue": "chaise longue",
        },
    },
    "bedroom": {
        "keywords": ["schlafzimmer", "bett", "matratze", "kissen", "bettwäsche"],
        "translations": {
            "bettgestell": "bedframe",
            "kopfteil": "hoofdeinde",
            "lattenrost": "lattenbodem",
            "bettkasten": "opbergbed",
        },
    },
    "outdoor": {
        "keywords": ["garten", "terrasse", "outdoor", "balkon", "außen"],
        "translations": {
            "gartenbank": "tuinbank",
            "liegestuhl": "ligstoel",
            "sonnenschirm": "parasol",
        },
    },
    "lighting": {
        "keywords": ["lampe", "leuchte", "licht", "led", "pendel", "spot"],
        "translations": {
            "pendelleuchte": "hanglamp",
            "stehleuchte": "vloerlamp",
            "wandleuchte": "wandlamp",
            "tischleuchte": "tafellamp",
            "deckenleuchte": "plafondlamp",
            "einbauleuchte": "inbouwspot",
        },
    },
    "storage": {
        "keywords": ["schrank", "regal", "kommode", "schublade", "ablage"],
        "translations": {
            "kleiderschrank": "kledingkast",
            "sideboard": "dressoir",
            "lowboard": "tv-meubel",
            "highboard": "hoge kast",
            "vitrine": "vitrinekast",
        },
    },
}


class DutchContextEngine:

    def detect_context(self, row_data: dict, headers: list[str]) -> ContextSignal:
        all_text = " ".join(str(v).lower() for v in row_data.values() if v)
        scores: dict[str, float] = {}

        for cat, rules in CONTEXT_RULES.items():
            hits = [kw for kw in rules["keywords"] if kw in all_text]
            if hits:
                scores[cat] = len(hits) / len(rules["keywords"])

        if not scores:
            return ContextSignal("general", 0.0, [])

        best_cat = max(scores, key=scores.get)
        return ContextSignal(best_cat, scores[best_cat], list(scores.keys()))

    def get_context_translation(self, source: str, context: ContextSignal) -> str | None:
        key = source.lower().strip()

        if context.category in CONTEXT_RULES:
            trans = CONTEXT_RULES[context.category]["translations"]
            if key in trans:
                return trans[key]

        for cat, rules in CONTEXT_RULES.items():
            if key in rules["translations"]:
                return rules["translations"][key]

        return None

    def enrich_prompt_with_context(self, source: str, context: ContextSignal) -> str:
        if context.category == "general":
            return source

        category_nl = {
            "kitchen": "keuken",
            "bathroom": "badkamer",
            "living": "woonkamer",
            "bedroom": "slaapkamer",
            "outdoor": "buiten",
            "lighting": "verlichting",
            "storage": "opbergruimte",
        }.get(context.category, context.category)

        return f"[Context: {category_nl}] {source}"


_instance: DutchContextEngine | None = None


def get_context_engine() -> DutchContextEngine:
    global _instance
    if _instance is None:
        _instance = DutchContextEngine()
    return _instance
