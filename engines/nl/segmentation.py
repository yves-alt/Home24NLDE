"""Cell segmentation.

Splits a cell into independently-translatable segments on ``<br>`` boundaries
(and recognizes ``Label: value`` structure within a segment) so each piece can
be translated, validated and reassembled without corrupting the layout. The
``<br>`` separators are preserved verbatim.
"""

import re
from dataclasses import dataclass

_BR_RE = re.compile(r"(<br\s*/?>)", re.IGNORECASE)
_LABEL_RE = re.compile(r"^(\s*)([^:<>]{1,40}?)(\s*:\s*)(.*)$", re.DOTALL)


@dataclass
class Part:
    kind: str   # "text" | "sep"
    text: str


def split(text: str) -> list[Part]:
    """Split into alternating text / <br> separator parts."""
    if not text:
        return [Part("text", text)]
    pieces = _BR_RE.split(text)
    parts: list[Part] = []
    for p in pieces:
        if p == "":
            continue
        parts.append(Part("sep", p) if _BR_RE.fullmatch(p) else Part("text", p))
    return parts or [Part("text", text)]


def join(parts: list[Part]) -> str:
    return "".join(p.text for p in parts)


def label_value(segment: str) -> tuple[str | None, str, str, str]:
    """Split a "Label: value" segment.

    Returns (label, sep, value, leading_ws). label is None when there is no
    leading label. Reassemble with: leading_ws + label + sep + value.
    """
    m = _LABEL_RE.match(segment)
    if not m:
        return None, "", segment, ""
    leading, label, sep, value = m.group(1), m.group(2), m.group(3), m.group(4)
    return label, sep, value, leading


def map_text_segments(text: str, fn) -> str:
    """Apply `fn` to each text segment, preserving <br> separators."""
    parts = split(text)
    for p in parts:
        if p.kind == "text":
            p.text = fn(p.text)
    return join(parts)


_HAS_BR = _BR_RE


def has_structure(text: str) -> bool:
    """True if the cell has <br> separators or labeled segments worth splitting."""
    if not text:
        return False
    if _HAS_BR.search(text):
        return True
    label, _, _, _ = label_value(text)
    return label is not None
