"""Page numbers of the printed book, from the EPUB's page list."""

import collections
import re

# One entry of the page list: where the page begins (path in the book and
# the id there, "" for the start of the file) and its name in the list.
PageTarget = collections.namedtuple("PageTarget", "path fragment name")

_ROMAN = re.compile(r"[ivxlcdm]+", re.IGNORECASE)
_DIGITS = re.compile(r"\d+")
# Longer numbers are no page numbers.
_MAX_DIGITS = 6
# See page_numbers.
RUN = 10


def parse_name(name):
    """(label, number) shown for a page named name in the list.

    "143" and "p143" are page 143 ("v2-5", page 5 of volume 2, is 5);
    Roman numerals of the front matter stay as printed, without a number.
    None for names without a number ("Cover"): no page.
    """
    name = " ".join(name.split())
    if _ROMAN.fullmatch(name):
        return name, None
    runs = _DIGITS.findall(name)
    if not runs or len(runs[-1]) > _MAX_DIGITS:
        return None
    number = int(runs[-1])
    return str(number), number


def page_numbers(spine_paths, targets):
    """What QML needs to show the printed page, or None to estimate it.

    spine_paths lists the chapters in reading order, targets the page list
    (PageTarget) in its order. The list is of no use if at most half of its
    entries point into a chapter (lists made by calibre put every page of
    a chapter at its start) or none names a page. Returns
    {"total", "marks", "start"}: total is the highest page number, 0 if
    the numbering starts again (several volumes in one book); marks[i]
    lists the pages beginning in chapter i as [fragment, label, counted],
    counted meaning that the page is a number of total; start[i] is the
    page in effect where chapter i begins, [label, counted], or None before
    the first page.

    Books move single pages: a copyright page printed at the back stands
    at the front ("338", then "1", "2" ...). Numbers before the first drop
    in fewer than RUN pages are left out, else the front matter would show
    the last page. The numbering starts again only if RUN or more numbers
    occur twice: a page out of order elsewhere or a short appendix counted
    anew keep the total.
    """
    if not targets or 2 * sum(1 for t in targets if t.fragment) <= len(targets):
        return None
    index = {}
    for i, path in enumerate(spine_paths):
        index.setdefault(path, i)
    entries = []
    for target in targets:
        chapter = index.get(target.path)
        parsed = parse_name(target.name)
        if chapter is not None and parsed is not None:
            entries.append((chapter, target.fragment) + parsed)
    numbers = [e[3] for e in entries if e[3] is not None]
    drop = next((k for k in range(1, len(numbers)) if numbers[k] < numbers[k - 1]), 0)
    if drop >= RUN:
        drop = 0
    marks = [[] for _ in spine_paths]
    seen = set()
    twice = 0
    counted = 0
    total = 0
    for chapter, fragment, label, number in entries:
        if number is not None:
            counted += 1
            if counted <= drop:
                continue
            twice += number in seen
            seen.add(number)
            total = max(total, number)
        marks[chapter].append([fragment, label, number is not None])
    if not any(marks):
        return None
    start = []
    current = None
    for chapter_marks in marks:
        start.append(current)
        if chapter_marks:
            current = chapter_marks[-1][1:]
    return {"total": 0 if twice >= RUN else total, "marks": marks, "start": start}


# Characters a printed page holds, measured on the library's page lists
# (lernen/31): German books 1590 (median), English ones 1690. ReaderPage
# estimates the page in the corner the same way.
def chars_per_page(language):
    return 1600 if (language or "").lower().startswith("de") else 1700


