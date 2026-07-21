"""File-level consistency harmonization (PART 1 §18, Pass 6).

Level 1: the same German source in the same column profile should produce the
same Dutch translation throughout a file. Glossary/TM/terminology already make
this the common case, but human edits, GPT variance, or multiple self-correct
paths can still leave the same source with two different targets in one file.
This pass detects that and harmonizes to the majority (confidence-weighted)
choice, logging every rewrite to `consistency_log`.

Level 3 (product-family consistency) is deliberately not attempted — it needs
product-family metadata the workbook doesn't reliably expose.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from database.database import get_connection

# Higher-confidence origins win ties when harmonizing.
_ORIGIN_RANK = {
    "HUMAN": 6, "GLOSSARY": 5, "TM_EXACT": 4, "TM_ADAPTED": 3,
    "TERMINOLOGY": 2, "GPT": 1, "EMPTY": 0,
}


@dataclass
class ConsistencyRewrite:
    source: str
    column: str
    chosen_target: str
    alternatives: list = field(default_factory=list)
    cells_changed: int = 0


@dataclass
class ConsistencyReport:
    rewrites: list = field(default_factory=list)

    @property
    def cells_harmonized(self) -> int:
        return sum(r.cells_changed for r in self.rewrites)


def _normalize(text: str) -> str:
    return " ".join((text or "").split()).lower()


def harmonize(cells, filename: str = "") -> ConsistencyReport:
    """Rewrite cells in-place so identical (source, column) pairs converge on
    one target within this file. Returns a report of what changed."""
    groups: dict[tuple, list] = defaultdict(list)
    for cell in cells:
        if not (cell.target or "").strip() or not (cell.source or "").strip():
            continue
        groups[(_normalize(cell.source), cell.column)].append(cell)

    report = ConsistencyReport()
    log_rows = []
    now = datetime.now().isoformat()

    for (_norm_src, column), group in groups.items():
        targets = Counter(c.target for c in group)
        if len(targets) <= 1:
            continue  # already consistent

        # Choose the target with the most occurrences; ties broken by the
        # highest-confidence origin among cells holding that target.
        def _score(target: str) -> tuple:
            best_rank = max(_ORIGIN_RANK.get(c.origin, 0) for c in group if c.target == target)
            return (targets[target], best_rank)

        chosen = max(targets, key=_score)
        alternatives = [t for t in targets if t != chosen]

        changed = 0
        for c in group:
            if c.target != chosen:
                c.target = chosen
                c.warnings = list(c.warnings) + ["harmonized to the file's majority translation"]
                changed += 1

        if changed:
            report.rewrites.append(ConsistencyRewrite(
                source=group[0].source, column=column, chosen_target=chosen,
                alternatives=alternatives, cells_changed=changed,
            ))
            log_rows.append((filename, group[0].source, chosen, "; ".join(alternatives), now))

    if log_rows:
        try:
            with get_connection() as conn:
                conn.executemany(
                    "INSERT INTO consistency_log (filename, source_term, chosen_target, alternatives, logged_at) "
                    "VALUES (?,?,?,?,?)",
                    log_rows,
                )
        except Exception:
            pass

    return report
