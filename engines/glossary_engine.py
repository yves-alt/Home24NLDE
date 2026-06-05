import re
from dataclasses import dataclass
from database.database import get_connection


@dataclass
class GlossaryHit:
    source_term: str
    target_term: str
    category: str
    confidence: float


class DutchGlossaryManager:

    def lookup(self, term: str) -> GlossaryHit | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT source_term, target_term, category, confidence FROM glossary "
                "WHERE active=1 AND source_term=? ORDER BY confidence DESC LIMIT 1",
                (term.lower(),),
            ).fetchone()
        if row:
            return GlossaryHit(row["source_term"], row["target_term"], row["category"], row["confidence"])
        return None

    def apply_glossary(self, source: str, translation: str) -> tuple[str, int]:
        hits = 0
        with get_connection() as conn:
            terms = conn.execute(
                "SELECT source_term, target_term FROM glossary WHERE active=1 ORDER BY LENGTH(source_term) DESC"
            ).fetchall()

        for row in terms:
            pattern = re.compile(re.escape(row["source_term"]), re.IGNORECASE)
            if pattern.search(translation):
                translation = pattern.sub(row["target_term"], translation)
                hits += 1

        return translation, hits

    def add_term(self, source: str, target: str, category: str = "general", source_type: str = "MANUAL") -> bool:
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO glossary (source_term, target_term, category, source_type, active) VALUES (?,?,?,?,1)",
                    (source.lower(), target, category, source_type),
                )
            return True
        except Exception:
            return False

    def update_term(self, term_id: int, target: str, category: str) -> bool:
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE glossary SET target_term=?, category=? WHERE id=?",
                    (target, category, term_id),
                )
            return True
        except Exception:
            return False

    def toggle_term(self, term_id: int, active: bool) -> bool:
        try:
            with get_connection() as conn:
                conn.execute("UPDATE glossary SET active=? WHERE id=?", (1 if active else 0, term_id))
            return True
        except Exception:
            return False

    def delete_term(self, term_id: int) -> bool:
        try:
            with get_connection() as conn:
                conn.execute("DELETE FROM glossary WHERE id=?", (term_id,))
            return True
        except Exception:
            return False

    def search(self, query: str, category: str | None = None, limit: int = 100) -> list[dict]:
        sql = "SELECT * FROM glossary WHERE (source_term LIKE ? OR target_term LIKE ?)"
        params: list = [f"%{query}%", f"%{query}%"]
        if category and category != "all":
            sql += " AND category=?"
            params.append(category)
        sql += " ORDER BY frequency DESC LIMIT ?"
        params.append(limit)
        with get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_all(self, category: str | None = None, active_only: bool = False, limit: int = 500, offset: int = 0) -> list[dict]:
        sql = "SELECT * FROM glossary WHERE 1=1"
        params: list = []
        if active_only:
            sql += " AND active=1"
        if category and category != "all":
            sql += " AND category=?"
            params.append(category)
        sql += " ORDER BY frequency DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        with get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM glossary").fetchone()[0]
            active = conn.execute("SELECT COUNT(*) FROM glossary WHERE active=1").fetchone()[0]
            by_type = conn.execute(
                "SELECT source_type, COUNT(*) as cnt FROM glossary GROUP BY source_type"
            ).fetchall()
            by_cat = conn.execute(
                "SELECT category, COUNT(*) as cnt FROM glossary WHERE active=1 GROUP BY category ORDER BY cnt DESC LIMIT 10"
            ).fetchall()
        return {
            "total": total,
            "active": active,
            "by_type": {r["source_type"]: r["cnt"] for r in by_type},
            "by_category": {r["category"]: r["cnt"] for r in by_cat},
        }

    def export_to_excel(self, filepath: str):
        import pandas as pd
        rows = self.get_all(limit=100000)
        df = pd.DataFrame(rows)
        df.to_excel(filepath, index=False, sheet_name="Glossary")

    def get_categories(self) -> list[str]:
        with get_connection() as conn:
            rows = conn.execute("SELECT DISTINCT category FROM glossary ORDER BY category").fetchall()
        return [r["category"] for r in rows]


_instance: DutchGlossaryManager | None = None


def get_glossary_manager() -> DutchGlossaryManager:
    global _instance
    if _instance is None:
        _instance = DutchGlossaryManager()
    return _instance
