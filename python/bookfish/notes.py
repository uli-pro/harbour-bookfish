"""Following a link in a book: a jump, or a note shown on its own page.

Few books mark their notes (epub:type="noteref"); most link a number to it.
So a link counts as a note by its form: a short mark ("12", "[3]", "*",
"a", "iv") inside running text, leading to a place that is no chapter.
Every other link (a chapter in the contents, "see chapter 3", a note's
number leading back to the text) is a jump. The rules were measured on a
library of some 590 books (18 000 notes); see the README.

Only the XHTML namespace counts; the text comes as Qt's StyledText with
nothing but <i>, <b> and <br>, all else escaped.
"""

import html
import re

from .errors import EpubError
from .paths import local_path, resolve
from .xmlutil import parse_xml

_XHTML = "{http://www.w3.org/1999/xhtml}"

# A comma or full stop may belong to the link: "4," "5," "6" (Duhigg).
_SHORT = re.compile(r"(?:[\[\(]?[0-9]{1,3}[a-z]?[\]\)]?|[\[\(]?[*†‡§¶]{1,3}[\]\)]?"
                    r"|[a-zA-Z]|[ivxlcIVXLC]{1,4})[,;.]?")
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_BLOCKS = {"address", "article", "aside", "blockquote", "body", "dd", "div", "dl", "dt",
           "figcaption", "figure", "footer", "header", "li", "main", "nav", "ol", "p",
           "pre", "section", "table", "tbody", "td", "tfoot", "th", "thead", "tr",
           "ul"} | _HEADINGS
_ITALIC = {"i", "em", "cite", "dfn", "var"}
_BOLD = {"b", "strong"}
_SKIPPED = {"script", "style", "head", "title"}

# Neighbours shown around a note, and the most text of a note alone.
NEIGHBOURS = 100
MAX_CHARS = 10000


def is_short(text):
    """Whether a link's text looks like the mark of a note."""
    return bool(_SHORT.fullmatch(text.strip()))


def follow_link(root, spine, toc, chapter, href, ordinal):
    """What a long press on a link does.

    chapter is the path of the chapter shown and href the link's address
    as written in it; ordinal tells which of the links with that address
    it is (0 for the first), as several may share one. spine is the list
    of chapter paths, toc the places of the contents as (path, fragment).

    Returns {"jump": spine index, "id": fragment} to go there,
    {"paragraphs": [StyledText], "first": i, "last": j} for a note (the
    note itself is first..last, the rest its neighbours), or {} if the
    link leads nowhere in the book.
    """
    try:
        target = resolve(chapter, href)
    except EpubError:
        return {}
    if target is None:
        return {}
    path, fragment = target
    # "#" and "" lead nowhere; books use them for links that do nothing.
    if path == chapter and not fragment:
        return {}
    index = spine.index(path) if path in spine else -1
    jump = {"jump": index, "id": fragment} if index >= 0 else {}
    source = _body(root, chapter)
    link = _link(source, href, ordinal) if source is not None else None
    if link is None or not is_short(_text(link)) or _leads(source, link) \
            or _list_page(source) or (path, fragment) in toc or not fragment:
        return jump
    doc = _doc(root, path)
    if doc is None:
        return jump
    found = _note(_body_of(doc), fragment, path != chapter, _class_styles(root, path, doc))
    if found is None:
        return jump
    if found:
        # Checked by is_short: a few digits, letters or signs.
        found["mark"] = _text(link).strip().rstrip(",;.")
    return found


def _body(root, path):
    doc = _doc(root, path)
    return _body_of(doc) if doc is not None else None


def _doc(root, path):
    try:
        return parse_xml(local_path(root, path), html_entities=True)
    except (EpubError, OSError, ValueError):
        return None


def _body_of(doc):
    body = doc.find(_XHTML + "body")
    if body is None:
        body = doc.find("body")
    return body if body is not None else doc


_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_CSS_CLASS = re.compile(r"(?:[a-zA-Z][\w-]*)?\.([\w-]+)")
_CSS_BOLD = re.compile(r"font-weight\s*:\s*(bold(?:er)?|[6-9]00)\b|\bfont\s*:[^;]*\bbold\b", re.I)
_CSS_ITALIC = re.compile(r"font-style\s*:\s*(italic|oblique)\b|\bfont\s*:[^;]*\b(italic|oblique)\b", re.I)
MAX_CSS_SIZE = 2 * 1024 * 1024


def _class_styles(root, path, doc):
    """{class: (bold, italic)} from the simple rules (".name", "span.name")
    of the style sheets of the file at path: many books set bold and italic
    by class, not with <b> and <i>."""
    sheets = []
    head = doc.find(_XHTML + "head")
    if head is None:
        head = doc.find("head")
    for element in (head if head is not None else []):
        name = _local(element.tag)
        if name == "style" and element.text:
            sheets.append(element.text)
        elif name == "link" and "stylesheet" in (element.get("rel") or "").lower():
            try:
                target = resolve(path, element.get("href") or "")
            except EpubError:
                continue
            if target is None:
                continue
            try:
                with open(local_path(root, target[0]), "rb") as f:
                    sheets.append(f.read(MAX_CSS_SIZE).decode("utf-8", "replace"))
            except (OSError, EpubError, ValueError):
                continue
    styles = {}
    for sheet in sheets:
        for selectors, declarations in _CSS_RULE.findall(_CSS_COMMENT.sub("", sheet)):
            bold = bool(_CSS_BOLD.search(declarations))
            italic = bool(_CSS_ITALIC.search(declarations))
            if not bold and not italic:
                continue
            for selector in selectors.split(","):
                match = _CSS_CLASS.fullmatch(selector.strip())
                if match:
                    old = styles.get(match.group(1), (False, False))
                    styles[match.group(1)] = (old[0] or bold, old[1] or italic)
    return styles


