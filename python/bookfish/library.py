"""Finding the books in the library folders and what the library shows
of them, kept in a cache file so that a memory card is not read again.

A book is an EPUB file or an audiobook. An audiobook is an M4B file, an MP3
file beside EPUBs (an author's folder holding several books) or in a library
folder itself, or a folder of MP3 files without EPUBs, each file a chapter.
If the files of such a folder name two albums or more, each album is an
audiobook, and each file without an album. An audiobook named like an
EPUB beside it is that book read aloud: it shows the EPUB's title, author,
series and cover. Another audiobook takes its series from its tags.
"""

import collections
import hashlib
import json
import math
import os
import re
import stat
import struct
import unicodedata
import zipfile

from . import mp3, mp4
from .archive import open_zip
from .audioutil import AudioError, natural_key, picture_type
from .errors import EpubError
from .package import check_encryption, package_path, read_info
from .xmlutil import MAX_XML_SIZE, parse_xml_data

MAX_CACHE_SIZE = 16 * 1024 * 1024
MAX_COVER_SIZE = 5 * 1024 * 1024
# Folders below the library folder; far deeper than any library.
MAX_DEPTH = 32
# PNG and GIF are decoded at full size before they are scaled down; a small
# file can hold a huge image. JPEG is decoded scaled.
MAX_COVER_PIXELS = 4096
# Raised whenever what is read from a book changes, so that all are read again.
_CACHE_VERSION = 6
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

# Joins folder and album in the path of an album's audiobook (see
# album_path); no path walked has two slashes in a row.
_ALBUM_SEP = "//"

BookFile = collections.namedtuple("BookFile", "path name kind files album",
                                  defaults=("epub", (), ""))
BookFile.__doc__ = """A book found: path of the EPUB or audio file, or of
the folder of an audiobook, or an album_path; name is the file name without
extension or the folder or album name; kind "epub" or "audiobook"; files the
audio files in order; album the title of an album in a folder of several,
else ""."""


def album_key(album):
    """album as albums are told apart: any case, spacing and Unicode form,
    and "/" taken as a space, which would end the album path's folder."""
    album = unicodedata.normalize("NFC", album)
    return " ".join(album.replace("/", " ").split()).casefold()


def album_path(folder, key):
    """The path that names the audiobook of the album key (see album_key) in
    folder: kept with positions and history like a file's."""
    return folder + _ALBUM_SEP + key


def split_album(path):
    """(folder, key) of an album_path; (path, None) for other paths."""
    folder, sep, key = path.rpartition(_ALBUM_SEP)
    return (folder, key) if sep and folder and key and "/" not in key else (path, None)


def exists(path):
    """Whether the book at path is still there: a file, a folder, or the
    folder of an album."""
    return os.path.exists(split_album(path)[0])


def list_books(folders, albums=None):
    """Return the books below folders (see BookFile), sorted by name.

    albums(files) gives the album tag of each of files, or None if they
    cannot all be read; it is asked for each folder of MP3 files without
    EPUBs, to tell the audiobooks in it apart (see _folder_books). Without
    it each such folder is one audiobook.

    Hidden files and folders are left out, and folders deeper than MAX_DEPTH.
    Symbolic links to folders are not followed, so a link cannot make the
    walk endless. Missing folders are
    ignored, and so are names that are not valid UTF-8: QML could not show
    or open them.
    """
    books = []
    seen = set()
    for folder in folders:
        # "Lib//" would walk "Lib//Book", taken for an album path.
        folder = os.path.normpath(folder)
        for dirpath, dirnames, filenames in os.walk(folder):
            # os.walk recurses before Python 3.12: 1000 levels raised
            # RecursionError on Sailfish OS, and no book was listed.
            if dirpath[len(folder):].count(os.sep) >= MAX_DEPTH:
                dirnames[:] = []
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
                books.extend(_folder_books(dirpath, mp3s, albums))
    books.sort(key=lambda book: (book.name.casefold(), book.path))
    return books


