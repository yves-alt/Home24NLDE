# Translation orchestrator — 5-step pipeline:
# 1. Exact TM match
# 2. RapidFuzz fuzzy match
# 3. TF-IDF semantic match
# 4. Glossary match
# 5. GPT fallback (only when steps 1–4 produce nothing)
import os
import time
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum

from dotenv import load_dotenv

load_dotenv()

from engines.tm_matcher import get_matcher, MatchType
from engines.fuzzy_matcher import FuzzyMatcher
from engines.semantic_matcher import get_semantic_matcher
from engines.glossary_engine import get_glossary_manager
from engines.consistency_engine import get_consistency_engine
from engines.context_engine import get_context_engine
from engines.naturalness_rewriter import get_rewriter
from engines.residue_detector import get_residue_detector
from engines.qa_engine import get_qa_engine
from engines.name_optimizer import get_name_optimizer
from engines.confidence_scorer import score_translation, ConfidenceLabel
from database.database import get_connection


class TranslationSource(str, Enum):
    TM_EXACT = "TM_EXACT"
    TM_FUZZY = "TM_FUZZY"
    TM_PATTERN = "TM_PATTERN"
    TFIDF = "TFIDF"
    GLOSSARY = "GLOSSARY"
    CONTEXT = "CONTEXT"
    GPT = "GPT"
    EMPTY = "EMPTY"


@dataclass
class TranslationResult:
    source: str
    target: str
    source_type: TranslationSource
    tm_score: float = 0.0
    qa_issues: list = field(default_factory=list)
    glossary_hits: int = 0
    was_rewritten: bool = False
    was_optimized: bool = False
    tokens_used: int = 0
    confidence_label: str = "UNKNOWN"
    confidence_score: float = 0.0
    needs_review: bool = False

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "source_type": self.source_type.value,
            "tm_score": self.tm_score,
            "qa_issues": self.qa_issues,
            "glossary_hits": self.glossary_hits,
            "was_rewritten": self.was_rewritten,
            "tokens_used": self.tokens_used,
            "confidence_label": self.confidence_label,
            "confidence_score": self.confidence_score,
            "needs_review": self.needs_review,
        }


@dataclass
class BatchResult:
    results: list[TranslationResult] = field(default_factory=list)
    total_tokens: int = 0
    tm_hits: int = 0
    fuzzy_hits: int = 0
    tfidf_hits: int = 0
    glossary_hits: int = 0
    ai_hits: int = 0
    qa_corrections: int = 0
    low_confidence_rows: list[int] = field(default_factory=list)
    processing_time: float = 0.0

    @property
    def consistency_score(self) -> float:
        if not self.results:
            return 1.0
        tm_gl = sum(
            1 for r in self.results
            if r.source_type in (TranslationSource.TM_EXACT, TranslationSource.TM_FUZZY,
                                  TranslationSource.TFIDF, TranslationSource.GLOSSARY)
        )
        return tm_gl / len(self.results)

    @property
    def api_savings_pct(self) -> float:
        if not self.results:
            return 0.0
        non_ai = sum(1 for r in self.results if r.source_type != TranslationSource.GPT)
        return non_ai / len(self.results)


GPT_SYSTEM_PROMPT = """You are a professional Dutch localization specialist for Home24.nl, a premium furniture and home decoration retailer.

Rules:
- Translate German product content to natural, native Dutch (nl-NL)
- Follow Home24.nl Dutch terminology strictly
- Never invent new terminology — use established Dutch furniture vocabulary
- Product model names (proper nouns) stay unchanged
- Decor names use "look" suffix: eikenlook, betonlook, notenlook, marmereffect
- Colors lowercase unless sentence-initial
- Never leave German words in output

Output: only the Dutch translation, no explanation, no quotes."""


def _load_api_key() -> str:
    # Load from Streamlit secrets first, then .env
    try:
        import streamlit as st
        key = st.secrets.get("OPENAI_API_KEY", "")
        if key:
            return key
    except Exception:
        pass
    return os.getenv("OPENAI_API_KEY", "")


