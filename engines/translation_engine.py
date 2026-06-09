import os
import re
import time
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
from engines.product_classifier import get_classifier
from engines.category_glossary import get_category_glossary
from engines.phrase_memory import get_phrase_memory
from engines.corpus_engine import get_corpus_engine
from engines.product_name_generator import get_name_generator
from engines.material_context import get_material_engine
from database.database import get_connection


class TranslationSource(str, Enum):
    TM_EXACT = "TM_EXACT"
    TM_FUZZY = "TM_FUZZY"
    TM_PATTERN = "TM_PATTERN"
    TFIDF = "TFIDF"
    GLOSSARY = "GLOSSARY"
    CATEGORY_GLOSSARY = "CATEGORY_GLOSSARY"
    PHRASE_MEMORY = "PHRASE_MEMORY"
    CORPUS = "CORPUS"
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
    warning_level: str = "ok"
    product_type: str = "general"

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
            "warning_level": self.warning_level,
            "product_type": self.product_type,
        }


@dataclass
class BatchResult:
    results: list[TranslationResult] = field(default_factory=list)
    total_tokens: int = 0
    tm_hits: int = 0
    fuzzy_hits: int = 0
    tfidf_hits: int = 0
    glossary_hits: int = 0
    phrase_hits: int = 0
    corpus_hits: int = 0
    ai_hits: int = 0
    qa_corrections: int = 0
    low_confidence_rows: list[int] = field(default_factory=list)
    warning_rows: list[int] = field(default_factory=list)
    critical_rows: list[int] = field(default_factory=list)
    processing_time: float = 0.0

    @property
    def consistency_score(self) -> float:
        if not self.results:
            return 1.0
        non_ai = sum(
            1 for r in self.results
            if r.source_type not in (TranslationSource.GPT, TranslationSource.EMPTY)
        )
        return non_ai / len(self.results)

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