class PageFinder(object):
    """The printed page at any place of a book: from its page list (info,
    see page_numbers), else estimated by characters like the corner of the
    reading page.

    chapters are the chapters' search.Chapter (text and where each id
    starts), linear whether each is in the reading order. Places are
    indices in a chapter's text.
    """

    def __init__(self, info, chapters, linear, language):
        self.info = info
        self.estimated = info is None
        self._chapters = chapters
        self._linear = linear
        if info is not None:
            # Per chapter: [(index, label, mark)] of the marks found in its
            # text, in the list's order; mark is the index in info's marks.
            self._marks = []
            for chapter, marks in zip(chapters, info["marks"]):
                found = []
                for k, (fragment, label, counted) in enumerate(marks):
                    if not fragment:
                        found.append((0, label, k))
                    elif fragment in chapter.ids:
                        found.append((chapter.ids[fragment], label, k))
                self._marks.append(found)
            return
        self.per_page = chars_per_page(language)
        # Counted as package.text_length counts, as the reading page does.
        self.lengths = [len(" ".join(c.text.split())) for c in chapters]
        self.total_chars = sum(n for n, on in zip(self.lengths, linear) if on)
        self.total = max(1, -(-self.total_chars // self.per_page))

    def label(self, spine, index):
        """The page at index in chapter spine's text: the last mark at or
        before it (or the spaces after it), "" if none (before the first page of the list, or a
        place not in the book)."""
        if not 0 <= spine < len(self._chapters):
            return ""
        if self.estimated:
            return str(self._estimate(spine, index))
        # A mark often follows a heading's id after a line break: the page
        # begins where the next text does.
        text = self._chapters[spine].text
        while index < len(text) and text[index].isspace():
            index += 1
        before = None
        for at, label, k in self._marks[spine]:
            if at <= index:
                before = label
        if before is not None:
            return before
        start = self.info["start"][spine]
        return start[0] if start else ""

    def _estimate(self, spine, index):
        before = sum(n for n, on in zip(self.lengths[:spine], self._linear) if on)
        text = self._chapters[spine].text
        length = self.lengths[spine] if self._linear[spine] else 0
        share = min(1.0, index / len(text)) if text else 0.0
        return min(self.total, int((before + share * length) // self.per_page) + 1)

    def stops(self, title_at):
        """The places of the bar in the page flip view, in reading order:
        [{label, spine, title}] with counted and mark (as in page_numbers:
        whether the page is a number of the total, and the index in the
        chapter's marks; -1 for the start of the book, before its first
        page), or with share (estimated pages: where the page begins, as a
        share of the chapter's characters). Chapters outside the reading
        order are left out. title_at(spine, index) names the heading there.
        """
        linear = [i for i, on in enumerate(self._linear) if on]
        if not linear:
            return []
        if self.estimated:
            return self._estimated_stops(linear, title_at)
        stops = []
        for spine in linear:
            # All of the list's marks: the frame script may find one Python
            # does not (and the other way round).
            places = {k: at for at, _, k in self._marks[spine]}
            for k, (fragment, label, counted) in enumerate(self.info["marks"][spine]):
                stops.append({"label": label, "counted": counted, "spine": spine, "mark": k,
                              "title": title_at(spine, places.get(k, 0))})
        first = linear[0]
        marks = self._marks[first]
        # Only if there is text before the first page (spaces are none).
        if (not stops or stops[0]["spine"] != first or not marks or marks[0][2] != 0
                or self._chapters[first].text[:marks[0][0]].strip()):
            stops.insert(0, {"label": "", "counted": False, "spine": first, "mark": -1,
                             "title": title_at(first, 0)})
        return stops

    def _estimated_stops(self, linear, title_at):
        stops = []
        spine_at = 0
        before = 0
        for page in range(self.total):
            goal = page * self.per_page
            # The chapter the page begins in; empty ones are passed over.
            while spine_at < len(linear) - 1 and before + self.lengths[linear[spine_at]] <= goal:
                before += self.lengths[linear[spine_at]]
                spine_at += 1
            spine = linear[spine_at]
            length = self.lengths[spine]
            share = min(1.0, (goal - before) / length) if length else 0.0
            stops.append({"label": str(page + 1), "spine": spine, "share": share,
                          "title": title_at(spine, int(share * len(self._chapters[spine].text)))})
        return stops