class TranslationEngine:

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._api_key = api_key or _load_api_key()
        self._model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self._client = None
        self._tm = get_matcher()
        self._fuzzy = FuzzyMatcher(threshold=float(os.getenv("TM_FUZZY_THRESHOLD", "0.75")))
        self._semantic = get_semantic_matcher(min_score=0.60)
        self._glossary = get_glossary_manager()
        self._consistency = get_consistency_engine()
        self._context = get_context_engine()
        self._rewriter = get_rewriter()
        self._residue = get_residue_detector()
        self._qa = get_qa_engine()
        self._optimizer = get_name_optimizer()
        self._dedup_cache: dict[str, str] = {}

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self._api_key)
        return self._client

    # ─── Single segment ───────────────────────────────────────────────

    def translate_single(self, source: str, context_data: dict | None = None) -> TranslationResult:
        if not source or not source.strip():
            return TranslationResult(source, source, TranslationSource.EMPTY,
                                     confidence_label="EMPTY", confidence_score=1.0)

        # Deduplication: same source text → same result
        if source in self._dedup_cache:
            cached = self._dedup_cache[source]
            return TranslationResult(source, cached, TranslationSource.TM_EXACT,
                                     tm_score=1.0, confidence_label="EXACT_TM", confidence_score=1.0)

        # ── Step 1: Exact TM match ──
        tm = self._tm.match(source)
        if tm and tm.match_type == MatchType.EXACT:
            result = self._post_process(source, tm.target, TranslationSource.TM_EXACT, 1.0)
            self._dedup_cache[source] = result.target
            return result

        # ── Step 2: Context lookup ──
        ctx = self._context.detect_context(context_data or {}, [])
        ctx_tl = self._context.get_context_translation(source, ctx)
        if ctx_tl:
            result = self._post_process(source, ctx_tl, TranslationSource.CONTEXT, 0.90)
            self._dedup_cache[source] = result.target
            return result

        # ── Step 3: Glossary (high confidence) ──
        gl = self._glossary.lookup(source)
        if gl and gl.confidence >= 0.85:
            result = self._post_process(source, gl.target_term, TranslationSource.GLOSSARY, gl.confidence)
            self._dedup_cache[source] = result.target
            return result

        # ── Step 4a: RapidFuzz fuzzy match ──
        if tm and tm.match_type in (MatchType.FUZZY, MatchType.PATTERN):
            result = self._post_process(source, tm.target, TranslationSource.TM_FUZZY, tm.score)
            self._dedup_cache[source] = result.target
            return result

        # ── Step 4b: TF-IDF semantic match ──
        if self._semantic.is_ready:
            sem = self._semantic.best_match(source)
            if sem and sem.score >= 0.65:
                result = self._post_process(source, sem.target, TranslationSource.TFIDF, sem.score)
                self._dedup_cache[source] = result.target
                return result

        # ── Step 4c: Low-confidence glossary ──
        if gl and gl.confidence >= 0.60:
            result = self._post_process(source, gl.target_term, TranslationSource.GLOSSARY, gl.confidence)
            self._dedup_cache[source] = result.target
            return result

        # ── Step 5: OpenAI GPT fallback ──
        translation, tokens = self._ai_translate(source, ctx)
        result = self._post_process(source, translation, TranslationSource.GPT, 0.0)
        result.tokens_used = tokens
        self._dedup_cache[source] = result.target
        return result

    # ─── Batch ────────────────────────────────────────────────────────

    def translate_batch(
        self,
        items: list[tuple[int, str]],
        context_rows: list[dict] | None = None,
        filename: str = "",
        progress_callback=None,
    ) -> BatchResult:
        start = time.time()
        batch = BatchResult()
        translations: list[tuple[str, str]] = []
        ctx_rows = context_rows or [{} for _ in items]

        for i, (row_idx, source) in enumerate(items):
            ctx = ctx_rows[i] if i < len(ctx_rows) else {}
            res = self.translate_single(source, ctx)
            batch.results.append(res)
            translations.append((source, res.target))

            match res.source_type:
                case TranslationSource.TM_EXACT:
                    batch.tm_hits += 1
                case TranslationSource.TM_FUZZY | TranslationSource.TM_PATTERN:
                    batch.fuzzy_hits += 1
                case TranslationSource.TFIDF:
                    batch.tfidf_hits += 1
                case TranslationSource.GLOSSARY | TranslationSource.CONTEXT:
                    batch.glossary_hits += 1
                case TranslationSource.GPT:
                    batch.ai_hits += 1

            batch.total_tokens += res.tokens_used
            batch.qa_corrections += sum(1 for q in res.qa_issues if getattr(q, "auto_fixable", False))

            if res.needs_review:
                batch.low_confidence_rows.append(row_idx)

            if progress_callback:
                progress_callback((i + 1) / len(items))

        # Consistency pass across workbook
        resolved = self._consistency.resolve_workbook(translations)
        for i, new_target in enumerate(resolved):
            if new_target != batch.results[i].target:
                batch.results[i].target = new_target

        batch.processing_time = time.time() - start
        self._log_export(filename, batch)
        return batch

    # ─── Post-processing ──────────────────────────────────────────────

    def _post_process(self, source: str, translation: str, source_type: TranslationSource, score: float) -> TranslationResult:
        rewritten, _ = self._rewriter.rewrite(translation)
        was_rewritten = rewritten != translation
        translation = rewritten

        residue = self._residue.detect_and_clean(translation, auto_fix=True)
        translation = residue.text

        translation, gloss_hits = self._glossary.apply_glossary(source, translation)

        qa_result = self._qa.validate(translation, source)
        translation = qa_result.corrected

        was_optimized = False
        if _looks_like_product_name(source):
            optimized, actions = self._optimizer.optimize(translation)
            if optimized != translation:
                translation = optimized
                was_optimized = True

        conf = score_translation(
            source=source,
            translation=translation,
            source_type=source_type.value,
            tm_score=score,
            qa_issue_count=len(qa_result.issues),
        )

        return TranslationResult(
            source=source,
            target=translation,
            source_type=source_type,
            tm_score=score,
            qa_issues=qa_result.issues,
            glossary_hits=gloss_hits,
            was_rewritten=was_rewritten,
            was_optimized=was_optimized,
            confidence_label=conf.label.value,
            confidence_score=conf.score,
            needs_review=conf.needs_review,
        )

    # ─── OpenAI ───────────────────────────────────────────────────────

    def _ai_translate(self, source: str, ctx_signal=None) -> tuple[str, int]:
        if not self._api_key:
            return source, 0

        ctx_hint = ""
        if ctx_signal and ctx_signal.category != "general":
            cat_nl = {"kitchen": "keuken", "bathroom": "badkamer", "bedroom": "slaapkamer",
                      "living": "woonkamer", "outdoor": "buiten", "lighting": "verlichting",
                      "storage": "opbergruimte", "textile": "textiel", "dining": "eetkamer"
                      }.get(ctx_signal.category, "")
            if cat_nl:
                ctx_hint = f" [Category: {cat_nl}]"

        try:
            client = self._get_client()
            resp = client.chat.completions.create(
                model=self._model,
                max_tokens=256,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": GPT_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Translate to Dutch:{ctx_hint}\n{source}"},
                ],
            )
            translation = resp.choices[0].message.content.strip()
            tokens = resp.usage.total_tokens
            return translation, tokens
        except Exception:
            return source, 0

    def _log_export(self, filename: str, batch: BatchResult):
        if not filename:
            return
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO export_log "
                "(filename, rows_processed, tm_hits, fuzzy_hits, glossary_hits, ai_hits, "
                "qa_corrections, consistency_score, token_usage, processing_time) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (filename, len(batch.results), batch.tm_hits,
                 batch.fuzzy_hits + batch.tfidf_hits,
                 batch.glossary_hits, batch.ai_hits, batch.qa_corrections,
                 batch.consistency_score, batch.total_tokens, batch.processing_time),
            )

    def set_api_key(self, key: str):
        self._api_key = key
        self._client = None

    def warm_up_semantic(self, progress_callback=None):
        """Pre-build TF-IDF index so first translation is fast."""
        if not self._semantic.is_ready:
            self._semantic.build_index(progress_callback=progress_callback)


def _looks_like_product_name(text: str) -> bool:
    if not text:
        return False
    words = text.split()
    return len(words) >= 2 and any(w[0].isupper() for w in words if w)


_instance: TranslationEngine | None = None


def get_engine(api_key: str | None = None) -> TranslationEngine:
    global _instance
    if _instance is None:
        _instance = TranslationEngine(api_key=api_key)
    elif api_key and _instance._api_key != api_key:
        _instance.set_api_key(api_key)
    return _instance
