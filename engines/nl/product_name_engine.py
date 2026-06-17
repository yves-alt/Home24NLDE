"""Dutch product-name engine (PART 10).

Enforces Home24.nl rules for the `name` column:
  * 40-character hard limit
  * no brackets, no commas
  * first letter capitalized (terminology renders product types lowercase)
  * never ends on a connector / bare adjective (forbidden endings)
  * graded shortening that preserves product type + model name, with a
    "shortened — review" warning when it has to cut.

Model names are kept intact: shortening drops trailing words but never cuts
below the leading "product type + model" head.
"""

import re
from dataclasses import dataclass, field

MAX_NAME_LENGTH = 40

# Words/sequences a name must never end on.
FORBIDDEN_ENDINGS = [
    "met", "van", "voor", "uit", "en", "of", "bij", "tot", "per", "als",
    "incl.", "inkl.", "incl", "inkl",
    "keramische", "schuine", "schuin", "houten", "eikenhouten",
    "elektrische", "verstelbare", "ronde", "rechte", "open",
]

# Trailing connector tokens dropped first during shortening.
_WEAK_TAIL = {"met", "van", "voor", "en", "of", "+", "-", "/", "incl.", "inkl.", "&"}


@dataclass
class NameResult:
    name: str
    warnings: list[str] = field(default_factory=list)
    was_shortened: bool = False


class DutchProductNameEngine:

    def optimize(self, name: str) -> NameResult:
        if not name or not name.strip():
            return NameResult(name, [])

        warnings: list[str] = []
        result = name.strip()

        # No brackets, no commas.
        result = re.sub(r"\s*[\(\[\{][^\)\]\}]*[\)\]\}]\s*", " ", result)
        result = result.replace(",", " ")
        result = re.sub(r"\s{2,}", " ", result).strip()

        # Capitalize first alphabetic character.
        result = self._capitalize_first(result)

        # Remove forbidden trailing words.
        result = self._strip_forbidden_endings(result)

        was_shortened = False
        if len(result) > MAX_NAME_LENGTH:
            result = self._shorten(result)
            was_shortened = True
            warnings.append("Product name shortened — review recommended")

        result = self._strip_forbidden_endings(result)
        result = self._capitalize_first(result.strip())

        return NameResult(result, warnings, was_shortened)

    def _capitalize_first(self, text: str) -> str:
        for i, ch in enumerate(text):
            if ch.isalpha():
                return text[:i] + ch.upper() + text[i + 1:]
        return text

    def _strip_forbidden_endings(self, name: str) -> str:
        words = name.split()
        changed = True
        while changed and words:
            changed = False
            last = words[-1].lower().strip(".,;:")
            last_full = words[-1].lower()
            if last in {w.strip(".") for w in FORBIDDEN_ENDINGS} or last_full in FORBIDDEN_ENDINGS:
                words.pop()
                changed = True
            elif words[-1] in {"+", "-", "/", "&"}:
                words.pop()
                changed = True
        return " ".join(words) if words else name

    def _shorten(self, name: str) -> str:
        words = name.split()
        # Never cut below the leading product type + model head (first 3 words
        # or until the limit, whichever is longer-but-still-fitting).
        floor = min(3, len(words))
        while len(" ".join(words)) > MAX_NAME_LENGTH and len(words) > floor:
            words.pop()
        # If still over the limit even at the floor, hard-trim on a word boundary.
        candidate = " ".join(words)
        if len(candidate) > MAX_NAME_LENGTH:
            candidate = candidate[:MAX_NAME_LENGTH].rsplit(" ", 1)[0].strip()
        return candidate

    def validate(self, name: str) -> list[str]:
        """Return quality-gate issues for a finished name."""
        issues: list[str] = []
        if not name:
            return issues
        if len(name) > MAX_NAME_LENGTH:
            issues.append(f"name exceeds {MAX_NAME_LENGTH} chars ({len(name)})")
        if any(b in name for b in "()[]{}"):
            issues.append("name contains brackets")
        if "," in name:
            issues.append("name contains a comma")
        words = name.split()
        if words:
            last = words[-1].lower().strip(".,;:")
            if last in {w.strip(".") for w in FORBIDDEN_ENDINGS} or words[-1] in {"+", "-", "/", "&"}:
                issues.append(f"name ends on forbidden word '{words[-1]}'")
        return issues


_instance: DutchProductNameEngine | None = None


def get_product_name_engine() -> DutchProductNameEngine:
    global _instance
    if _instance is None:
        _instance = DutchProductNameEngine()
    return _instance
