"""Entry points called from QML through PyOtherSide.

Returns plain dicts and lists, because PyOtherSide hands namedtuples to QML
as lists without field names. A book that cannot be used is not a program
error: it comes back as {"error": code, "detail": text}, where code is one
of the EpubError codes or "io", and QML shows a translated message.
"""

import collections
import getpass
import hashlib
import math
import os
import threading
import time
import traceback
import unicodedata

from . import audiobook, cache, history as history_store, library, notes, positions
from .errors import EpubError
from .overlay import read_overlay
from .package import read_package, text_length
from .paths import local_path
from .search import BookIndex

_MAX_KEY_LENGTH = 200


_MEDIA_ROOT = "/run/media"


def default_folders(documents):
    """Where books are looked for unless the user chose a folder: the
    documents folder and every memory card."""
    try:
        user = getpass.getuser()
    except (KeyError, OSError):
        return [documents]
    return [documents] + library.card_folders(os.path.join(_MEDIA_ROOT, user))


# SVG left out: QtSvg may load files an image names.
_COVER_TYPES = (".jpg", ".jpeg", ".png", ".gif")
_MAX_WAITING_COVERS = 50


class Worker:
    """A thread that runs requests one after the other, the newest first.

    A request with the key of one still waiting replaces it, so repeated
    requests run once; beyond limit the oldest waiting ones are dropped.
    """

    def __init__(self, run, limit=None):
        self._run = run
        self._limit = limit
        self._waiting = collections.OrderedDict()
        self._condition = threading.Condition()
        self._thread = None

    def submit(self, key, *args):
        with self._condition:
            self._waiting.pop(key, None)
            self._waiting[key] = args
            if self._limit is not None and len(self._waiting) > self._limit:
                self._waiting.popitem(last=False)
            if self._thread is None:
                self._thread = threading.Thread(target=self._loop, daemon=True)
                self._thread.start()
            self._condition.notify()

    def _loop(self):
        while True:
            with self._condition:
                while not self._waiting:
                    self._condition.wait()
                key, args = self._waiting.popitem(last=True)
            try:
                self._run(key, *args)
            except Exception:
                traceback.print_exc()


def _send(*args):
    import pyotherside  # only on the device
    pyotherside.send(*args)


def cached_library(cache_file, folders):
    """The books below folders as last scanned, at once; see library_view."""
    prefixes = tuple(os.path.join(folder, "") for folder in folders)
    return library_view([e for e in library.load_cached(cache_file)
                         if e["path"].startswith(prefixes)], folders)


def scan_library(folders, cache_file, covers_dir, serial):
    """Look for new and changed books in a thread, so that a book can be
    opened meanwhile; the result comes as the event ("library", serial,
    result). Only the latest request waiting is run."""
    _scanner.submit("scan", folders, cache_file, covers_dir, serial)


def _scan(key, folders, cache_file, covers_dir, serial):
    try:
        result = scan_now(folders, cache_file, covers_dir)
    except Exception as e:
        traceback.print_exc()
        result = _error("io", repr(e))
    _send("library", serial, result)


def scan_now(folders, cache_file, covers_dir):
    """The library view of a scan; {"unchanged": true} if the books are the
    ones of the cache, which cached_library has shown already."""
    try:
        entries, changed = library.scan(folders, cache_file)
    except OSError as e:
        return _error("io", str(e))
    if not changed:
        return {"unchanged": True}
    library.prune_covers(covers_dir, {library.cover_name(e)
                                      for e in library.load_cached(cache_file)})
    return library_view(entries, folders)


def library_view(entries, folders=()):
    """{books, authors} for the library pages.

    books are sorted by author, then series in order, then the other titles;
    authors lists each first author once with the number of books. Authors
    are told apart by their sort name ("Wilde, Oscar"), so "Oscar Wilde" in
    one book and "Wilde, Oscar" in another are one author; group is the key.
    Books that a readaloud replaces are left out (see library.arranged).
    kind is "epub", "readaloud" or "audiobook"; an audiobook read from an
    EPUB beside it has its cover (if it has one), and coverPath and key are
    the EPUB's. folders are the library folders (see library.arranged).
    """
    shown = library.arranged(entries, folders)
    keys = [(library.normal_identifier(info["identifier"]), info["title"], info["audio"])
            for _, info, _ in shown]
    copies = collections.Counter(keys)
    books = []
    for (entry, info, partner), key in zip(shown, keys):
        kind = ("audiobook" if info["kind"] == "audiobook"
                else "readaloud" if info["audio"] else "epub")
        cover_entry = partner if partner is not None and partner["info"]["cover"] else entry
        author = info["authors"][0] if info["authors"] else ""
        sort = info["sort"] or author
        books.append({
            "path": entry["path"], "key": library.cover_name(cover_entry),
            "kind": kind, "coverPath": cover_entry["path"],
            "title": info["title"], "author": author, "authors": "; ".join(info["authors"]),
            "coauthors": [_natural(name) for name in info["authors"][1:]],
            "sort": sort, "group": fold(sort), "letter": _letter(sort),
            "series": info["series"],
            "index": info["index"], "cover": cover_entry["info"]["cover"],
            "broken": info["broken"],
            "removable": entry["path"].startswith(_MEDIA_ROOT + "/"),
            # Several copies of one book: say where each is.
            "duplicate": bool(info["identifier"]) and copies[key] > 1,
            "search": fold(" ".join(info["authors"] + [info["title"], info["series"]]))})
    books.sort(key=_order)
    authors = []
    for book in books:
        if authors and authors[-1]["group"] == book["group"]:
            authors[-1]["count"] += 1
        else:
            authors.append({"name": book["author"], "group": book["group"],
                            "letter": book["letter"], "count": 1})
    return {"books": books, "authors": authors}


