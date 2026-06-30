"""DutchLocalizationEngine — central orchestrator (PART 2 & 7).

Deterministic-first, self-correcting DE→NL pipeline. Per segment:

  glossary/human review → adaptive TM (exact/adapted) → terminology →
  GPT (only if German still remains) → restore models → abbreviations →
  terminology enforce → (name engine for the name column)

Then a multi-pass self-correction loop fixes only the cells that fail the
quality gate, and the gate decides whether export is allowed.

GPT is never the primary translator and never silently falls back to German:
when a cell needs GPT and GPT is unavailable or fails, the cell keeps its best
deterministic form and is flagged so the quality gate blocks export.
"""

from engines.nl.terminology import get_terminology
from engines.nl.model_protector import get_model_protector
from engines.nl.adaptive_tm import get_adaptive_tm, TMKind, normalize
from engines.nl.abbreviations import get_abbreviation_resolver
from engines.nl import segmentation
from engines.nl.product_name_engine import get_product_name_engine
from engines.nl.naturalness_refiner import get_naturalness_refiner
from engines.nl.residue_gate import get_residue_gate
from engines.nl.info_preservation import get_info_validator
from engines.nl.quality_gate import get_quality_gate
from engines.nl.gpt_client import get_gpt_client
from engines.nl.types import CellResult
from database.database import get_connection


# Per-column guidance handed to GPT.
COLUMN_RULES: dict[str, str] = {
    "name": "Product name. Max 40 chars, no brackets, no commas. Format: product "
            "type + model name. End on a complete noun.",
    "materialDetail": "Concise material wording, lowercase. 'MDF' stays exactly 'MDF'.",
    "colorDetail": "Color names lowercase. Combinations use a slash without spaces "
                   "(zwart/wit).",
    "deliveryScope": "Complete delivery info, natural Dutch. Preserve every <br>.",
    "otherMeasurements": "Translate dimension labels only; keep all numbers and units. "
                         "B x H x T → B x H x D.",
    "qualityDetail": "Natural Dutch product copy, professional tone.",
    "variantName": "Concise, lowercase where appropriate.",
    "textileComposition": "Textile composition, lowercase material names.",
    "textileCompositionCover1": "Textile composition, lowercase. Translate percentages "
                                "and material names.",
    "warningsAndSafetyInformation": "Translate safety/warning text fully and naturally.",
}

# Origins that count as deterministic (no GPT spend).
DETERMINISTIC_ORIGINS = {"HUMAN", "GLOSSARY", "TM_EXACT", "TM_ADAPTED", "TERMINOLOGY", "EMPTY"}

_MAX_CORRECTION_PASSES = 3


