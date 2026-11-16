"""Finding words in the text of a book.

A chapter's text is all text below <body>, one string, exactly as the
reader's frame script sees it in body.textContent. Places in it are given
in UTF-16 code units, as JavaScript counts. A paragraph is the text between
two block boundaries, so text loose in <body> or a <section> is found too.
"""

import bisect
import re
import unicodedata

from .errors import EpubError
from .package import read_package
from .pages import PageFinder, page_numbers
from .paths import local_path
from .xmlutil import parse_xml

_XHTML = "{http://www.w3.org/1999/xhtml}"
_BLOCKS = {"address", "article", "aside", "blockquote", "body", "caption", "dd", "div", "dl",
           "dt", "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6",
           "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section", "table", "td",
           "th", "tr", "ul"}
_ASTRAL = re.compile("[\U00010000-\U0010FFFF]")
_SPACES = re.compile(r"\s+")

LIMIT = 200
# Characters of context shown before the first match, and in all.
_BEFORE = 50
_SNIPPET = 180
# Characters of a sentence or page shown in the history, and marked at most
# when going to a page from it.
_LINE = 100
_MARK = 40


# Distinct characters kept folded; a book using every code point must not
# fill the memory for as long as the app runs.
_MAX_FOLDED = 20000


class _Folding(dict):
    """str.translate table: each character folded, worked out on first use."""

    def __missing__(self, code):
        folded = []
        for c in unicodedata.normalize("NFKD", chr(code)):
            if unicodedata.combining(c):
                continue
            for d in c.casefold():
                if d.isalnum():
                    folded.append(d)
                elif unicodedata.category(d) != "Cf":
                    folded.append(" ")
        value = "".join(folded)
        if len(self) < _MAX_FOLDED:
            self[code] = value
        return value


_FOLDING = _Folding()


def fold(text):
    """text for comparing: without accents, lower case, ß as ss; anything
    but letters and digits is a space, except invisible characters such as
    the soft hyphen, which go."""
    return text.translate(_FOLDING)


def _folded_with_places(text):
    """fold(text), and for each of its characters the index in text."""
    parts = []
    places = []
    for i, c in enumerate(text):
        f = _FOLDING[ord(c)]
        parts.append(f)
        places.extend([i] * len(f))
    return "".join(parts), places


class Chapter(object):
    """The text of one chapter: text, paragraphs as (start, end) in text,
    and where the text of each element id starts and ends."""

    def __init__(self, text="", paragraphs=(), ids=None, ends=None):
        self.text = text
        self.paragraphs = list(paragraphs)
        self.folded = [fold(text[a:b]) for a, b in self.paragraphs]
        self.ids = ids or {}
        self.ends = ends or {}
        # Characters beyond the BMP count twice in UTF-16.
        self._astral = [m.start() for m in _ASTRAL.finditer(text)]

    def utf16(self, index):
        """index in text as UTF-16 code units."""
        return index + bisect.bisect_left(self._astral, index)

    def index(self, units):
        """The index in text at units UTF-16 code units; inside a character
        beyond the BMP, its start."""
        index = units
        for before, astral in enumerate(self._astral):
            if astral + before >= units:
                break
            index = max(astral, units - before - 1)
        return index


def read_chapter(root, path):
    """The Chapter of the XHTML file path; an unreadable file is empty."""
    try:
        doc = parse_xml(local_path(root, path), html_entities=True)
    except (EpubError, OSError):
        return Chapter()
    # Some books leave out the XHTML namespace.
    body = doc.find(_XHTML + "body")
    if body is None:
        body = doc.find("body")
    return chapter_of(body if body is not None else doc)