def request_cover(path, cover_path, name, covers_dir):
    """The file of the book's cover if it is extracted already, else "" and
    it is extracted in a thread, coming as the event ("cover", name, file);
    file is "" if the book has no usable cover. path is the book's coverPath
    and cover_path its cover (see library_view)."""
    target = _cover_target(cover_path, name, covers_dir)
    if not target:
        return ""
    if os.path.isfile(target):
        return target
    _covers.submit(name, path, cover_path, covers_dir)
    return ""


def _extract(name, path, cover_path, covers_dir):
    _send("cover", name, cover(path, cover_path, name, covers_dir))


def _cover_target(cover_path, name, covers_dir):
    ext = os.path.splitext(cover_path or "")[1].lower()
    return os.path.join(covers_dir, name + ext) if ext in _COVER_TYPES else ""


def cover(path, cover_path, name, covers_dir):
    """The file of the book's cover in covers_dir, extracted on first use
    from the EPUB or the audiobook at path; "" if there is none."""
    target = _cover_target(cover_path, name, covers_dir)
    if not target:
        return ""
    if os.path.isfile(target):
        return target
    try:
        os.makedirs(covers_dir, exist_ok=True)
    except OSError:
        return ""
    # Only files found as EPUBs end in .epub; a folder is an audiobook.
    if path.lower().endswith(".epub") and not os.path.isdir(path):
        found = library.extract_cover(path, cover_path, target)
    else:
        found = library.extract_audio_cover(path, cover_path, target)
    return target if found else ""


def recent_books(path):
    """The books opened last, newest first."""
    return positions.load_recent(path)


def fold(text):
    """text for comparing: lower case, without accents (ä → a, ß → ss)."""
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


_SUFFIXES = {"jr.", "jr", "sr.", "sr", "ii", "iii", "iv"}


def _natural(name):
    """ "Child, Andrew" as "Andrew Child"; other forms stay, also
    "Sammy Davis, Jr."."""
    parts = name.split(", ")
    if len(parts) != 2 or parts[1].casefold() in _SUFFIXES:
        return name
    return parts[1] + " " + parts[0]


def _letter(sort):
    first = fold(sort)[:1].upper()
    return first if first.isalpha() else ("#" if first else "")


def _order(book):
    # Authors not starting with a letter first, unknown ones last, so that
    # each section appears once.
    # The book before its audiobook.
    return (book["group"] == "", book["letter"] != "#", book["group"], book["series"] == "",
            fold(book["series"]), book["index"] if book["index"] is not None else math.inf,
            fold(book["title"]), book["kind"] == "audiobook", book["path"])


def open_book(epub_path, cache_dir):
    try:
        root, book = cache.open_book(epub_path, cache_dir, read_package)
    except EpubError as e:
        return _error(e.code, e.detail)
    except OSError as e:
        return _error("io", str(e))
    spine_index = {}
    for index, item in enumerate(book.spine):
        spine_index.setdefault(item.path, index)
    return {
        "root": root,
        "path": epub_path,
        "key": _epub_key(book.identifier, epub_path),
        "title": book.title,
        "authors": book.authors,
        "language": book.language,
        "duration": book.duration,
        # Shown on the lock screen; a cover named but missing is no cover.
        "cover": (book.cover if book.cover and os.path.isfile(local_path(root, book.cover))
                  else None),
        "activeClass": book.active_class,
        "spine": [{"path": item.path, "overlay": item.overlay,
                   "linear": item.linear} for item in book.spine],
        "toc": [{"title": entry.title, "path": entry.path,
                 "fragment": entry.fragment, "level": entry.level,
                 "spine": spine_index.get(entry.path, -1)}
                for entry in book.toc],
    }