Output format (CRITICAL):
- Return ONLY the Dutch translation of the source text — nothing else
- Do NOT add labels, metadata, categories, context, explanations, or annotations
- Forbidden output prefixes (never use these): Categorie:, Category:, Product type:, Context:, Note:, Explanation:
- If product category context is provided, use it for understanding only — never mention it in the output"""


# Strips any AI-injected metadata labels from output — safety net applied before the result leaves _ai_translate
_METADATA_LEAK_RE = re.compile(
    r"(?mi)^(?:Categorie|Category|Product\s*categor(?:y|ie)|Product\s*type|Product\s*soort"
    r"|Context|Note|Explanation|Toelichting)\s*:.*$\n?"
)


def _strip_metadata_leaks(text: str) -> str:
    return _METADATA_LEAK_RE.sub("", text).strip()


def _load_api_key() -> str:
    from auth.credentials import get_openai_key
    return get_openai_key()


class TranslationEngine:

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._api_key = api_key or _load_api_key()
        self._model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self._client = None

        # Core engines
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

        # New intelligence engines
        self._classifier = get_classifier()
        self._cat_glossary = get_category_glossary()
        self._phrase_mem = get_phrase_memory()
        self._corpus = get_corpus_engine()
        self._name_gen = get_name_generator()
        self._material = get_material_engine()

        self._dedup_cache: dict[str, str] = {}

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self._api_key)
        return self._client

    # ─── Single segment — 14-step pipeline ───────────────────────────

    def translate_single(self, source: str, context_data: dict | None = None) -> TranslationResult:
        if not source or not source.strip():
            return TranslationResult(source, source, TranslationSource.EMPTY,
                                     confidence_label="EMPTY", confidence_score=1.0)

        if source in self._dedup_cache:
            cached = self._dedup_cache[source]
            return TranslationResult(source, cached, TranslationSource.TM_EXACT,
                                     tm_score=1.0, confidence_label="EXACT_TM",
                                     confidence_score=1.0, warning_level="ok")

        # ── Step 1: Category detection ────────────────────────────────
        ctx_dict = context_data or {}
        classification = self._classifier.classify(
            source,
            *[str(v) for v in ctx_dict.values()]
        )
        product_type = classification.product_type

        # ── Step 2: Category glossary ────────────────────────────────
        if product_type != "general":
            cat_term = self._cat_glossary.lookup(source, product_type)
            if cat_term:
                result = self._post_process(
                    source, cat_term, TranslationSource.CATEGORY_GLOSSARY,
                    0.93, product_type
                )
                self._dedup_cache[source] = result.target
                return result

        # ── Step 3: Global glossary (high confidence) ─────────────────
        gl = self._glossary.lookup(source)
        if gl and gl.confidence >= 0.92:
            result = self._post_process(
                source, gl.target_term, TranslationSource.GLOSSARY,
                gl.confidence, product_type
            )
            self._dedup_cache[source] = result.target
            return result

        # ── Step 4: Phrase memory ─────────────────────────────────────
        phrase = self._phrase_mem.lookup(source, product_type)
        if phrase:
            result = self._post_process(
                source, phrase, TranslationSource.PHRASE_MEMORY,
                0.97, product_type
            )
            self._dedup_cache[source] = result.target
            return result

        # ── Step 5: Exact TM match ────────────────────────────────────
        tm = self._tm.match(source)
        if tm and tm.match_type == MatchType.EXACT:
            result = self._post_process(
                source, tm.target, TranslationSource.TM_EXACT,
                1.0, product_type
            )
            self._dedup_cache[source] = result.target
            return result

        # ── Step 6: Fuzzy TM match ────────────────────────────────────
        if tm and tm.match_type in (MatchType.FUZZY, MatchType.PATTERN):
            result = self._post_process(
                source, tm.target, TranslationSource.TM_FUZZY,
                tm.score, product_type
            )
            self._dedup_cache[source] = result.target
            return result

        # Context signal for GPT hint (used later if needed)
        ctx_signal = self._context.detect_context(ctx_dict, [])
        ctx_tl = self._context.get_context_translation(source, ctx_signal)
        if ctx_tl:
            result = self._post_process(
                source, ctx_tl, TranslationSource.CONTEXT,
                0.88, product_type
            )
            self._dedup_cache[source] = result.target
            return result

        # ── Step 6b: Moderate-confidence global glossary ──────────────
        if gl and gl.confidence >= 0.75:
            result = self._post_process(
                source, gl.target_term, TranslationSource.GLOSSARY,
                gl.confidence, product_type
            )
            self._dedup_cache[source] = result.target
            return result

        # ── Step 7: Corpus lookup ─────────────────────────────────────
        corpus_match = self._corpus.best_match(source, product_type if product_type != "general" else None)
        if corpus_match:
            corpus_text, corpus_score = corpus_match
            if corpus_score >= 0.75:
                result = self._post_process(
                    source, corpus_text, TranslationSource.CORPUS,
                    corpus_score, product_type
                )
                self._dedup_cache[source] = result.target
                return result

        # ── Step 7b: TF-IDF semantic match ────────────────────────────
        if self._semantic.is_ready:
            sem = self._semantic.best_match(source)
            if sem and sem.score >= 0.65:
                result = self._post_process(
                    source, sem.target, TranslationSource.TFIDF,
                    sem.score, product_type
                )
                self._dedup_cache[source] = result.target
                return result

        # ── Step 7c: Low-confidence glossary ─────────────────────────
        if gl and gl.confidence >= 0.60:
            result = self._post_process(
                source, gl.target_term, TranslationSource.GLOSSARY,
                gl.confidence, product_type
            )
            self._dedup_cache[source] = result.target
            return result

        # ── Step 8: GPT generation ────────────────────────────────────
        translation, tokens = self._ai_translate(source, ctx_signal, product_type)

        # ── Step 9: Product name generation post-correction ───────────
        if _looks_like_product_name(source):
            generated, did_generate = self._name_gen.translate_or_passthrough(source)
            if did_generate:
                translation = generated

        # ── Step 10: Material context correction ──────────────────────
        translation, _ = self._material.apply(translation, product_type)

        result = self._post_process(
            source, translation, TranslationSource.GPT,
            0.0, product_type
        )
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
                case TranslationSource.GLOSSARY | TranslationSource.CATEGORY_GLOSSARY | TranslationSource.CONTEXT:
                    batch.glossary_hits += 1
                case TranslationSource.PHRASE_MEMORY:
                    batch.phrase_hits += 1
                case TranslationSource.CORPUS:
                    batch.corpus_hits += 1
                case TranslationSource.GPT:
                    batch.ai_hits += 1

            batch.total_tokens += res.tokens_used
            batch.qa_corrections += sum(1 for q in res.qa_issues if getattr(q, "auto_fixable", False))

            if res.needs_review:
                batch.low_confidence_rows.append(row_idx)

            if res.warning_level == "critical":
                batch.critical_rows.append(row_idx)
            elif res.warning_level == "warning":
                batch.warning_rows.append(row_idx)

            if progress_callback:
                progress_callback((i + 1) / len(items))

        # ── Step 11: Consistency pass across workbook ─────────────────
        resolved = self._consistency.resolve_workbook(translations)
        for i, new_target in enumerate(resolved):
            if new_target != batch.results[i].target:
                batch.results[i].target = new_target

        batch.processing_time = time.time() - start
        self._log_export(filename, batch)
        return batch

    # ─── Post-processing (steps 12–13 for single items) ──────────────

    def _post_process(
        self,
        source: str,
        translation: str,
        source_type: TranslationSource,
        score: float,
        product_type: str = "general",
    ) -> TranslationResult:
        # ── Step 10 (inline): Material context ───────────────────────
        translation, _ = self._material.apply(translation, product_type)

        # ── Step 9 (inline): Product name generation ─────────────────
        if _looks_like_product_name(source) and source_type in (
            TranslationSource.TM_EXACT, TranslationSource.TM_FUZZY,
            TranslationSource.CORPUS, TranslationSource.GPT,
        ):
            generated, did_generate = self._name_gen.translate_or_passthrough(source)
            if did_generate and source_type == TranslationSource.GPT:
                translation = generated

        # Metadata leak safety net — strip any injected label lines from any source
        translation = _strip_metadata_leaks(translation)

        # MDF normalization — remove parenthetical expansions, ensure uppercase
        from engines.qa_engine import normalize_mdf_nl
        translation = normalize_mdf_nl(translation)

        # Naturalness rewrite
        rewritten, _ = self._rewriter.rewrite(translation)
        was_rewritten = rewritten != translation
        translation = rewritten

        # German residue cleanup
        residue = self._residue.detect_and_clean(translation, auto_fix=True)
        translation = residue.text

        # Glossary enforcement
        translation, gloss_hits = self._glossary.apply_glossary(source, translation)

        # ── Step 12: QA engine ────────────────────────────────────────
        qa_result = self._qa.validate(translation, source)
        translation = qa_result.corrected

        # Name optimizer for product titles
        was_optimized = False
        if _looks_like_product_name(source):
            optimized, _ = self._optimizer.optimize(translation)
            if optimized != translation:
                translation = optimized
                was_optimized = True

        # ── Step 13: Confidence scoring ───────────────────────────────
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
            warning_level=conf.warning_level,
            product_type=product_type,
        )

    # ─── OpenAI ───────────────────────────────────────────────────────

    def _ai_translate(self, source: str, ctx_signal=None, product_type: str = "general") -> tuple[str, int]:
        if not self._api_key:
            return source, 0

        cat_nl_map = {
            "kitchen": "keuken", "bathroom": "badkamer", "bedroom": "slaapkamer",
            "sofa": "woonkamer", "outdoor": "buiten", "lighting": "verlichting",
            "storage": "opbergruimte", "textile": "textiel", "dining": "eetkamer",
            "decoration": "decoratie", "office": "kantoor",
        }
        cat_nl = cat_nl_map.get(product_type, "")
        if not cat_nl and ctx_signal and getattr(ctx_signal, "category", "general") != "general":
            cat_nl = cat_nl_map.get(ctx_signal.category, "")

        # Category hint goes into the system message only — never into user content
        system_content = GPT_SYSTEM_PROMPT
        if cat_nl:
            system_content += (
                f"\n\nInternal context (do NOT reproduce in output): product category = {cat_nl}"
            )

        try:
            client = self._get_client()
            resp = client.chat.completions.create(
                model=self._model,
                max_tokens=256,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": f"Translate to Dutch:\n{source}"},
                ],
            )
            translation = resp.choices[0].message.content.strip()
            translation = _strip_metadata_leaks(translation)
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
                (
                    filename, len(batch.results), batch.tm_hits,
                    batch.fuzzy_hits + batch.tfidf_hits,
                    batch.glossary_hits + batch.phrase_hits + batch.corpus_hits,
                    batch.ai_hits, batch.qa_corrections,
                    batch.consistency_score, batch.total_tokens, batch.processing_time,
                ),
            )

    def set_api_key(self, key: str):
        self._api_key = key
        self._client = None

    def warm_up_semantic(self, progress_callback=None):
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
