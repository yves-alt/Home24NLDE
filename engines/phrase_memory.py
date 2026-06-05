import re
from database.database import get_connection


SEED_PHRASES: list[tuple[str, str, str, float]] = [
    # (source_phrase, target_phrase, category, confidence)
    ("Pflegeleicht und wetterfest", "onderhoudsvriendelijk en weerbestendig", "outdoor", 0.97),
    ("Pflegeleicht und strapazierfähig", "onderhoudsvriendelijk en slijtvast", "general", 0.97),
    ("Einfache Montage", "eenvoudige montage", "general", 0.97),
    ("Inklusive Montagematerial", "inclusief bevestigingsmateriaal", "general", 0.97),
    ("Inkl. Montageanleitung", "incl. montagehandleiding", "general", 0.97),
    ("Nicht im Lieferumfang enthalten", "niet inbegrepen", "general", 0.97),
    ("Im Lieferumfang enthalten", "inbegrepen in de levering", "general", 0.97),
    ("Maße (B x H x T)", "afmetingen (b x h x d)", "general", 0.97),
    ("Maße (B x T x H)", "afmetingen (b x d x h)", "general", 0.97),
    ("Breite x Tiefe x Höhe", "breedte x diepte x hoogte", "general", 0.97),
    ("aus massivem Holz", "van massief hout", "material", 0.97),
    ("aus Massivholz", "van massief hout", "material", 0.97),
    ("aus hochwertigem Material", "van hoogwaardig materiaal", "material", 0.97),
    ("aus robustem Material", "van robuust materiaal", "material", 0.97),
    ("mit Softclose-Funktion", "met soft-close functie", "general", 0.97),
    ("mit Selbstschlussdämpfer", "met zelfsluitende demper", "general", 0.97),
    ("mit Push-to-open-Funktion", "met push-to-open functie", "general", 0.97),
    ("mit Schubladenführung", "met ladegeleider", "general", 0.97),
    ("mit Vollauszug", "met volledig uittrekbaar systeem", "general", 0.97),
    ("mit Anti-Rutsch-Beschichtung", "met antislipcoating", "bathroom", 0.97),
    ("wasserabweisend und pflegeleicht", "waterafstotend en makkelijk schoon te maken", "bathroom", 0.97),
    ("geprüfte Sicherheit", "gecontroleerde veiligheid", "general", 0.97),
    ("TÜV-geprüft", "TÜV-gecertificeerd", "general", 0.97),
    ("GS-geprüft", "GS-gecertificeerd", "general", 0.97),
    ("FSC-zertifiziert", "FSC-gecertificeerd", "material", 0.97),
    ("in verschiedenen Farben erhältlich", "verkrijgbaar in verschillende kleuren", "general", 0.97),
    ("in verschiedenen Größen erhältlich", "verkrijgbaar in verschillende maten", "general", 0.97),
    ("nach Maß gefertigt", "op maat gemaakt", "general", 0.97),
    ("Handgefertigt in Europa", "handgemaakt in Europa", "general", 0.97),
    ("Nachhaltig produziert", "duurzaam geproduceerd", "general", 0.97),
    ("umweltfreundlich produziert", "milieuvriendelijk geproduceerd", "general", 0.97),
    ("mit Lederoptik", "met lederimitatie", "sofa", 0.97),
    ("im Landhausstil", "in landelijke stijl", "general", 0.97),
    ("im Industriestil", "in industriële stijl", "general", 0.97),
    ("im skandinavischen Stil", "in Scandinavische stijl", "general", 0.97),
    ("modernes Design", "modern design", "general", 0.97),
    ("zeitloses Design", "tijdloos design", "general", 0.97),
    ("elegantes Design", "elegant design", "general", 0.97),
    ("platzsparend", "ruimtebesparend", "general", 0.97),
    ("multifunktional", "multifunctioneel", "general", 0.97),
    ("Variante A", "Variant A", "general", 0.97),
    ("Variante B", "Variant B", "general", 0.97),
    ("Variante C", "Variant C", "general", 0.97),
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def seed_phrase_memory() -> int:
    inserted = 0
    with get_connection() as conn:
        for src, tgt, cat, conf in SEED_PHRASES:
            norm = _normalize(src)
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO phrase_memory
                       (source_phrase, target_phrase, normalized_src, category, confidence)
                       VALUES (?, ?, ?, ?, ?)""",
                    (src, tgt, norm, cat, conf),
                )
                if conn.execute("SELECT changes()").fetchone()[0]:
                    inserted += 1
            except Exception:
                pass
        conn.commit()
    return inserted


class PhraseMemory:

    def lookup(self, text: str, category: str = "general") -> str | None:
        norm = _normalize(text)
        with get_connection() as conn:
            # Exact normalized match
            row = conn.execute(
                """SELECT target_phrase FROM phrase_memory
                   WHERE normalized_src = ? AND active = 1
                   ORDER BY (category = ?) DESC, frequency DESC
                   LIMIT 1""",
                (norm, category),
            ).fetchone()
            if row:
                return row[0]

            # Substring match: phrase is contained in text
            rows = conn.execute(
                """SELECT source_phrase, target_phrase FROM phrase_memory
                   WHERE active = 1
                   ORDER BY length(source_phrase) DESC""",
            ).fetchall()
            for src, tgt in rows:
                if _normalize(src) in norm:
                    return tgt

        return None

    def apply(self, text: str, category: str = "general") -> tuple[str, bool]:
        norm = _normalize(text)
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT source_phrase, target_phrase FROM phrase_memory
                   WHERE active = 1
                   ORDER BY length(source_phrase) DESC""",
            ).fetchall()

        result = text
        changed = False
        for src, tgt in rows:
            pattern = re.compile(re.escape(src), re.IGNORECASE)
            new_result, n = pattern.subn(tgt, result)
            if n:
                result = new_result
                changed = True

        return result, changed

    def increment_frequency(self, source_phrase: str):
        norm = _normalize(source_phrase)
        with get_connection() as conn:
            conn.execute(
                "UPDATE phrase_memory SET frequency = frequency + 1 WHERE normalized_src = ?",
                (norm,),
            )
            conn.commit()


_instance: PhraseMemory | None = None


def get_phrase_memory() -> PhraseMemory:
    global _instance
    if _instance is None:
        _instance = PhraseMemory()
    return _instance
