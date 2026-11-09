"""Finding the books in the library folders and what the library shows
of them, kept in a cache file so that a memory card is not read again.

A book is an EPUB file or an audiobook. An audiobook is an M4B file, an MP3
file beside EPUBs (an author's folder holding several books) or in a library
folder itself, or a folder of MP3 files without EPUBs, each file a chapter. An audiobook named like an
EPUB beside it is that book read aloud: it shows the EPUB's title, author,
series and cover.
"""

import collections
import hashlib
import json
import math
import os
import re
import stat
import struct
import zipfile

from . import mp3, mp4
from .audioutil import natural_key, picture_type
from .errors import EpubError
from .package import check_encryption, package_path, read_info
from .xmlutil import MAX_XML_SIZE, parse_xml_data

MAX_CACHE_SIZE = 16 * 1024 * 1024
MAX_COVER_SIZE = 5 * 1024 * 1024
# PNG and GIF are decoded at full size before they are scaled down; a small
# file can hold a huge image. JPEG is decoded scaled.
MAX_COVER_PIXELS = 4096
# Raised whenever what is read from a book changes, so that all are read again.
_CACHE_VERSION = 5
# Errors that say something about the book. Others (a card pulled out, no
# memory) may pass, so the book is read again next time.
_BOOK_ERRORS = (EpubError, zipfile.BadZipFile, zipfile.LargeZipFile, KeyError, ValueError,
                EOFError, NotImplementedError, RuntimeError)
_UNREAD = [-1, -1]
# Prefixes of the same identifier: Storyteller writes "uuid:…" where the
# book it started from had "urn:uuid:…" or nothing.
_ID_PREFIXES = ("urn:", "uuid:", "url:", "asin:", "isbn:")
_COVER_FILE = re.compile(r"^([0-9a-f]{16})(\.[a-z]+)?(\.part)?$")
# A picture beside the audio files of a folder; or the one in the tags.
_FOLDER_COVER = re.compile(r"cover\.(jpe?g|png)", re.IGNORECASE)
_EMBEDDED_COVERS = ("embedded.jpg", "embedded.png")
_AUDIO_TYPES = (".mp3", ".m4b")
# kind: "epub" (with or without narration, see audio) or "audiobook".
_INFO_FIELDS = {"identifier": str, "title": str, "authors": list, "sort": str,
                "series": str, "index": (float, type(None)),
                "cover": (str, type(None)), "audio": bool, "broken": bool, "kind": str}
_KINDS = ("epub", "audiobook")

BookFile = collections.namedtuple("BookFile", "path name kind files", defaults=("epub", ()))
BookFile.__doc__ = """A book found: path of the EPUB or audio file, or of
the folder of an audiobook; name is the file name without extension or the
folder name; kind "epub" or "audiobook"; files the audio files in order."""


def list_books(folders):
    """Return the books below folders (see BookFile), sorted by name.

    Hidden files and folders are left out. Symbolic links to folders are not
    followed, so a link cannot make the walk endless. Missing folders are
    ignored, and so are names that are not valid UTF-8: QML could not show
    or open them.
    """
    books = []
    seen = set()
    for folder in folders:
        for dirpath, dirnames, filenames in os.walk(folder):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            epubs, mp3s = [], []
            for filename in filenames:
                stem, ext = os.path.splitext(filename)
                ext = ext.lower()
                if ext not in (".epub",) + _AUDIO_TYPES or filename.startswith("."):
                    continue
                path = os.path.join(dirpath, filename)
                try:
                    path.encode("utf-8")
                except UnicodeEncodeError:
                    continue
                real = os.path.realpath(path)
                if real in seen:
                    continue
                seen.add(real)
                if ext == ".epub":
                    epubs.append(path)
                    books.append(BookFile(path, stem))
                elif ext == ".m4b":
                    books.append(BookFile(path, stem, "audiobook", (path,)))
                else:
                    mp3s.append(path)
            # Beside EPUBs each MP3 is a book: an author's folder. So in
            # the library folder itself, which is no audiobook.
            if epubs or dirpath == folder:
                books.extend(BookFile(path, os.path.splitext(os.path.basename(path))[0],
                                      "audiobook", (path,)) for path in mp3s)
            elif mp3s:
                mp3s.sort(key=lambda path: natural_key(os.path.basename(path)))
                books.append(BookFile(dirpath, os.path.basename(dirpath), "audiobook",
                                      tuple(mp3s)))
    books.sort(key=lambda book: (book.name.casefold(), book.path))
    return books