def _folder_books(folder, files, albums):
    """The audiobooks in folder, which holds the MP3 files files (in order)
    and no EPUBs. One audiobook, unless the files name two albums or more
    (see album_key): then each album is one, its files in order, and each
    file without an album. An album of one file is that file, like an MP3
    beside EPUBs, with its own chapter marks. An album is titled as most of
    its files name it."""
    whole = [BookFile(folder, os.path.basename(folder), "audiobook", tuple(files))]
    names = albums(files) if albums is not None and len(files) > 1 else None
    if names is None:
        return whole
    keys = [album_key(name) for name in names]
    if len(set(keys) - {""}) < 2:
        return whole
    groups = collections.OrderedDict()
    books = []
    for path, name, key in zip(files, names, keys):
        if key:
            groups.setdefault(key, []).append((path, name))
        else:
            books.append(BookFile(path, _stem(path), "audiobook", (path,)))
    for key, members in groups.items():
        spellings = collections.Counter(name for _, name in members)
        # On a tie the spelling of the first file.
        title = max(spellings, key=lambda name: spellings[name])
        paths = tuple(path for path, _ in members)
        if len(paths) == 1:
            books.append(BookFile(paths[0], _stem(paths[0]), "audiobook", paths, title))
        else:
            books.append(BookFile(album_path(folder, key), title, "audiobook", paths, title))
    return books


def _stem(path):
    return os.path.splitext(os.path.basename(path))[0]


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
    with _open_regular(path) as f, open_zip(f) as archive:
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
    if book.album:
        title = book.album
    elif len(book.files) == 1 and book.path == first:
        # Audible files have the title in one and the title plus
        # "(Unabridged)" or a subtitle in the other, in either order.
        names = [name for name in (tags["title"], tags["album"]) if name]
        title = min(names, key=len) if names else ""
    else:
        title = tags["album"]
    series, index = tags["series"], tags["series_index"]
    title = _without_series(title, series, index)
    author = tags["albumartist"] or tags["artist"]
    cover = None
    # A picture beside the files belongs to the folder, not to one album.
    if book.path != first and not book.album:
        cover = next((name for name in sorted(os.listdir(book.path))
                      if _FOLDER_COVER.fullmatch(name)), None)
    if cover is None and tags["picture"]:
        cover = "embedded." + tags["picture"]
    return {"identifier": "", "title": title or book.name, "authors": [author] if author else [],
            "sort": "", "series": series, "index": index, "cover": cover, "audio": False,
            "broken": False, "kind": "audiobook"}


def _without_series(title, series, index):
    """title without a leading "<series> <index> – ", which the library
    shows as the heading and "Book <index>" already. Also with "-", "—" or
    ":"; the rest of the title must remain."""
    if not series or index is None:
        return title
    number = re.escape(("%.3f" % index).rstrip("0").rstrip(".")).replace(r"\.", "[.,]")
    match = re.match(re.escape(series) + r"\s+0*" + number + r"(?:\s*[-–—]\s+|\s*:\s+)(\S.*)",
                     title, re.IGNORECASE)
    return match.group(1) if match else title


def broken_info(path, kind="epub", name=None):
    """The entry of a book that cannot be read: listed by name, else by its
    file or folder name, so that opening it explains what is wrong."""
    if name is None:
        name = os.path.basename(path)
        if not os.path.isdir(path):
            name = os.path.splitext(name)[0]
    return {"identifier": "", "title": name,
            "authors": [], "sort": "", "series": "", "index": None, "cover": None,
            "audio": False, "broken": True, "kind": kind}


def scan(folders, cache_file):
    """All books below folders, EPUBs and audiobooks, as ([{path, stamp,
    info}], changed).

    Only files that are new or changed since the cache file was written are
    read; reading every book from a memory card took 93 s on the device.
    The cache keeps the books of other folders and of folders that are
    missing now, e.g. a memory card taken out. changed is false if the
    entries are those of the cache.
    """
    folders = [os.path.normpath(folder) for folder in folders]
    stored = _load_store(cache_file)
    cached = stored["books"]
    walked = tuple(os.path.join(folder, "") for folder in folders if os.path.isdir(folder))
    known = {e["path"]: e for e in cached if e["path"].startswith(walked)}
    albums = _Albums(stored["albums"])
    entries = []
    changed = False
    for book in list_books(folders, albums):
        stamp = _stamp(book)
        if stamp is None:
            continue
        old = known.get(book.path)
        # A file titled by its album is titled otherwise beside EPUBs.
        if (old is not None and old["stamp"] == stamp and old["info"]["kind"] == book.kind
                and old.get("album", "") == book.album):
            info = old["info"]
        else:
            changed = True
            try:
                info = book_info(book.path) if book.kind == "epub" else audio_info(book)
            except _BOOK_ERRORS:
                info = broken_info(book.path, book.kind, book.name)
            except Exception:
                info = broken_info(book.path, book.kind, book.name)
                stamp = _UNREAD
        entry = {"path": book.path, "stamp": stamp, "info": info}
        if book.album:
            entry["album"] = book.album
        entries.append(entry)
    # A folder gone during the walk, e.g. a card pulled out: what was seen
    # of it may be incomplete, so its books stay as they were.
    gone = tuple(folder for folder in walked if not os.path.isdir(folder))
    if gone:
        entries = ([e for e in entries if not e["path"].startswith(gone)]
                   + [e for e in known.values() if e["path"].startswith(gone)])
    changed = changed or {e["path"] for e in entries} != set(known)
    kept = tuple(set(walked) - set(gone))
    album_tags = {folder: tag for folder, tag in stored["albums"].items()
                  if not folder.startswith(kept)}
    album_tags.update((folder, tag) for folder, tag in albums.read.items()
                      if not folder.startswith(gone))
    if changed or album_tags != stored["albums"]:
        others = [e for e in cached if e["path"] not in known]
        _save_cache(cache_file, others + entries, album_tags)
    return entries, changed


