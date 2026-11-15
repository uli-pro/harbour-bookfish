"""Bookmarks and notes, per book. A note is a bookmark with text of its own.

Kept in a file of its own beside the positions and the history. Unlike
those, it holds the reader's own writing: a file that cannot be read is put
aside before anything new is written, never overwritten, and entries that
are not understood stay in the file untouched.

A bookmark is a dict: id (int, unique within its book), created and changed
(seconds since 1970), spine (index of the chapter), offset and length (the
place in the chapter's text, in UTF-16 code units, as the search and the
reader's frame script count), raw (the text there exactly as it stands, to
find the place again should the offset no longer fit), quote (the text to
show: spaces folded, without notes' numbers) and note ("" for a bookmark
without a note).

File format: {"books": {key: [bookmark, ...]}}.
"""

import json
import math
import os

from . import jsonfile

MAX_PER_BOOK = 5000
MAX_NOTE = 100000
MAX_TEXT = 10000
MAX_SIZE = 20 * 1024 * 1024
_MAX_SPINE = 100000


def load(path, key):
    """The valid bookmarks of the book key, in the order of the book."""
    return _ordered(_valid(entry) for entry in _read(path)[1].get(key, []))


def add(path, key, mark, now):
    """Add mark ({spine, offset, length, raw, quote, note}) to the book key
    and return it as stored, with id, created and changed. Raises
    ValueError if it is not valid or the book or the file is full."""
    entry = _valid(dict(mark, id=0, created=now, changed=now))
    if entry is None:
        raise ValueError("invalid bookmark")
    stored, books = _for_writing(path)
    entries = books.get(key, [])
    if sum(1 for e in entries if _valid(e) is not None) >= MAX_PER_BOOK:
        raise ValueError("too many bookmarks")
    # Also past ids of entries not understood: they stay in the file.
    ids = [_number(e.get("id")) for e in entries if isinstance(e, dict)]
    entry["id"] = max((i for i in ids if i is not None), default=0) + 1
    books[key] = entries + [entry]
    _write(path, stored, books)
    return entry


def set_note(path, key, ident, note, now):
    """Change the note of bookmark ident of the book key and return it as
    stored; None if there is no such bookmark. Raises ValueError for a note
    that is too long."""
    if not isinstance(note, str) or len(note) > MAX_NOTE:
        raise ValueError("invalid note")
    stored, books = _for_writing(path)
    entries = books.get(key, [])
    for i, entry in enumerate(entries):
        if _id(entry) == ident:
            # Fields of a later version stay.
            entries[i] = dict(entry, note=note, changed=now)
            _write(path, stored, books)
            return _valid(entries[i])
    return None


def delete(path, key, ident):
    """Remove bookmark ident of the book key; False if there is none."""
    stored, books = _for_writing(path)
    entries = books.get(key, [])
    kept = [entry for entry in entries if _id(entry) != ident]
    if len(kept) == len(entries):
        return False
    if kept:
        books[key] = kept
    else:
        del books[key]
    _write(path, stored, books)
    return True


def _id(entry):
    mark = _valid(entry)
    return mark["id"] if mark is not None else None


def _ordered(marks):
    return sorted((m for m in marks if m is not None),
                  key=lambda m: (m["spine"], m["offset"], m["id"]))


def _read(path):
    """The whole file, its books, and whether it is damaged: there, but not
    JSON of the expected form, or too large. A file that cannot be opened
    raises OSError: it may be fine, and must not be put aside."""
    if not os.path.exists(path):
        return {}, {}, False
    with open(path, "rb"):
        pass
    stored = jsonfile.read(path, MAX_SIZE)
    books = stored.get("books") if isinstance(stored, dict) else None
    if not isinstance(books, dict) or not all(isinstance(entries, list) for entries in books.values()):
        return {}, {}, True
    return stored, books, False


def _for_writing(path):
    stored, books, damaged = _read(path)
    if damaged:
        # Kept for the reader to rescue: never written over.
        aside = "{}.damaged-{}".format(path, int(os.path.getmtime(path)))
        n = 1
        while os.path.exists(aside):
            n += 1
            aside = "{}.damaged-{}-{}".format(path, int(os.path.getmtime(path)), n)
        os.replace(path, aside)
    return stored, books


def _write(path, stored, books):
    # Other keys, of a later version, stay.
    data = dict(stored, books=books)
    # As jsonfile.write stores it; a file too large would not be read again.
    if len(json.dumps(data, sort_keys=True)) > MAX_SIZE:
        raise ValueError("bookmarks file full")
    jsonfile.write(path, data)


def _valid(entry):
    """A clean copy of entry, or None if it is not a valid bookmark."""
    if not isinstance(entry, dict):
        return None
    ident = _number(entry.get("id"))
    spine = _number(entry.get("spine"))
    offset = _number(entry.get("offset"))
    length = _number(entry.get("length"))
    created = entry.get("created")
    changed = entry.get("changed")
    raw = entry.get("raw")
    quote = entry.get("quote")
    note = entry.get("note", "")
    if (ident is None or spine is None or spine > _MAX_SPINE or offset is None
            or length is None or not 0 < length <= MAX_TEXT
            or not _time(created) or not _time(changed)
            or not isinstance(raw, str) or not 0 < len(raw) <= MAX_TEXT
            or not isinstance(quote, str) or len(quote) > MAX_TEXT
            or not isinstance(note, str) or len(note) > MAX_NOTE):
        return None
    return {"id": ident, "created": created, "changed": changed, "spine": spine,
            "offset": offset, "length": length, "raw": raw, "quote": quote, "note": note}


def _number(value):
    """value as an int >= 0, or None."""
    # A number from QML may come as a float.
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    # bool is a subclass of int, but true is no number here.
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return None
    return value


def _time(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