def audio_files(folder):
    """The MP3 files of an audiobook folder in order, as list_books finds
    them."""
    names = [name for name in os.listdir(folder)
             if os.path.splitext(name)[1].lower() == ".mp3" and not name.startswith(".")
             and _utf8(name)]
    return [os.path.join(folder, name) for name in sorted(names, key=natural_key)]


def _utf8(name):
    # QML could not show or open other names.
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def card_folders(media_root):
    """The mounted memory cards: folders in media_root (/run/media/<user>)."""
    try:
        names = sorted(os.listdir(media_root))
    except OSError:
        return []
    return [os.path.join(media_root, name) for name in names
            if os.path.isdir(os.path.join(media_root, name))]


def book_info(path):
    """The library entry of the EPUB at path, read without unpacking.

    Raises EpubError, OSError or zipfile errors if the book is unusable. A
    book with DRM is listed, marked broken: opening it says why.
    """
    with _open_regular(path) as f, zipfile.ZipFile(f) as archive:
        container = parse_xml_data(_member(archive, "META-INF/container.xml"),
                                   "META-INF/container.xml")
        opf_path = package_path(container)
        info = read_info(parse_xml_data(_member(archive, opf_path), opf_path), opf_path)
        broken = False
        if "META-INF/encryption.xml" in archive.namelist():
            try:
                check_encryption(parse_xml_data(_member(archive, "META-INF/encryption.xml"),
                                                "META-INF/encryption.xml"))
            except EpubError:
                broken = True
    return {"identifier": info.identifier, "title": info.title, "authors": info.authors,
            "sort": info.sort, "series": info.series, "index": info.series_index,
            "cover": info.cover, "audio": info.audio, "broken": broken, "kind": "epub"}


def audio_info(book):
    """The library entry of the audiobook book (a BookFile), from the tags
    of its first file.

    Raises AudioError or OSError if the file is unusable.
    """
    first = book.files[0]
    reader = mp4 if first.lower().endswith(".m4b") else mp3
    tags = reader.read(first, chapters=False)
    if len(book.files) == 1 and book.path == first:
        # Audible files have the title in one and the title plus
        # "(Unabridged)" or a subtitle in the other, in either order.
        names = [name for name in (tags["title"], tags["album"]) if name]
        title = min(names, key=len) if names else ""
    else:
        title = tags["album"]
    author = tags["albumartist"] or tags["artist"]
    cover = None
    if book.path != first:
        cover = next((name for name in sorted(os.listdir(book.path))
                      if _FOLDER_COVER.fullmatch(name)), None)
    if cover is None and tags["picture"]:
        cover = "embedded." + tags["picture"]
    return {"identifier": "", "title": title or book.name, "authors": [author] if author else [],
            "sort": "", "series": "", "index": None, "cover": cover, "audio": False,
            "broken": False, "kind": "audiobook"}


def broken_info(path, kind="epub"):
    """The entry of a book that cannot be read: listed by its file or
    folder name, so that opening it explains what is wrong."""
    name = os.path.basename(path)
    if not os.path.isdir(path):
        name = os.path.splitext(name)[0]
    return {"identifier": "", "title": name,
            "authors": [], "sort": "", "series": "", "index": None, "cover": None,
            "audio": False, "broken": True, "kind": kind}


def scan(folders, cache_file):
    """All EPUBs below folders as ([{path, stamp, info}], changed).

    Only files that are new or changed since the cache file was written are
    read; reading every book from a memory card took 93 s on the device.
    The cache keeps the books of other folders and of folders that are
    missing now, e.g. a memory card taken out. changed is false if the
    entries are those of the cache.
    """
    cached = load_cached(cache_file)
    walked = tuple(os.path.join(folder, "") for folder in folders if os.path.isdir(folder))
    known = {e["path"]: e for e in cached if e["path"].startswith(walked)}
    entries = []
    changed = False
    for book in list_books(folders):
        stamp = _stamp(book)
        if stamp is None:
            continue
        old = known.get(book.path)
        if old is not None and old["stamp"] == stamp and old["info"]["kind"] == book.kind:
            info = old["info"]
        else:
            changed = True
            try:
                info = book_info(book.path) if book.kind == "epub" else audio_info(book)
            except _BOOK_ERRORS:
                info = broken_info(book.path, book.kind)
            except Exception:
                info = broken_info(book.path, book.kind)
                stamp = _UNREAD
        entries.append({"path": book.path, "stamp": stamp, "info": info})
    # A folder gone during the walk, e.g. a card pulled out: what was seen
    # of it may be incomplete, so its books stay as they were.
    gone = tuple(folder for folder in walked if not os.path.isdir(folder))
    if gone:
        entries = ([e for e in entries if not e["path"].startswith(gone)]
                   + [e for e in known.values() if e["path"].startswith(gone)])
    changed = changed or {e["path"] for e in entries} != set(known)
    if changed:
        others = [e for e in cached if e["path"] not in known]
        _save_cache(cache_file, others + entries)
    return entries, changed