class DutchLocalizationEngine:
    def __init__(self, use_gpt: bool = True, use_refiner: bool = False):
        self._term = get_terminology()
        self._protector = get_model_protector()
        self._tm = get_adaptive_tm()
        self._abbrev = get_abbreviation_resolver()
        self._name = get_product_name_engine()
        self._refiner = get_naturalness_refiner()
        self._residue = get_residue_gate()
        self._info = get_info_validator()
        self._gate = get_quality_gate()
        self._gpt = get_gpt_client()
        self._use_gpt = use_gpt
        self._use_refiner = use_refiner
        self._glossary_cache: dict[str, tuple[str, str]] = {}

    @property
    def gpt_active(self) -> bool:
        return self._use_gpt and self._gpt.available

    # ── glossary / human review (exact, indexed) ─────────────────────────

    def _glossary_lookup(self, source: str) -> tuple[str, str] | None:
        """Return (target, origin) for an exact human-review / high-conf glossary hit."""
        key = source.lower().strip()
        if key in self._glossary_cache:
            hit = self._glossary_cache[key]
            return hit if hit[0] else None
        target_origin = ("", "")
        try:
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT target_term, source_type, confidence FROM glossary "
                    "WHERE active=1 AND source_term=? "
                    "ORDER BY (source_type='HUMAN_REVIEW') DESC, confidence DESC LIMIT 1",
                    (key,),
                ).fetchone()
            if row and row["target_term"] and normalize(row["target_term"]) != key:
                is_human = row["source_type"] == "HUMAN_REVIEW"
                if is_human or (row["confidence"] or 0) >= 0.95:
                    target_origin = (row["target_term"], "HUMAN" if is_human else "GLOSSARY")
        except Exception:
            pass
        self._glossary_cache[key] = target_origin
        return target_origin if target_origin[0] else None

    def clear_glossary_cache(self):
        self._glossary_cache.clear()

    # ── segment translation ──────────────────────────────────────────────

    def _translate_segment(self, text: str, column: str) -> tuple[str, str, bool]:
        """Translate one segment. Returns (target, origin, gpt_failed)."""
        if not text or not text.strip():
            return text, "EMPTY", False

        # 1. Human review / glossary exact.
        hit = self._glossary_lookup(text)
        if hit:
            return hit[0], hit[1], False

        # 2. Spec phrase patterns (decor combos, compounds) are authoritative —
        #    they win over generic TM entries. If a phrase matched and the full
        #    terminology pass resolves cleanly, that is the canonical form.
        _, phrase_hits = self._term.apply_phrases(text)
        if phrase_hits:
            term_text, _ = self._term.apply(text)
            if self._residue.is_clean(term_text):
                return term_text, "TERMINOLOGY", False

        # 3. Adaptive TM (exact or model-preserving adaptation).
        tm = self._tm.lookup(text)
        if tm.kind in (TMKind.EXACT, TMKind.ADAPTED) and tm.target:
            return tm.target, tm.kind.value, False

        # 4. Deterministic terminology pass.
        term_text, _ = self._term.apply(text)
        if self._residue.is_clean(term_text):
            return term_text, "TERMINOLOGY", False

        # 4. German remains → controlled GPT (models masked).
        if self.gpt_active:
            prot = self._protector.protect(text)
            res = self._gpt.translate(prot.text, column, COLUMN_RULES.get(column, ""))
            if res.ok and res.text:
                restored = self._protector.restore(res.text, prot.mapping)
                enforced, _ = self._term.apply(restored)
                if self._residue.is_clean(enforced):
                    return enforced, "GPT", False
                # GPT left residue → fall through to flagged terminology result.
                return enforced, "GPT", True
            # GPT unavailable/failed → keep best deterministic effort, flag it.
            return term_text, "TERMINOLOGY", True

        # No GPT and residue remains → flag for the quality gate.
        return term_text, "TERMINOLOGY", True

    # ── cell translation ─────────────────────────────────────────────────

    def translate_cell(self, row: int, column: str, source) -> CellResult:
        text = "" if source is None else str(source).strip()
        models = self._protector.protect(text).model_names if text else []

        if not text:
            return CellResult(row, column, text, "", "EMPTY", 1.0, "EMPTY", models)

        # Translate each <br>-delimited segment independently, preserving seps.
        parts = segmentation.split(text)
        origins: list[str] = []
        gpt_failed = False
        for p in parts:
            if p.kind == "sep":
                continue
            tgt, origin, failed = self._translate_segment(p.text, column)
            p.text = tgt
            origins.append(origin)
            gpt_failed = gpt_failed or failed
        target = segmentation.join(parts)

        # Post: abbreviations (expand + flag) and terminology enforcement.
        abbr = self._abbrev.resolve(target)
        target = abbr.text
        target, _ = self._term.apply(target)
        warnings = list(abbr.warnings)

        # Name column rules.
        if column == "name":
            name_res = self._name.optimize(target)
            target = name_res.name
            warnings.extend(name_res.warnings)

        # Optional GPT naturalness refinement (off by default; never reduces correctness).
        origin = self._summarize_origin(origins)
        if self._use_refiner and origin == "GPT":
            refined, changed = self._refiner.refine(target, text, models)
            if changed:
                target = refined

        label, score = self._confidence(origin, gpt_failed)
        return CellResult(
            row=row, column=column, source=text, target=target,
            origin=origin, confidence=score, confidence_label=label,
            model_names=models, warnings=warnings, gpt_failed=gpt_failed,
        )

    def _summarize_origin(self, origins: list[str]) -> str:
        present = [o for o in origins if o != "EMPTY"]
        if not present:
            return "EMPTY"
        if "GPT" in present:
            return "GPT"
        # Most "interesting" deterministic origin wins for display.
        for pref in ("HUMAN", "GLOSSARY", "TM_ADAPTED", "TM_EXACT", "TERMINOLOGY"):
            if pref in present:
                return pref
        return present[0]

    def _confidence(self, origin: str, gpt_failed: bool) -> tuple[str, float]:
        if gpt_failed:
            return "NEEDS_REVIEW", 0.3
        return {
            "HUMAN": ("HUMAN_REVIEW", 1.0),
            "GLOSSARY": ("GLOSSARY", 0.97),
            "TM_EXACT": ("EXACT_TM", 1.0),
            "TM_ADAPTED": ("ADAPTED_TM", 0.9),
            "TERMINOLOGY": ("TERMINOLOGY", 0.92),
            "GPT": ("AI", 0.8),
            "EMPTY": ("EMPTY", 1.0),
        }.get(origin, ("OK", 0.85))

    # ── multi-pass self-correction (PART 7) ──────────────────────────────

    def self_correct(self, cells: list[CellResult]) -> list[CellResult]:
        """Iterative gate→fix loop. Only failing cells are retried each pass.

        Pass 1–3: residue + terminology + info-preservation fix cycles.
        Pass 4 (optional): Dutch naturalness refinement for GPT-translated cells.
        """
        for _ in range(_MAX_CORRECTION_PASSES):
            report = self._gate.evaluate(cells)
            if report.passed:
                break
            failing = {(i.row, i.column) for i in report.issues}
            changed = False
            for cell in cells:
                if (cell.row, cell.column) in failing:
                    if self._fix_cell(cell):
                        changed = True
            if not changed:
                break

        # Naturalness pass (off by default — GPT cells only, safe fallback).
        if self._use_refiner and self._refiner.available:
            for cell in cells:
                if cell.origin == "GPT" and not cell.gpt_failed and cell.target:
                    refined, changed = self._refiner.refine(
                        cell.target, cell.source, cell.model_names
                    )
                    if changed:
                        cell.target = refined

        return cells

    def _fix_cell(self, cell: CellResult) -> bool:
        """Fix a single failing cell in-place. Returns True if anything changed."""
        before = cell.target

        # Step 1: Deterministic residue autofix.
        res_report = self._residue.autofix(cell.target)
        if res_report.was_fixed:
            cell.target = res_report.text

        # Step 2: Terminology re-enforcement (catches residue the autofix missed).
        enforced, hits = self._term.apply(cell.target)
        if hits:
            cell.target = enforced

        # Step 3: Re-apply abbreviations now so the info-preservation check sees
        # the expanded forms (e.g. MW → magnetron, 3er-Set → set van 3).
        cell.target = self._abbrev.resolve(cell.target).text

        # Step 4: If residue still present OR information was lost → GPT retry.
        still_dirty = bool(self._residue.scan(cell.target))
        info_lost = not self._info.validate(cell.source, cell.target, cell.model_names).ok
        if (still_dirty or info_lost) and self.gpt_active:
            prot = self._protector.protect(cell.source)
            gpt_res = self._gpt.translate(
                prot.text, cell.column, COLUMN_RULES.get(cell.column, "")
            )
            if gpt_res.ok and gpt_res.text:
                restored = self._protector.restore(gpt_res.text, prot.mapping)
                enforced2, _ = self._term.apply(restored)
                enforced2 = self._abbrev.resolve(enforced2).text
                if self._residue.is_clean(enforced2):
                    cell.target = enforced2
                    cell.gpt_failed = False

        # Step 5: Name column rules.
        if cell.column == "name":
            name_res = self._name.optimize(cell.target)
            cell.target = name_res.name
            if name_res.warnings and name_res.warnings not in cell.warnings:
                cell.warnings = list(set(cell.warnings) | set(name_res.warnings))

        return cell.target != before

    # ── reporting ────────────────────────────────────────────────────────

    def quality_report(self, cells: list[CellResult], coverage_errors=()):
        return self._gate.evaluate(cells, coverage_errors=coverage_errors)


_instance: DutchLocalizationEngine | None = None


def get_localization_engine(use_gpt: bool = True, use_refiner: bool = False) -> DutchLocalizationEngine:
    global _instance
    if _instance is None:
        _instance = DutchLocalizationEngine(use_gpt=use_gpt, use_refiner=use_refiner)
    return _instance