def chapter_of(body):
    """The Chapter of the element body. Walks the tree without recursion: a
    book may nest elements deeper than Python's stack allows."""
    pieces = []
    bounds = [0]
    ids = {}
    ends = {}
    # The element that gave each id its start; a later one with the same id,
    # even nested inside it, must not end it.
    owners = {}
    pos = 0
    # Each entry: element, and whether its children are done.
    stack = [(body, False)]
    while stack:
        element, done = stack.pop()
        block = _local_name(element.tag) in _BLOCKS
        if done:
            if block:
                bounds.append(pos)
            ident = element.get("id")
            if ident and owners.get(ident) is element:
                ends[ident] = pos
            if element is not body and element.tail:
                pieces.append(element.tail)
                pos += len(element.tail)
            continue
        if block:
            bounds.append(pos)
        ident = element.get("id")
        if ident and ident not in ids:
            ids[ident] = pos
            owners[ident] = element
        if element.text:
            pieces.append(element.text)
            pos += len(element.text)
        stack.append((element, True))
        for child in reversed(list(element)):
            stack.append((child, False))
    text = "".join(pieces)
    bounds = sorted(set(bounds + [pos]))
    paragraphs = [(a, b) for a, b in zip(bounds, bounds[1:]) if text[a:b].strip()]
    return Chapter(text, paragraphs, ids, ends)


def _local_name(tag):
    """The name of an XHTML element, also without namespace; "" for
    elements of other namespaces (SVG, MathML)."""
    if not isinstance(tag, str):
        return ""
    if tag.startswith(_XHTML):
        return tag[len(_XHTML):]
    return "" if tag.startswith("{") else tag


