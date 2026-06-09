import json
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

# ── Model configuration ───────────────────────────────────────────────
# Override via env vars: OPENAI_MODEL_MAIN and OPENAI_MODEL_QA
_DEFAULT_MODEL_MAIN = os.getenv("OPENAI_MODEL_MAIN", "gpt-5.5")
_DEFAULT_MODEL_QA   = os.getenv("OPENAI_MODEL_QA",   "gpt-5.5-mini")


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


# ── System prompt ─────────────────────────────────────────────────────

GPT_SYSTEM_PROMPT = """You are a senior bilingual German-to-Dutch copywriter and product localization expert for Home24 Netherlands, specialized in furniture and home decor e-commerce.

Your mission is NOT to translate literally. Your mission is to produce a fluent, natural, premium Dutch version that reads like it was originally written by a skilled Home24.nl copywriter.

COLUMNS TO TRANSLATE: name, colorDetail, deliveryScope, otherMeasurements, qualityDetail, textileCompositionCover1, variantName, materialDetail, textileComposition
NEVER TRANSLATE OR MODIFY: articleNumber, SKU, ID, EAN, GTIN
PRESERVE EXACTLY: all <br> tags, Excel structure, dimensions and numbers

HOME24.NL TERMINOLOGY (use these exact forms):
- Bezug → bekleding (textile) / hoes (fitted cover)
- Gestell → frame or onderstel
- Maße / Maß → afmetingen
- Set bestehend aus → set bestaande uit
- B x H x T → B x H x D
- Liegehöhe → lighoogte
- Tischplatte → tafelblad, Arbeitsplatte → werkblad
- Dekor / Decor → look (suffix: eikenlook, notenlook, betonlook)
- Eiche Sägerau Dekor → grof gezaagde eikenlook
- Nussbaum Dekor → notenlook
- MDF → MDF (NEVER expand, NEVER add parenthetical)
- Singleküche → mini keuken, Kücheninsel → kookeiland
- 2er-Set → set van 2, 3er-Set → set van 3
- Rollen → rollen (furniture), Duschmatte → douchemat
- Bettwäsche → beddengoed, Eisen → IJzer (capital IJ)
- Herrendiener → herenknecht, Tellerstand → bordenstandaard

MANDATORY GERMAN→DUTCH CONVERSIONS:
- ohne → zonder, mit → met, und → en, oder → of, für → voor
- aus → van/uit, bestehend aus → bestaande uit
- Schwarz → zwart, Weiß/Weiss → wit, Grau → grijs
- Hellgrau → lichtgrijs, Dunkelgrau → donkergrijs
- Braun → bruin, Grün → groen, Blau → blauw, Rot → rood
- Gelb → geel, Sand → zand, Orange → oranje, Rosa → roze
- Metall → metaal, Holz → hout, Leder → leer, Kunststoff → kunststof
- lackiert → gelakt, beschichtet → gecoat, foliert → gefolieerd
- pulverbeschichtet → poedergecoat

PRODUCT NAME RULES (column "name" only):
- Maximum 40 characters — HARD LIMIT
- No brackets, no commas
- Forbidden endings: met, van, voor, keramische, schuin(e), houten, eikenhouten, elektrische, ronde, rechte
- Never cut mid-adjective — always end on a complete noun or complete phrase
- If too long: abbreviate elegantly, preserve the model name

DUTCH STYLE RULES:
- Colors and materials: lowercase (zwart, wit, grijs, eikenlook)
- After colon: lowercase unless proper noun
- IJzer, not Ijzer or ijzer
- Never sound robotic or German-structured

OUTPUT FORMAT (CRITICAL):
- Return ONLY the Dutch translation — nothing else
- FORBIDDEN output prefixes: Categorie:, Category:, Product type:, Context:, Note:, Explanation:
- Never add metadata, labels, or annotations
- If category context is provided in the system message, use it internally ONLY — never output it"""


# Metadata leak pattern — strips injected label lines before output
_METADATA_LEAK_RE = re.compile(
    r"(?mi)^(?:Categorie|Category|Product\s*categor(?:y|ie)|Product\s*type|Product\s*soort"
    r"|Context|Note|Explanation|Toelichting)\s*:.*$\n?"
)


def _strip_metadata_leaks(text: str) -> str:
    return _METADATA_LEAK_RE.sub("", text).strip()


# ── Column-specific instructions ──────────────────────────────────────

