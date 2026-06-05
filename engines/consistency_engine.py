import re
from collections import defaultdict
from dataclasses import dataclass, field
from database.database import get_connection


@dataclass
class ConsistencyIssue:
    source_term: str
    used_translation: str
    expected_translation: str
    row_idx: int


class DutchWorkbookConsistencyEngine:
    # Enforces: same German term → always same Dutch term within a workbook

    def __init__(self):
        self._locked: dict[str, str] = {}
        self._seen: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._issues: list[ConsistencyIssue] = []

    def reset(self):
        self._locked.clear()
        self._seen.clear()
        self._issues.clear()

    def register(self, source: str, translation: str, row_idx: int = 0) -> str:
        key = _normalize_key(source)
        if not key:
            return translation

        if key in self._locked:
            locked = self._locked[key]
            if locked != translation:
                self._issues.append(ConsistencyIssue(source, translation, locked, row_idx))
            return locked

        self._seen[key][translation] += 1
        return translation

    def lock(self, source: str, translation: str):
        key = _normalize_key(source)
        self._locked[key] = translation

    def lock_batch_from_glossary(self):
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT source_term, target_term FROM glossary WHERE active=1 AND confidence >= 0.8"
            ).fetchall()
        for row in rows:
            self._locked[_normalize_key(row["source_term"])] = row["target_term"]

    def resolve_workbook(self, translations: list[tuple[str, str]]) -> list[str]:
        # Pick the most frequent translation per source term, then apply consistently
        freq: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for source, translation in translations:
            key = _normalize_key(source)
            if key:
                freq[key][translation] += 1

        chosen: dict[str, str] = {}
        for key, counts in freq.items():
            if key in self._locked:
                chosen[key] = self._locked[key]
            else:
                chosen[key] = max(counts, key=counts.get)

        resolved = []
        for source, translation in translations:
            key = _normalize_key(source)
            if key and key in chosen:
                resolved.append(chosen[key])
            else:
                resolved.append(translation)

        return resolved

    def get_issues(self) -> list[ConsistencyIssue]:
        return self._issues

    def get_locked_count(self) -> int:
        return len(self._locked)

    def log_to_db(self, filename: str):
        for key, translation in self._locked.items():
            alternatives = list(self._seen.get(key, {}).keys())
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO consistency_log (filename, source_term, chosen_target, alternatives) VALUES (?,?,?,?)",
                    (filename, key, translation, ", ".join(alternatives)),
                )


def _normalize_key(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.lower().strip())


_instance: DutchWorkbookConsistencyEngine | None = None


def get_consistency_engine() -> DutchWorkbookConsistencyEngine:
    global _instance
    if _instance is None:
        _instance = DutchWorkbookConsistencyEngine()
    return _instance