class BookIndex(object):
    """The text of every chapter of the book unpacked at root, for searching."""

    def __init__(self, root):
        self.root = root
        book = read_package(root)
        self.chapters = [read_chapter(root, item.path) for item in book.spine]
        self.pages = PageFinder(page_numbers([item.path for item in book.spine], book.pages),
                                self.chapters, [item.linear for item in book.spine], book.language)
        spine_index = {}
        for index, item in enumerate(book.spine):
            spine_index.setdefault(item.path, index)
        # Headings of the table of contents by place; the last one at or
        # before a place names its chapter.
        marks = []
        for order, entry in enumerate(book.toc):
            spine = spine_index.get(entry.path, -1)
            if spine < 0 or not entry.title:
                continue
            offset = self.chapters[spine].ids.get(entry.fragment, 0) if entry.fragment else 0
            marks.append(((spine, offset), order, entry.title))
        marks.sort()
        self._marks = [m[0] for m in marks]
        self._titles = [m[2] for m in marks]

    def title_at(self, spine, offset):
        """The heading of the table of contents that the place falls under,
        or ""."""
        i = bisect.bisect_right(self._marks, (spine, offset)) - 1
        return self._titles[i] if i >= 0 else ""

    def page_labels(self, places):
        """The printed page at each place, for lists: {estimated, labels},
        a label being "" where there is none. A place is {spine, offset}
        (UTF-16, as bookmarks) or {spine, fragment} (an element, as the
        contents); anything else has no page."""
        labels = []
        for place in places:
            spine = place.get("spine") if isinstance(place, dict) else None
            if isinstance(spine, float) and spine.is_integer():
                spine = int(spine)
            if not isinstance(spine, int) or isinstance(spine, bool) or not 0 <= spine < len(self.chapters):
                labels.append("")
                continue
            chapter = self.chapters[spine]
            fragment = place.get("fragment")
            offset = place.get("offset")
            if isinstance(fragment, str):
                labels.append(self.pages.label(spine, chapter.ids.get(fragment, 0)))
            elif isinstance(offset, (int, float)) and not isinstance(offset, bool) and offset >= 0:
                labels.append(self.pages.label(spine, min(chapter.index(int(offset)), len(chapter.text))))
            else:
                labels.append("")
        return {"estimated": self.pages.estimated, "labels": labels}

    def flip_stops(self):
        """{estimated, stops} for the bar of the page flip view, see
        pages.PageFinder.stops."""
        return {"estimated": self.pages.estimated, "stops": self.pages.stops(self.title_at)}

    def sentence(self, spine, ident):
        """The element ident of chapter spine as a place to go to, like a
        hit: {spine, chapter, offset, length, text, line}, line being the
        start of its text to show. offset is -1 if there is no such element
        or it holds no text (the book changed since)."""
        chapter = self.chapters[spine] if 0 <= spine < len(self.chapters) else Chapter()
        start = chapter.ids.get(ident, -1)
        end = chapter.ends.get(ident, start)
        if start < 0 or end <= start:
            return {"spine": spine, "chapter": self.title_at(spine, 0),
                    "offset": -1, "length": 0, "text": "", "line": ""}
        text = chapter.text[start:end]
        return {"spine": spine,
                "chapter": self.title_at(spine, start),
                "offset": chapter.utf16(start),
                "length": chapter.utf16(end) - chapter.utf16(start),
                "text": text,
                "line": _line(text)}

    def text_at(self, spine, offset):
        """The page of chapter spine beginning offset UTF-16 code units into
        its text as a place to go to, like sentence(): its first words to
        mark (up to _MARK characters, not past the paragraph) and line, the
        text from there to show. Leading whitespace is skipped. offset is -1
        if the place is not in the chapter (the book changed since)."""
        chapter = self.chapters[spine] if 0 <= spine < len(self.chapters) else Chapter()
        start = chapter.index(offset) if offset >= 0 else len(chapter.text)
        while start < len(chapter.text) and chapter.text[start].isspace():
            start += 1
        if start >= len(chapter.text):
            return {"spine": spine, "chapter": self.title_at(spine, 0),
                    "offset": -1, "length": 0, "text": "", "line": ""}
        i = bisect.bisect_right(chapter.paragraphs, (start, len(chapter.text) + 1)) - 1
        end = chapter.paragraphs[i][1] if i >= 0 and chapter.paragraphs[i][1] > start else len(chapter.text)
        # Cut after a word only if the paragraph goes on: the next one may
        # follow without a space.
        if start + _MARK < end:
            end = start + _MARK
            if not chapter.text[end].isspace():
                space = max((m.start() for m in _SPACES.finditer(chapter.text, start, end)), default=-1)
                if space > start:
                    end = space
        text = chapter.text[start:end].rstrip()
        return {"spine": spine,
                "chapter": self.title_at(spine, start),
                "offset": chapter.utf16(start),
                "length": chapter.utf16(start + len(text)) - chapter.utf16(start),
                "text": text,
                "line": _line(chapter.text[start:start + 3 * _LINE])}

    def place(self, here):
        """here {spine, id, offset, fraction} as (spine, offset in text), or
        None; the first of id, offset (UTF-16) and fraction that is given."""
        if not isinstance(here, dict):
            return None
        spine = here.get("spine")
        # A number from QML may come as a float.
        if isinstance(spine, float) and spine.is_integer():
            spine = int(spine)
        if not isinstance(spine, int) or isinstance(spine, bool):
            return None
        if not 0 <= spine < len(self.chapters):
            return None
        chapter = self.chapters[spine]
        ident = here.get("id")
        if ident and ident in chapter.ids:
            return spine, chapter.ids[ident]
        offset = here.get("offset")
        if isinstance(offset, float) and offset.is_integer():
            offset = int(offset)
        if isinstance(offset, int) and not isinstance(offset, bool) and offset >= 0:
            return spine, min(chapter.index(offset), len(chapter.text))
        fraction = here.get("fraction")
        fraction = fraction if isinstance(fraction, (int, float)) and 0 <= fraction <= 1 else 0
        return spine, int(fraction * len(chapter.text))

    def search(self, query, here=None, limit=LIMIT):
        """The paragraphs holding every word of query, in reading order.

        Returns {hits, total, before, pagesEstimated}: at most limit hits,
        the number of all hits, how many of them lie before the place here
        (see place; -1 if here is not a place in the book), and whether the
        hits' pages are estimated.
        A hit is {spine, chapter, page, offset, length, text, snippet}: page
        is the printed page ("" if none), offset and length (UTF-16) give
        the first match in the chapter's text, text is that match, snippet a
        list of {text, match} to show.
        """
        words = fold(query).split()
        hits = []
        total = 0
        before = 0
        place = self.place(here)
        if not words:
            return {"hits": hits, "total": 0, "before": 0 if place is not None else -1,
                    "pagesEstimated": self.pages.estimated}
        for spine, chapter in enumerate(self.chapters):
            for (start, end), folded in zip(chapter.paragraphs, chapter.folded):
                if not all(word in folded for word in words):
                    continue
                total += 1
                if place is not None and self._before(spine, start, end, folded, words, place):
                    before += 1
                if len(hits) < limit:
                    hits.append(self._hit(spine, chapter, start, end, words))
        return {"hits": hits, "total": total, "before": before if place is not None else -1,
                "pagesEstimated": self.pages.estimated}

    def _before(self, spine, start, end, folded, words, place):
        """Whether the first match in the paragraph lies before place."""
        if (spine, end) <= place:
            return True
        if (spine, start) >= place:
            return False
        # The place is inside the paragraph: folded text may be longer or
        # shorter than the text (ß → ss), so map the match back.
        first = min(folded.find(word) for word in words)
        places = _folded_with_places(self.chapters[spine].text[start:end])[1]
        return start + places[first] < place[1]

    def _hit(self, spine, chapter, start, end, words):
        paragraph = chapter.text[start:end]
        folded, places = _folded_with_places(paragraph)
        matches = []
        for word in words:
            i = folded.find(word)
            while i >= 0:
                end = places[i + len(word) - 1] + 1
                # Not between a letter and its accent in decomposed text.
                while end < len(paragraph) and not _FOLDING[ord(paragraph[end])]:
                    end += 1
                matches.append((places[i], end))
                i = folded.find(word, i + len(word))
        matches = _merged(matches)
        a, b = matches[0]
        return {"spine": spine,
                "chapter": self.title_at(spine, start + a),
                "page": self.pages.label(spine, start + a),
                "offset": chapter.utf16(start + a),
                "length": chapter.utf16(start + b) - chapter.utf16(start + a),
                "text": paragraph[a:b],
                "snippet": _snippet(paragraph, matches)}