def _stamp(book):
    """[size, modification time] of the book's file, or None if it is not
    a regular file. For a folder the size of its files and a number made
    from their names, sizes and times: a renamed file changes no time."""
    try:
        if book.path in book.files or book.kind == "epub":
            st = os.stat(book.path)
            return [st.st_size, st.st_mtime_ns] if stat.S_ISREG(st.st_mode) else None
        size = 0
        digest = hashlib.sha1()
        for path in book.files:
            st = os.stat(path)
            size += st.st_size
            digest.update("{}\0{}\0{}\0".format(os.path.basename(path), st.st_size, st.st_mtime_ns)
                          .encode("utf-8", "surrogateescape"))
        return [size, int.from_bytes(digest.digest()[:7], "big")]
    except OSError:
        return None


def load_cached(cache_file):
    """The entries of the last scan, without looking at the books; [] if the
    cache file is missing or damaged."""
    try:
        with open(cache_file, "rb") as f:
            data = f.read(MAX_CACHE_SIZE + 1)
        if len(data) > MAX_CACHE_SIZE:
            return []
        stored = json.loads(data.decode("utf-8"))
    except (OSError, ValueError, RecursionError):
        return []
    if not isinstance(stored, dict) or stored.get("version") != _CACHE_VERSION:
        return []
    books = stored.get("books")
    return [entry for entry in books if _valid_entry(entry)] if isinstance(books, list) else []


def without_replaced(entries):
    """entries without the books that a readaloud of the same book replaces:
    same identifier, prefixes aside, and same title."""
    def key(info):
        return (normal_identifier(info["identifier"]), info["title"])

    narrated = {key(e["info"]) for e in entries
                if e["info"]["audio"] and e["info"]["identifier"]}
    return [e for e in entries
            if e["info"]["audio"] or not e["info"]["identifier"]
            or e["info"]["kind"] != "epub" or key(e["info"]) not in narrated]


def arranged(entries, roots=()):
    """The books as the library shows them: [(entry, info, partner)].

    A readaloud replaces its EPUB (see without_replaced) and with it the
    audiobook of that EPUB. An audiobook named like an EPUB beside it has
    that EPUB as partner and shows its title, authors and series. Another
    audiobook takes the author of the EPUBs beside it if they all have the
    same: its tags may name the author otherwise ("Timothy J. Keller" for
    "Keller, Timothy") or name the narrator. Not in the library folders
    roots themselves, which may hold anybody's books.
    """
    roots = {os.path.normpath(root) for root in roots}
    epubs = {e["path"]: e for e in entries if e["info"]["kind"] == "epub"}
    kept = without_replaced(entries)
    kept_paths = {e["path"] for e in kept}
    neighbours = collections.defaultdict(set)
    sorts = {}
    for e in epubs.values():
        folder = os.path.dirname(e["path"])
        authors = e["info"]["authors"]
        neighbours[folder].add(authors[0] if authors else "")
        sorts.setdefault(folder, e["info"]["sort"])
    result = []
    for entry in kept:
        info = entry["info"]
        if info["kind"] != "audiobook":
            result.append((entry, info, None))
            continue
        folder = os.path.dirname(entry["path"])
        partner = epubs.get(os.path.join(folder, _audiobook_name(entry["path"]) + ".epub"))
        if partner is not None:
            if partner["path"] not in kept_paths:
                continue
            p = partner["info"]
            info = dict(info, title=p["title"], authors=p["authors"], sort=p["sort"],
                        series=p["series"], index=p["index"])
        elif (len(neighbours.get(folder, ())) == 1 and "" not in neighbours[folder]
              and os.path.normpath(folder) not in roots):
            info = dict(info, authors=list(neighbours[folder]), sort=sorts[folder])
        result.append((entry, info, partner))
    return result


def _audiobook_name(path):
    stem, ext = os.path.splitext(os.path.basename(path))
    return stem if ext.lower() in _AUDIO_TYPES else os.path.basename(path)


def normal_identifier(identifier):
    identifier = identifier.strip().lower()
    stripped = True
    while stripped:
        stripped = False
        for prefix in _ID_PREFIXES:
            if identifier.startswith(prefix):
                identifier = identifier[len(prefix):]
                stripped = True
    return identifier