def _local(tag):
    if not isinstance(tag, str):
        return ""
    if tag.startswith(_XHTML):
        return tag[len(_XHTML):]
    return "" if tag.startswith("{") else tag


def _text(element):
    return "".join(element.itertext())


def _link(body, href, ordinal):
    count = 0
    for element in body.iter():
        if _local(element.tag) == "a" and element.get("href") == href:
            if count == ordinal:
                return element
            count += 1
    return None


def _parents(body):
    parents = {}
    stack = [body]
    while stack:
        element = stack.pop()
        for child in element:
            parents[child] = element
            stack.append(child)
    return parents


def _block_of(element, parents):
    while element is not None and _local(element.tag) not in _BLOCKS:
        element = parents.get(element)
    return element


def _text_before(container, target):
    """Whether visible text comes before target inside container. Walks
    without recursion: books may nest deeper than Python's stack."""
    stack = [(container, False)]
    while stack:
        element, done = stack.pop()
        if done:
            if element is not container and element.tail and element.tail.strip():
                return True
            continue
        if element is target:
            return False
        if element.text and element.text.strip():
            return True
        stack.append((element, True))
        for child in reversed(list(element)):
            stack.append((child, False))
    return False


def _leads(body, link):
    """A number at the start of its paragraph or alone in it: a chapter in
    a list of contents, or a note's number leading back to the text."""
    block = _block_of(link, _parents(body))
    return block is not None and not _text_before(block, link)


def _list_page(body):
    """A page mostly of links: contents, an index."""
    links = [a for a in body.iter() if _local(a.tag) == "a" and a.get("href")]
    if len(links) < 5:
        return False
    def length(element):
        return len(re.sub(r"\s+", "", _text(element)))
    return sum(length(a) for a in links) > 0.5 * length(body)


def _units(body):
    """The innermost blocks in reading order: paragraphs, headings, and
    table rows of plain cells (a note's number and text side by side)."""
    units = []
    stack = [body]
    while stack:
        element = stack.pop()
        name = _local(element.tag)
        if name in _BLOCKS and (not _has_block(element, ()) or
                                name == "tr" and not _has_block(element, ("td", "th"))):
            units.append(element)
            continue
        stack.extend(reversed(list(element)))
    return units


def _has_block(element, allowed):
    """Whether a block other than allowed lies inside element. Stops at the
    first: a book may nest blocks very deep."""
    return any(_local(e.tag) in _BLOCKS and _local(e.tag) not in allowed
               for e in element.iter() if e is not element)


def _note(body, fragment, neighbours, styles):
    target = next((e for e in body.iter() if e.get("id") == fragment), None)
    if target is None:
        return {}
    if _local(target.tag) in _HEADINGS or not _text_before(body, target):
        return None
    order = {}
    for position, element in enumerate(body.iter()):
        order[element] = position
    units = _units(body)
    last_inside = {}
    for unit in units:
        last_inside[unit] = max(order[e] for e in unit.iter())
    at = order[target]
    start = next((i for i, u in enumerate(units) if order[u] <= at <= last_inside[u]), None)
    if start is None:
        start = next((i for i, u in enumerate(units) if order[u] > at), None)
        if start is None:
            return {}
    unit = units[start]
    if _local(unit.tag) in _HEADINGS:
        return None
    # Inside a paragraph, after other text: a place in the text (an index
    # entry, a note's mark leading back), that paragraph alone.
    if order[unit] <= at and _text_before(unit, target):
        return _shown([unit], 0, 0, True, styles)
    stop = _end(body, target, unit)
    end = start
    if stop is None or order[stop] > last_inside[unit]:
        # On to the unit before the next note; to the end of the section
        # if nothing follows.
        while end + 1 < len(units) and _local(units[end + 1].tag) not in _HEADINGS \
                and (stop is None or last_inside[units[end + 1]] < order[stop]):
            end += 1
    if not neighbours:
        return _shown(units[start:end + 1], 0, end - start, True, styles)
    first = start
    while first > 0 and start - first < NEIGHBOURS \
            and _local(units[first - 1].tag) not in _HEADINGS:
        first -= 1
    last = end
    while last + 1 < len(units) and last - end < NEIGHBOURS \
            and _local(units[last + 1].tag) not in _HEADINGS:
        last += 1
    return _shown(units[first:last + 1], start - first, end - first, False, styles)