_COLUMN_RULES: dict[str, str] = {
    "name": (
        "Hard limit: 40 characters. No brackets, no commas. "
        "Format: product type + model name. "
        "End on a complete noun. "
        "Forbidden endings: met, van, voor, keramische, schuin(e), houten, eikenhouten, elektrische, ronde, rechte."
    ),
    "materialDetail": (
        "Concise material wording. Lowercase materials. "
        "MDF stays exactly 'MDF' — never expand or add parenthetical. "
        "Remove German parenthetical explanations. "
        "Use: eikenhout, notenhout, spaanplaat, MDF, metaal, staal, aluminium, kunststof, glas, leer, stof."
    ),
    "colorDetail": (
        "Color names lowercase. Use slash for combinations (zwart/wit). "
        "Translate German colors: Schwarz→zwart, Weiß→wit, Grau→grijs, Braun→bruin, Grün→groen, Rot→rood."
    ),
    "deliveryScope": (
        "Complete delivery information. Natural Dutch. Preserve <br> tags exactly. "
        "No metadata injection. Set bestehend aus → set bestaande uit."
    ),
    "otherMeasurements": (
        "Translate dimension labels only. Preserve all numbers and units. "
        "B x H x T → B x H x D. Liegehöhe → lighoogte. No category injection."
    ),
    "qualityDetail": (
        "Natural Dutch product copy. No German residue. "
        "ohne → zonder, mit → met. Professional tone."
    ),
    "variantName": (
        "Concise. Lowercase where appropriate. No unnecessary capitalization. "
        "Translate colors and materials."
    ),
    "textileCompositionCover1": (
        "Textile composition. Lowercase material names. "
        "Mehrfarbig → meerdere kleuren. Translate percentages + material names."
    ),
    "textileComposition": (
        "Textile composition. Lowercase. Translate all material and color terms."
    ),
}


def _column_instructions(col_name: str) -> str:
    return _COLUMN_RULES.get(col_name, "Translate naturally to Dutch. No German residue.")


# ── Pre-translation dimension label normalization ─────────────────────
# Applied BEFORE TM lookup so bad TM fuzzy matches don't garble labels.
_DIM_LABEL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bB\s*[x×]\s*H\s*[x×]\s*T\b"), "B x H x D"),
    (re.compile(r"\bLiegehöhe\b", re.IGNORECASE), "lighoogte"),
    (re.compile(r"\bSitzhöhe\b", re.IGNORECASE), "zithoogte"),
    (re.compile(r"\bArmlehnenh(?:ö)he\b", re.IGNORECASE), "armleuninghoogte"),
    (re.compile(r"\bBetthöhe\b", re.IGNORECASE), "bedhoogte"),
]

_NAME_FORBIDDEN_ENDINGS = frozenset({
    "met", "van", "voor", "uit", "en", "of", "de", "het", "een", "in",
    "naar", "op", "bij", "als", "per", "tot",
})


def _apply_dim_labels(text: str) -> str:
    for pat, repl in _DIM_LABEL_PATTERNS:
        text = pat.sub(repl, text)
    return text


def _truncate_name(text: str, max_len: int = 40) -> str:
    if len(text) <= max_len:
        return text
    truncated = text[:max_len].rsplit(" ", 1)[0]
    words = truncated.split()
    while words and words[-1].lower() in _NAME_FORBIDDEN_ENDINGS:
        words.pop()
    return " ".join(words) if words else text[:max_len].strip()


# ── Category map ──────────────────────────────────────────────────────

_CAT_NL_MAP: dict[str, str] = {
    "kitchen": "keuken", "bathroom": "badkamer", "bedroom": "slaapkamer",
    "sofa": "woonkamer", "outdoor": "buiten", "lighting": "verlichting",
    "storage": "opbergruimte", "textile": "textiel", "dining": "eetkamer",
    "decoration": "decoratie", "office": "kantoor",
}


def _load_api_key() -> str:
    from auth.credentials import get_openai_key
    return get_openai_key()


