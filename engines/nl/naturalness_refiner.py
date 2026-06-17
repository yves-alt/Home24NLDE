"""Dutch naturalness refiner (PART 12).

A GPT pass that makes a translated segment read like Home24.nl copy — natural,
commercial, concise. It is strictly conservative: if the refinement introduces
German residue or drops any data (numbers / colors / model names), it is
discarded and the original is kept. Refinement never reduces correctness.
"""

from engines.nl.gpt_client import get_gpt_client
from engines.nl.info_preservation import get_info_validator
from engines.nl.residue_gate import get_residue_gate

_INSTRUCTION = (
    "Herschrijf deze Nederlandse producttekst zodat hij vloeiend, natuurlijk en "
    "commercieel klinkt voor Home24.nl. Behoud ALLE feiten, cijfers, kleuren, "
    "modelnamen, placeholders en de <br>-structuur exact. Voeg niets toe en laat "
    "niets weg."
)


class DutchNaturalnessRefiner:
    def __init__(self):
        self._gpt = get_gpt_client()
        self._info = get_info_validator()
        self._residue = get_residue_gate()

    @property
    def available(self) -> bool:
        return self._gpt.available

    def refine(self, text: str, source: str, model_names=()) -> tuple[str, bool]:
        """Return (text, changed). Falls back to the input on any risk."""
        if not self.available or not text or not text.strip():
            return text, False
        result = self._gpt.refine(text, _INSTRUCTION)
        if not result.ok or not result.text:
            return text, False
        candidate = result.text
        if self._residue.scan(candidate):
            return text, False
        if not self._info.validate(source, candidate, model_names).ok:
            return text, False
        return candidate, candidate != text


_instance: DutchNaturalnessRefiner | None = None


def get_naturalness_refiner() -> DutchNaturalnessRefiner:
    global _instance
    if _instance is None:
        _instance = DutchNaturalnessRefiner()
    return _instance