def _end(body, target, first):
    """The element where the note at target ends: the next note, a mark
    leading back, a heading; None if it runs to the end. first is the
    note's first paragraph: the one holding target, or the one after it
    when target is an anchor between paragraphs."""
    in_first = False
    # Past the first paragraph, what begins something else ends the note
    # even if the note had no text (a picture).
    left_first = False
    collected = False
    stack = [(body, False)]
    started = False
    while stack:
        element, done = stack.pop()
        name = _local(element.tag)
        if done:
            if element is first:
                in_first = False
                left_first = True
            if started and element.tail and element.tail.strip():
                collected = True
            continue
        if element is first:
            in_first = True
        if element is target:
            started = True
        elif started:
            ends = collected or left_first
            if ends and name in _HEADINGS:
                return element
            if ends and element.get("id") and (name in _BLOCKS or name == "a"):
                # An empty anchor inside the note's paragraph marks a
                # printed page; a term's explanation (dd) belongs to it.
                empty_anchor = name == "a" and not _text(element).strip()
                if not (empty_anchor and in_first) and not (
                        name == "dd" and first is not None and _local(first.tag) == "dt"):
                    return element
            if ends and name == "a" and not in_first:
                href = element.get("href") or ""
                if href and not re.match(r"[a-z]+:", href) and is_short(_text(element)):
                    return element
        if started and element.text and element.text.strip():
            collected = True
        stack.append((element, True))
        for child in reversed(list(element)):
            stack.append((child, False))
    return None


def _shown(units, first, last, alone, styles):
    """{paragraphs, first, last} without the empty paragraphs; {} if the
    note itself has no text. alone: a note without neighbours, cut after
    MAX_CHARS. Every paragraph is cut there too: one Label must not get a
    whole book."""
    styled = [_cut(_styled(u, styles), MAX_CHARS) for u in units]
    kept = [i for i, p in enumerate(styled) if p]
    if not any(first <= i <= last for i in kept):
        return {}
    paragraphs = [styled[i] for i in kept]
    new_first = sum(1 for i in kept if i < first)
    new_last = sum(1 for i in kept if i <= last) - 1
    if alone:
        total = 0
        for n, paragraph in enumerate(paragraphs):
            total += len(paragraph)
            if total > MAX_CHARS and n > 0:
                paragraphs = paragraphs[:n] + ["\u2026"]
                break
        new_first, new_last = 0, len(paragraphs) - 1
    return {"paragraphs": paragraphs, "first": new_first, "last": new_last}


_TOKEN = re.compile(r"<(/?)([ib]|br)>|&[#a-zA-Z0-9]+;|[^<&]")


def _cut(styled, limit):
    """StyledText cut after limit characters, its tags closed."""
    if len(styled) <= limit:
        return styled
    out = []
    count = 0
    open_tags = []
    for match in _TOKEN.finditer(styled):
        if match.group(2):
            if match.group(2) != "br":
                if match.group(1):
                    if open_tags and open_tags[-1] == match.group(2):
                        open_tags.pop()
                else:
                    open_tags.append(match.group(2))
        else:
            if count >= limit:
                out.append("\u2026")
                break
            count += 1
        out.append(match.group(0))
    out.extend("</%s>" % tag for tag in reversed(open_tags))
    return "".join(out)


def _styled(unit, styles):
    """The text of a block as StyledText: <i>, <b>, <br>; all else escaped.
    styles: bold and italic by class, see _class_styles."""
    out = []
    # Each entry: element, done, and whether it is inside italic and bold
    # (before it; when done, whether it opened them).
    stack = [(unit, False, False, False)]
    while stack:
        element, done, italic, bold = stack.pop()
        name = _local(element.tag)
        if done:
            # italic and bold say here what this element opened.
            if bold:
                out.append("</b>")
            if italic:
                out.append("</i>")
            # Cells of a row: side by side.
            if element is not unit and name in _BLOCKS:
                out.append(" ")
            if element is not unit and element.tail:
                out.append(_escape(element.tail))
            continue
        if name in _SKIPPED or (name == "" and element is not unit):
            if element.tail:
                out.append(_escape(element.tail))
            continue
        if name == "br":
            out.append("<br>")
        by_class = [styles.get(c, (False, False)) for c in (element.get("class") or "").split()]
        opens_italic = not italic and (name in _ITALIC or any(c[1] for c in by_class))
        opens_bold = not bold and (name in _BOLD or any(c[0] for c in by_class))
        if opens_italic:
            out.append("<i>")
        if opens_bold:
            out.append("<b>")
        if element.text:
            out.append(_escape(element.text))
        stack.append((element, True, opens_italic, opens_bold))
        for child in reversed(list(element)):
            stack.append((child, False, italic or opens_italic, bold or opens_bold))
    text = "".join(out)
    # Only ASCII white space: a no-break space keeps "p. 12" together.
    text = re.sub(r"[ \t\n\r\f]+", " ", text)
    text = re.sub(r" ?<br> ?", "<br>", text)
    text = re.sub(r"^(<br>)+|(<br>)+$", "", text.strip())
    return text if re.sub(r"<[^>]+>|[ \t\n\r\f]", "", text) else ""


def _escape(text):
    return html.escape(text, quote=False)
