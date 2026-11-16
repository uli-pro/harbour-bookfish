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