def open_audiobook(path, library_cache, folders, covers_dir, audio_cache):
    """The audiobook at path (file or folder) for the player page: its
    chapters as audiobook.open_audiobook gives them, and title, authors and
    cover as the library shows them (an EPUB beside it gives its own).
    folders are the library folders, [] if not known yet (the app is
    starting); then every book of the cache counts. cover is a file or "".

    A folder not read yet comes with estimated chapters ("complete" false);
    the files are read in a thread, and the full chapters come as the event
    ("audiobook", path, result).
    """
    try:
        book = audiobook.open_audiobook(path, audio_cache)
    except EpubError as e:
        return _error(e.code, e.detail)
    except OSError as e:
        return _error("io", str(e))
    except Exception as e:
        # The library waits for an answer.
        traceback.print_exc()
        return _error("internal", repr(e))
    entry = next((b for b in library_view(library.load_cached(library_cache), folders)["books"]
                  if b["path"] == path), None)
    if entry is not None:
        title = entry["title"]
        authors = [a for a in entry["authors"].split("; ") if a]
        cover_file = cover(entry["coverPath"], entry["cover"], entry["key"], covers_dir)
    else:
        # Not in the library (yet): the tags tell.
        info = _tags_info(path)
        title, authors, cover_file = info["title"], info["authors"], ""
    book.update(kind="audiobook", path=path, title=title, authors=authors, cover=cover_file,
                key=_audio_key(path))
    if not book["complete"]:
        _audiobooks.submit(path, audio_cache)
    return book


def _tags_info(path):
    files = library.audio_files(path) if os.path.isdir(path) else [path]
    name = os.path.basename(path)
    if not os.path.isdir(path):
        name = os.path.splitext(name)[0]
    try:
        return library.audio_info(library.BookFile(path, name, "audiobook", tuple(files)))
    except Exception:
        return library.broken_info(path, "audiobook")


def _read_audiobook(path, audio_cache):
    try:
        result = audiobook.read_folder(path, audio_cache)
    except EpubError as e:
        result = _error(e.code, e.detail)
    except OSError as e:
        result = _error("io", str(e))
    except Exception as e:
        traceback.print_exc()
        result = _error("internal", repr(e))
    _send("audiobook", path, result)


def is_audiobook(path):
    """Whether the book at path, as the library found it, is an audiobook:
    the library lists only EPUB files, audio files and audio folders."""
    return os.path.isdir(path) or not path.lower().endswith(".epub")


def audio_history(path, key):
    """The sessions of listening to the audiobook key, newest first (see
    history.sessions); each entry is {time, kind, spine, ms}."""
    return {"sessions": history_store.sessions(history_store.load(path, key))}


def chapter_lengths(root, paths):
    """Characters of text in each chapter, for estimating page numbers.

    A separate call, so that parsing every chapter does not delay opening
    the book.
    """
    lengths = {}
    for path in paths:
        if path not in lengths:
            lengths[path] = text_length(root, path)
    return [lengths[path] for path in paths]


def read_chapter(root, chapter_path, smil_path):
    """The sentences of the chapter chapter_path, in reading order.

    "ids" lists each sentence element once, for the page; "sentences" lists
    what is played: element id, audio file (path in the book), begin and
    end in ms, end None meaning to the end of the file.
    """
    try:
        overlay = read_overlay(root, smil_path)
    except EpubError as e:
        return _error(e.code, e.detail)
    except OSError as e:
        return _error("io", str(e))
    ids = []
    seen = set()
    sentences = []
    for fragment in overlay.fragments:
        # A SMIL file may point into other chapters; those ids could collide
        # with ids of this page.
        if fragment.text_path != chapter_path:
            continue
        sentences.append({"id": fragment.text_id, "audio": fragment.audio_path,
                          "begin": fragment.begin, "end": fragment.end})
        if fragment.text_id not in seen:
            seen.add(fragment.text_id)
            ids.append(fragment.text_id)
    return {"ids": ids, "sentences": sentences, "skipped": overlay.skipped}


def follow_link(root, spine, toc, chapter, href, ordinal):
    """What a long press on a link does, see notes.follow_link; spine and
    toc as open_book gives them."""
    try:
        return notes.follow_link(root, [item["path"] for item in spine],
                                 {(entry["path"], entry["fragment"] or "") for entry in toc},
                                 chapter, href, int(ordinal))
    except Exception:
        # The reader waits for an answer.
        traceback.print_exc()
        return {}


def load_position(path, key):
    return positions.load(path, key)


def save_position(path, key, position, moved=False):
    """moved: the reader moved the place, see positions.save."""
    try:
        positions.save(path, key, position, time.time() if moved else None)
    except OSError as e:
        return _error("io", str(e))
    return True


def load_last_book(path):
    return positions.load_last(path)


def save_last_book(path, epub_path):
    try:
        positions.save_last(path, epub_path)
    except OSError as e:
        return _error("io", str(e))
    return True