def _line(text):
    """text on one line, cut after a word if longer than _LINE."""
    text = _SPACES.sub(" ", text).strip()
    if len(text) <= _LINE:
        return text
    cut = text.rfind(" ", 0, _LINE + 1)
    return text[:cut if cut > 0 else _LINE].rstrip() + "…"


def _merged(ranges):
    ranges.sort()
    merged = []
    for a, b in ranges:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def _snippet(paragraph, matches):
    """Some context around the first match, as [{text, match}], with
    whitespace as single spaces and "…" where text was left out."""
    first, first_end = matches[0]
    start = max(0, first - _BEFORE)
    if start > 0 and not paragraph[start - 1].isspace():
        # Not in the middle of a word.
        space = _SPACES.search(paragraph, start, first)
        if space:
            start = space.end()
    end = min(len(paragraph), max(start + _SNIPPET, first_end))
    if end < len(paragraph) and not paragraph[end].isspace():
        space = max((m.start() for m in _SPACES.finditer(paragraph, first_end, end)), default=-1)
        if space >= 0:
            end = space
    parts = []
    pos = start
    for a, b in matches:
        if b <= start or a >= end:
            continue
        a, b = max(a, start), min(b, end)
        if a > pos:
            parts.append({"text": paragraph[pos:a], "match": False})
        parts.append({"text": paragraph[a:b], "match": True})
        pos = b
    if pos < end:
        parts.append({"text": paragraph[pos:end], "match": False})
    for part in parts:
        part["text"] = _SPACES.sub(" ", part["text"])
    parts[0]["text"] = parts[0]["text"].lstrip()
    parts[-1]["text"] = parts[-1]["text"].rstrip()
    if start > 0:
        parts.insert(0, {"text": "…", "match": False})
    if end < len(paragraph):
        parts.append({"text": "…", "match": False})
    return [part for part in parts if part["text"]]
