"""Centralized GPT (gpt-4o) client for the NL localization engine.

Design rule that fixes the historical silent-failure bug: a failed or
unusable GPT response is reported as an explicit ``GptResult(ok=False)`` —
it is NEVER replaced by the German source text. The orchestrator turns a
GPT failure into a blocking quality-gate issue instead of shipping German.

The model is read from ``OPENAI_MODEL`` (default ``gpt-4o``) so it can be
changed without touching code.
"""

import os
import re
import time
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

# Placeholder format used by ModelNameProtector — the prompt instructs GPT to
# copy these verbatim.
_PLACEHOLDER_RE = re.compile(r"⟦M\d+⟧")

_METADATA_LEAK_RE = re.compile(
    r"(?mi)^(?:Categorie|Category|Product\s*categor(?:y|ie)|Product\s*type"
    r"|Context|Note|Explanation|Toelichting|Vertaling|Translation)\s*:.*$\n?"
)

_SYSTEM_PROMPT = """You are a senior German-to-Dutch copywriter for Home24 Netherlands \
(furniture and home decor e-commerce). Produce fluent, natural, premium Dutch that \
reads like original Home24.nl copy — never a literal or German-structured translation.

HARD RULES:
- Output ONLY the Dutch translation. No labels, no notes, no quotes, no explanation.
- Copy every ⟦M…⟧ placeholder EXACTLY as-is. They are protected model names — never \
translate, reorder, or alter them.
- Preserve all numbers, dimensions and units exactly (e.g. "180 cm", "B x H x D").
- Preserve every <br> tag and the overall structure of the text.
- Colors and materials are lowercase (zwart, wit, grijs, eikenlook). "IJzer" keeps the \
capital IJ.
- Never leave any German word in the output."""


@dataclass
class GptResult:
    ok: bool
    text: str | None = None
    error: str = ""
    tokens: int = 0


def _clean(text: str) -> str:
    text = _METADATA_LEAK_RE.sub("", text).strip()
    # Strip wrapping quotes a model sometimes adds.
    if len(text) >= 2 and text[0] in "\"'" and text[-1] == text[0]:
        text = text[1:-1].strip()
    return text


class NLGptClient:
    def __init__(self, model: str | None = None, max_retries: int = 2):
        self._model = model or DEFAULT_MODEL
        self._max_retries = max_retries
        self._client = None
        self._key = None

    @property
    def model(self) -> str:
        return self._model

    def _key_value(self) -> str | None:
        if self._key is None:
            try:
                from auth.credentials import get_openai_key
                self._key = get_openai_key() or ""
            except Exception:
                self._key = ""
        return self._key or None

    @property
    def available(self) -> bool:
        return bool(self._key_value())

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self._key_value())
        return self._client

    def set_key(self, key: str):
        self._key = key or ""
        self._client = None

    # ── core call ──────────────────────────────────────────────────────

    def _chat(self, system: str, user: str, max_tokens: int) -> GptResult:
        if not self.available:
            return GptResult(ok=False, error="no_api_key")

        last_err = ""
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._get_client().chat.completions.create(
                    model=self._model,
                    temperature=0.1,
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
                raw = (resp.choices[0].message.content or "").strip()
                text = _clean(raw)
                tokens = getattr(resp.usage, "total_tokens", 0) or 0
                if not text:
                    last_err = "empty_response"
                    continue
                return GptResult(ok=True, text=text, tokens=tokens)
            except Exception as e:  # network, auth, bad model name, rate limit…
                last_err = f"{type(e).__name__}: {e}"
                if attempt < self._max_retries:
                    time.sleep(0.8 * (attempt + 1))
        return GptResult(ok=False, error=last_err or "unknown_error")

    # ── public helpers ──────────────────────────────────────────────────

    def translate(self, source: str, column: str = "", column_rule: str = "") -> GptResult:
        """Translate one (placeholder-masked) source segment to Dutch."""
        system = _SYSTEM_PROMPT
        if column and column_rule:
            system += f"\n\nColumn '{column}' rules:\n{column_rule}"
        result = self._chat(system, f"Translate to Dutch:\n{source}", max_tokens=400)
        result = self._verify_placeholders(source, result)
        return result

    def refine(self, dutch: str, instruction: str) -> GptResult:
        """Rewrite an existing Dutch segment per `instruction`, preserving data."""
        system = _SYSTEM_PROMPT + (
            "\n\nYou are refining EXISTING Dutch text. Keep all facts, numbers, "
            "placeholders and structure identical — only improve wording per the "
            "instruction."
        )
        user = f"{instruction}\n\nText:\n{dutch}"
        result = self._chat(system, user, max_tokens=400)
        return self._verify_placeholders(dutch, result)

    def _verify_placeholders(self, source: str, result: GptResult) -> GptResult:
        """A response that dropped/altered a model placeholder is a failure."""
        if not result.ok or result.text is None:
            return result
        src_ph = set(_PLACEHOLDER_RE.findall(source))
        out_ph = set(_PLACEHOLDER_RE.findall(result.text))
        if src_ph != out_ph:
            return GptResult(ok=False, error="placeholder_mismatch", tokens=result.tokens)
        return result


_instance: NLGptClient | None = None


def get_gpt_client() -> NLGptClient:
    global _instance
    if _instance is None:
        _instance = NLGptClient()
    return _instance
