import re

FORBIDDEN_ENDINGS = [
    "met", "keramische", "schuine", "houten", "verstelbare",
    "van", "in", "op", "voor", "bij", "met een", "een",
    "en", "of", "maar",
]

OPTIONAL_WORDS = [
    "premium", "exclusief", "luxe", "special", "edition",
    "deluxe", "plus", "pro", "lite", "basic",
]

MAX_NAME_LENGTH = 60


class ProductNameOptimizer:

    def optimize(self, name: str, max_length: int = MAX_NAME_LENGTH) -> tuple[str, list[str]]:
        if not name:
            return name, []

        actions = []
        result = name.strip()

        result, fixed = self._fix_trailing_prepositions(result)
        if fixed:
            actions.append(f"Removed trailing preposition: {fixed}")

        if len(result) > max_length:
            result, removed = self._trim_optional_words(result, max_length)
            if removed:
                actions.append(f"Removed optional words: {', '.join(removed)}")

        result, fixed = self._fix_trailing_prepositions(result)
        if fixed and not any("trailing" in a for a in actions):
            actions.append(f"Removed trailing preposition after trim: {fixed}")

        return result, actions

    def _fix_trailing_prepositions(self, name: str) -> tuple[str, str | None]:
        words = name.strip().split()
        if not words:
            return name, None

        for forbidden in sorted(FORBIDDEN_ENDINGS, key=len, reverse=True):
            forbidden_words = forbidden.split()
            if len(words) >= len(forbidden_words):
                tail = words[-len(forbidden_words):]
                if [w.lower() for w in tail] == forbidden_words:
                    removed = " ".join(tail)
                    remaining = " ".join(words[:-len(forbidden_words)]).strip()
                    if remaining:
                        return remaining, removed

        return name, None

    def _trim_optional_words(self, name: str, max_length: int) -> tuple[str, list[str]]:
        removed = []
        result = name

        for word in OPTIONAL_WORDS:
            if len(result) <= max_length:
                break
            pattern = re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
            new = pattern.sub("", result).strip()
            new = re.sub(r"\s+", " ", new)
            if new != result:
                removed.append(word)
                result = new

        return result, removed

    def validate(self, name: str) -> list[str]:
        issues = []
        words = name.strip().split()

        if not words:
            issues.append("Empty name")
            return issues

        last_word = words[-1].lower()
        for forbidden in FORBIDDEN_ENDINGS:
            forbidden_words = forbidden.split()
            if len(words) >= len(forbidden_words):
                tail = [w.lower() for w in words[-len(forbidden_words):]]
                if tail == forbidden_words:
                    issues.append(f"Name ends with forbidden word(s): '{forbidden}'")

        if len(name) > MAX_NAME_LENGTH + 10:
            issues.append(f"Name is very long ({len(name)} chars)")

        return issues


_instance: ProductNameOptimizer | None = None


def get_name_optimizer() -> ProductNameOptimizer:
    global _instance
    if _instance is None:
        _instance = ProductNameOptimizer()
    return _instance