class _Albums:
    """The album tags of the MP3 files of a folder (see list_books), read
    once and kept per folder with its stamp: tags read from a memory card
    again at every start would take long. Of a folder of one album only
    that is kept, as [] for its names."""

    def __init__(self, cached):
        self.cached = cached
        self.read = {}

    def __call__(self, files):
        folder = os.path.dirname(files[0])
        stamp = _stamp(BookFile(folder, "", "audiobook", tuple(files)))
        if stamp is None:
            return None
        old = self.cached.get(folder)
        if old is not None and old[:2] == stamp:
            names = old[2]
        else:
            names = []
            for path in files:
                try:
                    names.append(mp3.album(path))
                except (AudioError, ValueError):
                    names.append("")  # an unusable file: a book of its own, as it says why
                except OSError:
                    # Maybe a card that hangs: not split this time, read again next time.
                    return None
            if len({album_key(name) for name in names} - {""}) < 2:
                names = []
        self.read[folder] = stamp + [names]
        return names or [""] * len(files)


def album_files(path, cache_file=None):
    """The files of the audiobook at the album_path path, in order, as
    list_books finds them; the album tags known from the cache file are not
    read again. Raises OSError if the tags cannot be read."""
    folder, key = split_album(path)
    files = audio_files(folder)
    names = _Albums(_load_store(cache_file)["albums"] if cache_file else {})(files)
    if names is None:
        raise OSError("cannot read the album tags in " + folder)
    return [file for file, name in zip(files, names) if album_key(name) == key]


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
    return _load_store(cache_file)["books"]


def _load_store(cache_file):
    """{books, albums}: the entries and the album tags by folder (see
    _Albums) of the last scan. Album tags came later than the cache version, so a cache
    without them is still used."""
    empty = {"books": [], "albums": {}}
    try:
        with open(cache_file, "rb") as f:
            data = f.read(MAX_CACHE_SIZE + 1)
        if len(data) > MAX_CACHE_SIZE:
            return empty
        stored = json.loads(data.decode("utf-8"))
    except (OSError, ValueError, RecursionError):
        return empty
    if not isinstance(stored, dict) or stored.get("version") != _CACHE_VERSION:
        return empty
    books, albums = stored.get("books"), stored.get("albums")
    return {"books": ([entry for entry in books if _valid_entry(entry)]
                      if isinstance(books, list) else []),
            "albums": ({path: tag for path, tag in albums.items() if _valid_album(tag)}
                       if isinstance(albums, dict) else {})}


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
        with _open_regular(epub_path) as f, open_zip(f) as archive:
            data = _member(archive, cover, MAX_COVER_SIZE)
    except Exception:
        return False
    if not small_image(data):
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
            if split_album(path)[1] is not None:
                files = album_files(path)
            else:
                files = audio_files(path) if os.path.isdir(path) else [path]
            first = (files or [None])[0]
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
            or not small_image(data)):
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


def small_image(data):
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


def _save_cache(cache_file, entries, albums=None):
    directory = os.path.dirname(cache_file)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = cache_file + ".tmp"
    try:
        # ASCII escapes also cover file names that are not valid UTF-8.
        with open(tmp, "w", encoding="ascii") as f:
            json.dump({"version": _CACHE_VERSION, "books": entries, "albums": albums or {}}, f)
        os.replace(tmp, cache_file)
    except OSError:
        pass  # without a cache the books are read again next time


def _valid_album(tag):
    return (isinstance(tag, list) and len(tag) == 3 and all(isinstance(n, int) for n in tag[:2])
            and isinstance(tag[2], list) and all(isinstance(name, str) for name in tag[2]))


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