class TranslationEngine:

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._api_key = api_key or _load_api_key()
        self._model = model or _DEFAULT_MODEL_MAIN
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

        # Intelligence engines
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

    # ─── Deterministic path (steps 1–7, no GPT) ──────────────────────

    def _translate_deterministic(
        self,
        source: str,
        context_data: dict | None = None,
    ) -> tuple["TranslationResult | None", object, str]:
        """Run all deterministic steps. Returns (result_or_None, ctx_signal, product_type).

        None result means GPT is required.
        """
        if not source or not source.strip():
            return (
                TranslationResult(source, source, TranslationSource.EMPTY,
                                  confidence_label="EMPTY", confidence_score=1.0),
                None, "general",
            )

        # Pre-normalize dimension labels before TM lookup prevents bad fuzzy matches
        source = _apply_dim_labels(source)

        if source in self._dedup_cache:
            cached = self._dedup_cache[source]
            return (
                TranslationResult(source, cached, TranslationSource.TM_EXACT,
                                  tm_score=1.0, confidence_label="EXACT_TM",
                                  confidence_score=1.0, warning_level="ok"),
                None, "general",
            )

        ctx_dict = context_data or {}
        classification = self._classifier.classify(source, *[str(v) for v in ctx_dict.values()])
        product_type = classification.product_type

        # Step 2: Category glossary
        if product_type != "general":
            cat_term = self._cat_glossary.lookup(source, product_type)
            if cat_term:
                r = self._post_process(source, cat_term, TranslationSource.CATEGORY_GLOSSARY, 0.93, product_type)
                self._dedup_cache[source] = r.target
                return r, None, product_type

        # Step 3: Global glossary (high confidence)
        gl = self._glossary.lookup(source)
        if gl and gl.confidence >= 0.92:
            r = self._post_process(source, gl.target_term, TranslationSource.GLOSSARY, gl.confidence, product_type)
            self._dedup_cache[source] = r.target
            return r, None, product_type

        # Step 4: Phrase memory
        phrase = self._phrase_mem.lookup(source, product_type)
        if phrase:
            r = self._post_process(source, phrase, TranslationSource.PHRASE_MEMORY, 0.97, product_type)
            self._dedup_cache[source] = r.target
            return r, None, product_type

        # Step 5: Exact TM
        tm = self._tm.match(source)
        if tm and tm.match_type == MatchType.EXACT:
            r = self._post_process(source, tm.target, TranslationSource.TM_EXACT, 1.0, product_type)
            self._dedup_cache[source] = r.target
            return r, None, product_type

        # Step 6: Fuzzy TM
        if tm and tm.match_type in (MatchType.FUZZY, MatchType.PATTERN):
            r = self._post_process(source, tm.target, TranslationSource.TM_FUZZY, tm.score, product_type)
            self._dedup_cache[source] = r.target
            return r, None, product_type

        # Step 6b: Context translation
        ctx_signal = self._context.detect_context(ctx_dict, [])
        ctx_tl = self._context.get_context_translation(source, ctx_signal)
        if ctx_tl:
            r = self._post_process(source, ctx_tl, TranslationSource.CONTEXT, 0.88, product_type)
            self._dedup_cache[source] = r.target
            return r, ctx_signal, product_type

        # Step 6c: Moderate glossary
        if gl and gl.confidence >= 0.75:
            r = self._post_process(source, gl.target_term, TranslationSource.GLOSSARY, gl.confidence, product_type)
            self._dedup_cache[source] = r.target
            return r, ctx_signal, product_type

        # Step 7: Corpus
        corpus_match = self._corpus.best_match(source, product_type if product_type != "general" else None)
        if corpus_match:
            corpus_text, corpus_score = corpus_match
            if corpus_score >= 0.75:
                r = self._post_process(source, corpus_text, TranslationSource.CORPUS, corpus_score, product_type)
                self._dedup_cache[source] = r.target
                return r, ctx_signal, product_type

        # Step 7b: TF-IDF semantic
        if self._semantic.is_ready:
            sem = self._semantic.best_match(source)
            if sem and sem.score >= 0.65:
                r = self._post_process(source, sem.target, TranslationSource.TFIDF, sem.score, product_type)
                self._dedup_cache[source] = r.target
                return r, ctx_signal, product_type

        # Step 7c: Low-confidence glossary
        if gl and gl.confidence >= 0.60:
            r = self._post_process(source, gl.target_term, TranslationSource.GLOSSARY, gl.confidence, product_type)
            self._dedup_cache[source] = r.target
            return r, ctx_signal, product_type

        # Nothing resolved — GPT needed
        return None, ctx_signal, product_type

    # ─── Single segment — full 14-step pipeline ──────────────────────

    def translate_single(self, source: str, context_data: dict | None = None) -> TranslationResult:
        det_result, ctx_signal, product_type = self._translate_deterministic(source, context_data)
        if det_result is not None:
            return det_result

        # Step 8: GPT
        translation, tokens = self._ai_translate(source, ctx_signal, product_type)
        result = self._post_process(source, translation, TranslationSource.GPT, 0.0, product_type)
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
        column_name: str = "",
    ) -> BatchResult:
        start = time.time()
        batch = BatchResult()
        translations: list[tuple[str, str]] = []
        ctx_rows = context_rows or [{} for _ in items]

        # Stage 1: Deterministic steps for all items
        gpt_queue: list[tuple[int, int, str, object, str]] = []  # (i, row_idx, source, ctx_signal, product_type)
        results: list[TranslationResult | None] = [None] * len(items)

        for i, (row_idx, source) in enumerate(items):
            ctx = ctx_rows[i] if i < len(ctx_rows) else {}
            det_result, ctx_signal, product_type = self._translate_deterministic(source, ctx)

            if det_result is not None:
                results[i] = det_result
            else:
                gpt_queue.append((i, row_idx, source, ctx_signal, product_type))

            if progress_callback:
                # First half of progress bar is deterministic pass
                progress_callback((i + 1) / (len(items) * 2))

        # Stage 2: Batch GPT for remaining items (if any)
        if gpt_queue:
            if self._api_key and len(gpt_queue) > 1 and column_name:
                # True batch: single GPT call for multiple cells
                batch_translations, batch_tokens = self._ai_translate_batch(
                    [(i, source) for i, _, source, _, _ in gpt_queue],
                    column_name=column_name,
                    product_type=gpt_queue[0][4],
                    ctx_signal=gpt_queue[0][3],
                )
                for j, (i, row_idx, source, ctx_signal, product_type) in enumerate(gpt_queue):
                    translation = batch_translations.get(i, source)
                    res = self._post_process(source, translation, TranslationSource.GPT, 0.0, product_type)
                    res.tokens_used = batch_tokens // max(len(gpt_queue), 1)
                    results[i] = res
                    self._dedup_cache[source] = res.target
            else:
                # Single-cell GPT fallback
                for j, (i, row_idx, source, ctx_signal, product_type) in enumerate(gpt_queue):
                    translation, tokens = self._ai_translate(source, ctx_signal, product_type, column_name)
                    res = self._post_process(source, translation, TranslationSource.GPT, 0.0, product_type)
                    res.tokens_used = tokens
                    results[i] = res
                    self._dedup_cache[source] = res.target

                    if progress_callback:
                        offset = len(items)
                        progress_callback((offset + j + 1) / (len(items) * 2))

        # Assemble batch result
        for i, (row_idx, source) in enumerate(items):
            res = results[i]
            if res is None:
                res = TranslationResult(source, source, TranslationSource.EMPTY,
                                        confidence_label="EMPTY", confidence_score=1.0)
                results[i] = res

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
            progress_callback(1.0)

        # Step 11: Consistency pass
        resolved = self._consistency.resolve_workbook(translations)
        for i, new_target in enumerate(resolved):
            if new_target != batch.results[i].target:
                batch.results[i].target = new_target

        # Enforce 40-char limit for product name column (after consistency pass)
        if column_name == "name":
            for res in batch.results:
                if res and res.target:
                    res.target = _truncate_name(res.target)

        batch.processing_time = time.time() - start
        self._log_export(filename, batch)
        return batch

    # ─── Post-processing ──────────────────────────────────────────────

    def _post_process(
        self,
        source: str,
        translation: str,
        source_type: TranslationSource,
        score: float,
        product_type: str = "general",
    ) -> TranslationResult:
        translation, _ = self._material.apply(translation, product_type)

        if _looks_like_product_name(source) and source_type in (
            TranslationSource.TM_EXACT, TranslationSource.TM_FUZZY,
            TranslationSource.CORPUS, TranslationSource.GPT,
        ):
            generated, did_generate = self._name_gen.translate_or_passthrough(source)
            if did_generate and source_type == TranslationSource.GPT:
                translation = generated

        # Metadata leak safety net
        translation = _strip_metadata_leaks(translation)

        # MDF normalization + Home24 label normalization
        from engines.qa_engine import normalize_mdf_nl, normalize_home24_labels_nl
        translation = normalize_home24_labels_nl(translation)
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

        # QA engine
        qa_result = self._qa.validate(translation, source)
        translation = qa_result.corrected

        # Name optimizer
        was_optimized = False
        if _looks_like_product_name(source):
            optimized, _ = self._optimizer.optimize(translation)
            if optimized != translation:
                translation = optimized
                was_optimized = True

        # Confidence scoring
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

    # ─── Single-cell GPT ──────────────────────────────────────────────

    def _ai_translate(
        self,
        source: str,
        ctx_signal=None,
        product_type: str = "general",
        column_name: str = "",
    ) -> tuple[str, int]:
        if not self._api_key:
            return source, 0

        cat_nl = _CAT_NL_MAP.get(product_type, "")
        if not cat_nl and ctx_signal and getattr(ctx_signal, "category", "general") != "general":
            cat_nl = _CAT_NL_MAP.get(ctx_signal.category, "")

        system_content = GPT_SYSTEM_PROMPT
        if column_name:
            system_content += f"\n\nColumn-specific rules for '{column_name}':\n{_column_instructions(column_name)}"
        if cat_nl:
            system_content += f"\n\nInternal context (do NOT reproduce in output): product category = {cat_nl}"

        try:
            client = self._get_client()
            resp = client.chat.completions.create(
                model=self._model,
                max_tokens=300,
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

    # ─── Batch GPT (JSON) ─────────────────────────────────────────────

    def _ai_translate_batch(
        self,
        items: list[tuple[int, str]],   # (item_idx, source_text)
        column_name: str = "",
        product_type: str = "general",
        ctx_signal=None,
    ) -> tuple[dict[int, str], int]:
        """Translate multiple cells in one GPT call using JSON output.

        Returns ({item_idx: dutch_translation}, total_tokens).
        Falls back to source text per item if parsing fails.
        """
        if not self._api_key or not items:
            return {i: src for i, src in items}, 0

        cat_nl = _CAT_NL_MAP.get(product_type, "")
        if not cat_nl and ctx_signal and getattr(ctx_signal, "category", "general") != "general":
            cat_nl = _CAT_NL_MAP.get(ctx_signal.category, "")

        system_content = GPT_SYSTEM_PROMPT
        if column_name:
            system_content += f"\n\nColumn-specific rules for '{column_name}':\n{_column_instructions(column_name)}"
        if cat_nl:
            system_content += f"\n\nInternal context (do NOT reproduce in output): product category = {cat_nl}"

        batch_input = [{"id": i, "source": src} for i, src in items]
        user_content = (
            "Translate each 'source' to Dutch. "
            "Return a JSON array. Each object must have 'id' (unchanged integer) "
            "and 'translation' (Dutch text only, no metadata, no labels).\n\n"
            f"{json.dumps(batch_input, ensure_ascii=False)}"
        )

        try:
            client = self._get_client()
            resp = client.chat.completions.create(
                model=self._model,
                max_tokens=min(len(items) * 300, 4096),
                temperature=0.1,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content},
                ],
            )
            raw = resp.choices[0].message.content.strip()
            tokens = resp.usage.total_tokens
            parsed = self._parse_batch_json(raw, items)

            # If fewer than half items parsed successfully, retry as individual calls
            resolved = sum(1 for i, src in items if parsed.get(i) and parsed.get(i) != src)
            if resolved < len(items) // 2:
                raise ValueError("Batch parse yield too low — retrying individually")

            return parsed, tokens

        except Exception:
            # Fallback: individual single-cell calls
            fallback: dict[int, str] = {}
            total_tokens = 0
            for i, source in items:
                translation, tok = self._ai_translate(source, ctx_signal, product_type, column_name)
                fallback[i] = translation
                total_tokens += tok
            return fallback, total_tokens

    def _parse_batch_json(self, raw: str, items: list[tuple[int, str]]) -> dict[int, str]:
        """Parse JSON array from GPT batch response. Missing items fall back to source."""
        item_map = {i: source for i, source in items}
        try:
            # Extract JSON array from response (model may wrap in markdown or prose)
            json_start = raw.find("[")
            json_end = raw.rfind("]") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = raw[json_start:json_end]
            else:
                json_str = raw

            parsed = json.loads(json_str)
            result: dict[int, str] = {}
            for obj in parsed:
                idx = obj.get("id")
                translation = (obj.get("translation") or "").strip()
                if idx is not None and translation:
                    result[int(idx)] = _strip_metadata_leaks(translation)

            # Fill missing items with source
            for i, source in items:
                if i not in result:
                    result[i] = source

            return result

        except (json.JSONDecodeError, ValueError, TypeError):
            return item_map

    # ─── Export log ───────────────────────────────────────────────────

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
