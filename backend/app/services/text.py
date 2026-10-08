"""
Text normalisation shared by indexing and search.

Accents are folded here, in Python, rather than with PostgreSQL's `unaccent`
extension: the embedded PostgreSQL used for development doesn't ship it, and
doing it in one place guarantees that what is indexed and what is searched are
normalised the same way ("información" finds "informacion" and vice versa).

Folding maps one character to one character, so offsets in folded text are
offsets in the original: that is what lets snippets highlight the original.
"""

import re
import unicodedata
from dataclasses import dataclass, field


def _fold_table() -> dict[int, str]:
    table = {}
    for cp in range(0xC0, 0x250):  # Latin-1 Supplement and Latin Extended-A/B
        base = "".join(c for c in unicodedata.normalize("NFKD", chr(cp)) if not unicodedata.combining(c))
        if len(base) == 1 and base != chr(cp):
            table[cp] = base
    table[0x130] = "I"  # İ lower-cases to two characters; keep it one
    return table


_FOLD = _fold_table()
_NON_WORD = re.compile(r"[\W_]+")


def fold(s: str) -> str:
    """Lower-case and strip accents, keeping the length (ñ -> n, É -> e)."""
    return s.translate(_FOLD).lower()


def words(s: str) -> str:
    """
    Folded words of a file name or path, separated by spaces. PostgreSQL's parser
    would read "budget.xlsx" as one host name and "a_b" as one word; names are
    searched by their parts.
    """
    return _NON_WORD.sub(" ", fold(s)).strip()


def clean_content(s: str, max_chars: int) -> str:
    """Text as stored: no NUL characters (PostgreSQL rejects them), collapsed blank runs."""
    s = s.replace("\x00", "")
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()[:max_chars]


# ── Queries ───────────────────────────────────────────────────────────────────

@dataclass
class ParsedQuery:
    text: str  # for websearch_to_tsquery: words, "phrases", -exclusions, or
    terms: list[str] = field(default_factory=list)  # positive words, for highlighting
    excluded: list[str] = field(default_factory=list)


def parse_query(q: str) -> ParsedQuery:
    q = fold(q)
    # Keep what websearch syntax understands (quotes, leading minus); everything else
    # splits words, as it did when the names were indexed ("INF-2023.pdf" -> inf 2023 pdf).
    q = re.sub(r"(?<=\w)[^\w\s\"]+(?=\w)|_", " ", q)
    q = re.sub(r"[^\w\s\"-]", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    terms, excluded = [], []
    for token in re.findall(r"-?\w+", q):
        if token.startswith("-"):
            excluded.append(token[1:])
        elif token != "or":
            terms.append(token)
    return ParsedQuery(text=q, terms=terms, excluded=excluded)


# ── Snippets ──────────────────────────────────────────────────────────────────

def _stem(term: str) -> str:
    # Crude, but enough to highlight plurals and verb forms the search matched.
    return term if len(term) <= 4 else term[: max(4, len(term) - 2)]


def snippet(text: str, terms: list[str], width: int = 240) -> list[dict]:
    """
    A fragment of `text` around the first match, as segments
    [{"text": ..., "hit": bool}]: the UI renders hits without ever parsing HTML.
    """
    if not text:
        return []
    folded = fold(text)
    if len(folded) != len(text):  # an unusual character changed length: no highlights
        folded = ""
    stems = sorted({_stem(t) for t in terms if t}, key=len, reverse=True)
    pattern = re.compile(r"\b(?:" + "|".join(map(re.escape, stems)) + r")\w*") if stems and folded else None
    hits = [m.span() for m in pattern.finditer(folded)] if pattern else []

    if hits:
        center = hits[0][0]
        start = max(0, center - width // 3)
        end = min(len(text), start + width)
    else:
        start, end = 0, min(len(text), width)
    # Don't cut words in half.
    if start > 0:
        space = text.rfind(" ", 0, start)
        start = space + 1 if space >= 0 and start - space < 30 else start
    if end < len(text):
        space = text.find(" ", end)
        end = space if 0 <= space and space - end < 30 else end

    segments: list[dict] = []
    if start > 0:
        segments.append({"text": "…", "hit": False})
    pos = start
    for a, b in hits:
        if a < start or b > end:
            continue
        if a > pos:
            segments.append({"text": text[pos:a], "hit": False})
        segments.append({"text": text[a:b], "hit": True})
        pos = b
    if pos < end:
        segments.append({"text": text[pos:end], "hit": False})
    if end < len(text):
        segments.append({"text": "…", "hit": False})
    for s in segments:
        s["text"] = re.sub(r"\s+", " ", s["text"])
    return segments