def extract_cover(epub_path, cover, target):
    """Copy the image cover (a path in the book) out of the EPUB to target.

    Returns False if there is no usable image; the library then shows none.
    """
    try:
        with _open_regular(epub_path) as f, zipfile.ZipFile(f) as archive:
            data = _member(archive, cover, MAX_COVER_SIZE)
    except Exception:
        return False
    if not _small_image(data):
        return False
    return _write_cover(data, target)


def _write_cover(data, target):
    tmp = target + ".part"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, target)
    except OSError:
        return False
    return True


def extract_audio_cover(path, cover, target):
    """Copy the cover of the audiobook at path (file or folder) to target:
    cover is a picture file in the folder or embedded.jpg/.png, the picture
    in the tags of the (first) file. Returns False if there is no usable
    image."""
    try:
        if cover in _EMBEDDED_COVERS:
            first = path if not os.path.isdir(path) else (audio_files(path) or [None])[0]
            if first is None:
                return False
            reader = mp4 if first.lower().endswith(".m4b") else mp3
            data = reader.picture(first)
        elif _FOLDER_COVER.fullmatch(cover) and os.path.isdir(path):
            with _open_regular(os.path.join(path, cover)) as f:
                data = f.read(MAX_COVER_SIZE + 1)
        else:
            return False
    except Exception:
        return False
    if (not data or len(data) > MAX_COVER_SIZE
            or picture_type(data) != os.path.splitext(cover)[1].lower().replace("jpeg", "jpg")[1:]
            or not _small_image(data)):
        return False
    return _write_cover(data, target)


def cover_name(entry):
    """File name stem of the entry's cover in the covers folder; changes when
    the book file changes."""
    data = "\0".join([entry["path"]] + [str(n) for n in entry["stamp"]])
    return hashlib.sha1(data.encode("utf-8", "surrogateescape")).hexdigest()[:16]


def prune_covers(covers_dir, names):
    """Remove the covers of books no longer in the library."""
    try:
        files = os.listdir(covers_dir)
    except OSError:
        return
    for name in files:
        match = _COVER_FILE.match(name)
        if match and match.group(1) not in names:
            try:
                os.remove(os.path.join(covers_dir, name))
            except OSError:
                pass


def _small_image(data):
    """False for PNG and GIF images larger than MAX_COVER_PIXELS a side."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
    elif data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        width, height = struct.unpack("<HH", data[6:10])
    else:
        return True
    return width <= MAX_COVER_PIXELS and height <= MAX_COVER_PIXELS


def _open_regular(path):
    """Open path for reading only if it is a regular file. Opened without
    blocking first: a FIFO put in place of a book would block forever."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise EpubError("not_epub", "not a regular file")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def _member(archive, name, max_size=MAX_XML_SIZE):
    """The content of name in the ZIP archive, with the limits used when
    books are unpacked: no encryption, only stored or deflated, no more than
    max_size bytes whatever the header claims."""
    try:
        info = archive.getinfo(name)
    except KeyError:
        raise EpubError("not_epub", "missing " + name)
    if info.flag_bits & 0x1 or info.compress_type not in (zipfile.ZIP_STORED,
                                                           zipfile.ZIP_DEFLATED):
        raise EpubError("not_epub", "unsupported entry " + name)
    if info.file_size > max_size:
        raise EpubError("too_large", name)
    with archive.open(info) as f:
        data = f.read(max_size + 1)
    if len(data) > max_size:
        raise EpubError("too_large", name)
    return data


def _save_cache(cache_file, entries):
    directory = os.path.dirname(cache_file)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = cache_file + ".tmp"
    try:
        # ASCII escapes also cover file names that are not valid UTF-8.
        with open(tmp, "w", encoding="ascii") as f:
            json.dump({"version": _CACHE_VERSION, "books": entries}, f)
        os.replace(tmp, cache_file)
    except OSError:
        pass  # without a cache the books are read again next time


def _valid_entry(entry):
    if not (isinstance(entry, dict) and isinstance(entry.get("path"), str)
            and isinstance(entry.get("stamp"), list) and len(entry["stamp"]) == 2
            and all(isinstance(n, int) for n in entry["stamp"])
            and isinstance(entry.get("info"), dict)):
        return False
    info = entry["info"]
    return (all(isinstance(info.get(field), kind) for field, kind in _INFO_FIELDS.items())
            and info["kind"] in _KINDS
            and all(isinstance(a, str) for a in info["authors"])
            and (info["index"] is None or math.isfinite(info["index"])))