def partner(path, library_cache, positions_file):
    """The other form of the book at path, as the library pairs them: the
    audiobook of an EPUB, the EPUB of an audiobook; None for a readaloud or
    a book without one. {path, key, kind, progress, time}: its place as
    stored, progress -1 and time 0 if not known. Of several audiobooks of
    one EPUB the one used last that has a progress."""
    found = []
    for entry, _, epub in library.arranged(library.load_cached(library_cache)):
        if epub is None:
            continue
        if entry["path"] == path:
            found.append((epub["path"], _epub_key(epub["info"]["identifier"], epub["path"]),
                          "epub"))
        elif epub["path"] == path:
            found.append((entry["path"], _audio_key(entry["path"]), "audiobook"))
    best = None
    for other, key, kind in found:
        stored = positions.load(positions_file, key) or {}
        candidate = {"path": other, "key": key, "kind": kind,
                     "progress": stored.get("progress", -1), "time": stored.get("time", 0)}
        if best is None or ((candidate["progress"] >= 0, candidate["time"])
                            > (best["progress"] >= 0, best["time"])):
            best = candidate
    return best


def _epub_key(identifier, epub_path):
    return _position_key(identifier or os.path.basename(epub_path))


def _audio_key(path):
    return _position_key("audio:" + os.path.basename(path))


def _position_key(name):
    # The identifier stays the same when the file is renamed or synced again,
    # so the reading position follows the book. It comes from the book and
    # has no length limit; a huge one must not fill the positions file.
    if len(name) <= _MAX_KEY_LENGTH:
        return name
    return "sha1:" + hashlib.sha1(name.encode("utf-8", "surrogateescape")).hexdigest()


# The index of the book searched last: (root, BookIndex). Only the worker
# thread builds it; a reference taken there stays usable if it is dropped.
_index = None
# Books closed: an index still being built for one of them is not kept.
_closed = set()


def prepare_search(root):
    """Read the book's text in a thread, so the first search is quick."""
    _closed.discard(root)
    _searcher.submit("prepare", root, 0)


def search(root, query, here, serial):
    """Look for query in the book in a thread; the result comes as the event
    ("search", serial, result), see search.BookIndex.search. here is the
    reading position, as stored. Only the latest request waiting is run."""
    _closed.discard(root)
    _searcher.submit("search", root, serial, query, here)


def add_history(path, key, kind, place):
    """Note in the history that kind happened at place of the book key now:
    {spine, id} when listening to a readaloud, {spine, ms} to an audiobook,
    {spine, offset} when reading; see history.add."""
    try:
        history_store.add(path, key, kind, place, int(time.time()))
    except ValueError as e:
        return _error("invalid", str(e))
    except OSError as e:
        return _error("io", str(e))
    return True


def history(root, path, key, serial):
    """The sessions of reading and listening of the book key at root, read
    in a thread like the search; the result comes as the event ("history",
    serial, result): {sessions: [{mode, start, end, entries}]}, newest first
    (see history.sessions). Each entry is {time, kind} and its place as
    BookIndex.sentence or BookIndex.text_at gives it."""
    _closed.discard(root)
    _searcher.submit("history", root, serial, path, key)


def drop_search(root):
    """Forget the index of the book at root, which is being closed."""
    global _index
    _closed.add(root)
    if _index is not None and _index[0] == root:
        _index = None


def _book_index(root):
    global _index
    index = _index
    if index is None or index[0] != root:
        index = (root, BookIndex(root))
        if root not in _closed:
            _index = index
    return index[1]


def _search(key, root, serial, *args):
    try:
        if key == "history" and not history_store.load(*args):
            # Not worth reading the book for: the search page waits for this
            # before it gives the keyboard.
            result = {"sessions": []}
        else:
            index = _book_index(root)
            if key == "prepare":
                return
            if key == "history":
                result = _history(index, *args)
            else:
                result = index.search(*args)
    except EpubError as e:
        result = _error(e.code, e.detail)
    except OSError as e:
        result = _error("io", str(e))
    except Exception as e:
        # The search page waits for an answer.
        traceback.print_exc()
        result = _error("internal", repr(e))
    _send("history" if key == "history" else "search", serial, result)


def _history(index, path, key):
    sessions = history_store.sessions(history_store.load(path, key))
    for session in sessions:
        places = []
        for entry in session["entries"]:
            if "offset" in entry:
                place = index.text_at(entry["spine"], entry["offset"])
            else:
                place = index.sentence(entry["spine"], entry["id"])
            place.update(time=entry["time"], kind=entry["kind"])
            places.append(place)
        session["entries"] = places
    return {"sessions": sessions}


def _error(code, detail):
    return {"error": code, "detail": detail}


_scanner = Worker(_scan)
_covers = Worker(_extract, _MAX_WAITING_COVERS)
_searcher = Worker(_search)
_audiobooks = Worker(_read_audiobook)
