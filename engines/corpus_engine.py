import re
from database.database import get_connection


SEED_CORPUS: list[tuple[str, str, str, str]] = [
    # (category, product_type, source, text)
    # Kitchen
    ("kitchen", "singleküche", "home24.nl", "Mini keuken"),
    ("kitchen", "singleküche", "home24.nl", "Compacte keuken"),
    ("kitchen", "kücheninsel", "home24.nl", "Kookeiland"),
    ("kitchen", "kücheninsel", "home24.nl", "Keukeneiland"),
    ("kitchen", "einbauküche", "home24.nl", "Inbouwkeuken"),
    ("kitchen", "pantryküche", "home24.nl", "Pantrykeukentje"),
    ("kitchen", "general", "home24.nl", "Kastdeur met softclose"),
    ("kitchen", "general", "home24.nl", "Werkblad van keramiek"),
    ("kitchen", "general", "home24.nl", "Lade met volledige uittrek"),
    # Bathroom
    ("bathroom", "duschmatte", "home24.nl", "Douchemat met antislip"),
    ("bathroom", "duschmatte", "home24.nl", "Badmat voor de douche"),
    ("bathroom", "badewannenmatte", "home24.nl", "Badkuipmat met zuignappen"),
    ("bathroom", "badewannenmatte", "home24.nl", "Antislipmat voor het bad"),
    ("bathroom", "badset", "home24.nl", "Badkamerset compleet"),
    ("bathroom", "general", "home24.nl", "Badkamerkast met spiegel"),
    ("bathroom", "general", "home24.nl", "Wastafelmeubel eiken look"),
    ("bathroom", "general", "home24.nl", "Vrijstaand bad acryl"),
    # Sofa
    ("sofa", "sofa", "home24.nl", "3-zitsbank met chaise longue"),
    ("sofa", "sofa", "home24.nl", "Hoekbank met slaapfunctie"),
    ("sofa", "sofa", "home24.nl", "Stofbank in bouclé"),
    ("sofa", "sofa", "home24.nl", "Leren bank zwart"),
    ("sofa", "sofa", "home24.nl", "Relaxfauteuil met voetsteun"),
    ("sofa", "wohnlandschaft", "home24.nl", "Woonlandschap XXL"),
    # Bedroom
    ("bedroom", "bett", "home24.nl", "Gestoffeerd bed met opbergruimte"),
    ("bedroom", "bett", "home24.nl", "Massief houten bed eiken"),
    ("bedroom", "matratze", "home24.nl", "Pocketvering matras"),
    ("bedroom", "matratze", "home24.nl", "Koudschuim matras medium"),
    ("bedroom", "general", "home24.nl", "Nachtkastje met lade"),
    ("bedroom", "general", "home24.nl", "Kleedkamer met schuifdeuren"),
    # Textile
    ("textile", "teppich", "home24.nl", "Hoogpolig tapijt crème"),
    ("textile", "teppich", "home24.nl", "Laagpolig vloerkleed grijs"),
    ("textile", "vorhang", "home24.nl", "Verduisteringsgordijn antraciet"),
    ("textile", "vorhang", "home24.nl", "Linnen gordijn naturel"),
    ("textile", "general", "home24.nl", "Kussenhoes velvet mosterd"),
    ("textile", "general", "home24.nl", "Fleece plaid 150x200 cm"),
    # Outdoor
    ("outdoor", "general", "home24.nl", "Tuinstoel stapelbaar"),
    ("outdoor", "general", "home24.nl", "Parasolvoet graniet"),
    ("outdoor", "general", "home24.nl", "Balkonset 2-delig"),
    ("outdoor", "general", "home24.nl", "Loungebank wicker grijs"),
    ("outdoor", "general", "home24.nl", "Plantenbak verzinkt staal"),
    # Lighting
    ("lighting", "general", "home24.nl", "Hanglamp industrieel zwart"),
    ("lighting", "general", "home24.nl", "Vloerlamp met leesarm"),
    ("lighting", "general", "home24.nl", "LED plafondlamp dimbaar"),
    ("lighting", "general", "home24.nl", "Wandlamp up-down effect"),
    # Storage
    ("storage", "schrank", "home24.nl", "Kledingkast 3-deurs spiegel"),
    ("storage", "sideboard", "home24.nl", "Dressoir eiken 4 deuren"),
    ("storage", "kommode", "home24.nl", "Ladekast 5 lades"),
    ("storage", "lowboard", "home24.nl", "Tv-meubel met vakken"),
    ("storage", "general", "home24.nl", "Vitrinekast met verlichting"),
    # Dining
    ("dining", "esstisch", "home24.nl", "Eettafel uitschuifbaar"),
    ("dining", "stuhl", "home24.nl", "Eetkamerstoel gestoffeerd"),
    ("dining", "general", "home24.nl", "Barhocker verstelbaar"),
    # General materials / descriptions
    ("general", "general", "home24.nl", "Eikenhouten look"),
    ("general", "general", "home24.nl", "Betonlook oppervlak"),
    ("general", "general", "home24.nl", "Marmer look tafelblad"),
    ("general", "general", "home24.nl", "Metalen frame zwart"),
    ("general", "general", "home24.nl", "Roestvrij stalen poten"),
    ("general", "general", "home24.nl", "Massief eiken"),
    ("general", "general", "home24.nl", "Melamine coating wit"),
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def seed_corpus() -> int:
    inserted = 0
    with get_connection() as conn:
        for cat, ptype, src, text in SEED_CORPUS:
            norm = _normalize(text)
            try:
                existing = conn.execute(
                    "SELECT id FROM home24_nl_corpus WHERE normalized_text = ?",
                    (norm,),
                ).fetchone()
                if not existing:
                    conn.execute(
                        """INSERT INTO home24_nl_corpus
                           (category, product_type, source, text, normalized_text)
                           VALUES (?, ?, ?, ?, ?)""",
                        (cat, ptype, src, text, norm),
                    )
                    inserted += 1
            except Exception:
                pass
        conn.commit()
    return inserted


class Home24CorpusEngine:

    def lookup_exact(self, text: str, category: str | None = None) -> str | None:
        norm = _normalize(text)
        with get_connection() as conn:
            if category:
                row = conn.execute(
                    """SELECT text FROM home24_nl_corpus
                       WHERE normalized_text = ? AND category = ?
                       ORDER BY frequency DESC LIMIT 1""",
                    (norm, category),
                ).fetchone()
            else:
                row = conn.execute(
                    """SELECT text FROM home24_nl_corpus
                       WHERE normalized_text = ?
                       ORDER BY frequency DESC LIMIT 1""",
                    (norm,),
                ).fetchone()
        return row[0] if row else None

    def lookup_fuzzy(self, text: str, category: str | None = None, limit: int = 5) -> list[tuple[str, float]]:
        try:
            from rapidfuzz.fuzz import token_sort_ratio
        except ImportError:
            return []

        norm = _normalize(text)
        with get_connection() as conn:
            if category:
                rows = conn.execute(
                    "SELECT text, normalized_text FROM home24_nl_corpus WHERE category = ?",
                    (category,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT text, normalized_text FROM home24_nl_corpus"
                ).fetchall()

        scored = [
            (row[0], token_sort_ratio(norm, row[1]) / 100.0)
            for row in rows
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [(t, s) for t, s in scored[:limit] if s >= 0.70]

    def best_match(self, text: str, category: str | None = None) -> tuple[str, float] | None:
        exact = self.lookup_exact(text, category)
        if exact:
            return exact, 1.0
        fuzzy = self.lookup_fuzzy(text, category, limit=1)
        if fuzzy:
            return fuzzy[0]
        return None

    def increment_frequency(self, text: str):
        norm = _normalize(text)
        with get_connection() as conn:
            conn.execute(
                "UPDATE home24_nl_corpus SET frequency = frequency + 1 WHERE normalized_text = ?",
                (norm,),
            )
            conn.commit()


_instance: Home24CorpusEngine | None = None


def get_corpus_engine() -> Home24CorpusEngine:
    global _instance
    if _instance is None:
        _instance = Home24CorpusEngine()
    return _instance
