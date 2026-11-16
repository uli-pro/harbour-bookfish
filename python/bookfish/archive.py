"""Safe extraction of an EPUB into a directory."""

import os
import shutil
import stat
import zipfile
import zlib

from .errors import EpubError

# Limits against zip bombs that do not cap the length of a book. Audio barely
# compresses, so a real readaloud unpacks to about the size of the EPUB file
# (The Happy Prince: 100 MB -> 101 MB); a zip bomb unpacks to thousands of
# times its size. The headroom covers text-heavy books whose XHTML compresses
# well. Long audiobooks are large but legitimate (51 h at 64 kbit/s = 1.5 GB),
# so the real risk is filling the phone: keep MIN_FREE_SPACE free afterwards.
MAX_ENTRIES = 10000
# zipfile turns the whole central directory into objects before anything can
# be checked: 1 million entries took 550 MB. 10000 entries with long names
# need about 1 MB.
MAX_DIRECTORY = 16 * 1024 * 1024
MAX_RATIO = 2
HEADROOM = 100 * 1024 * 1024
MIN_FREE_SPACE = 500 * 1024 * 1024

# Each directory we create costs a block on disk; counting it keeps archives
# of empty nested directories within the limits as well.
_DIRECTORY_COST = 4096
_MAX_NAME_LENGTH = 1024
_MAX_PART_BYTES = 255
_CHUNK = 64 * 1024
_MIMETYPE = b"application/epub+zip"
# The only methods the EPUB container format allows. zipfile does not bound
# the memory of its bzip2 and LZMA decoders, so refusing them is also a
# defence against memory bombs.
_COMPRESSION = (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
# What zipfile raises while reading damaged archives: OSError for bad
# offsets, ValueError for undecodable names, NotImplementedError for unknown
# format versions. Errors while writing are not caught and pass through.
_CORRUPT = (zipfile.BadZipFile, zlib.error, EOFError, ValueError, OSError,
            NotImplementedError)


def extract(epub_path, dest_dir, max_entries=MAX_ENTRIES, max_ratio=MAX_RATIO,
            headroom=HEADROOM, min_free_space=MIN_FREE_SPACE):
    """Unpack the EPUB at epub_path into dest_dir, which must not exist.

    Unpacks into dest_dir + ".part" first and renames it at the end, so an
    interrupted extraction never looks like a complete one. Raises EpubError
    for unusable archives and OSError if epub_path cannot be opened or
    writing fails.
    """
    if os.path.lexists(dest_dir):
        raise ValueError("destination exists: " + dest_dir)
    with open(epub_path, "rb") as f:
        epub_size = os.fstat(f.fileno()).st_size
        archive = open_zip(f, max_entries)
        with archive:
            infos = archive.infolist()
            if len(infos) > max_entries:
                raise EpubError("too_many_files", str(len(infos)))
            for info in infos:
                if info.compress_type not in _COMPRESSION:
                    raise EpubError("not_epub", "compression of " + info.filename)
                if info.flag_bits & 0x1:
                    raise EpubError("not_epub", "encrypted " + info.filename)
            _check_mimetype(archive)
            max_size = max_ratio * epub_size + headroom
            declared = sum(info.file_size for info in infos)
            if declared > max_size:
                raise EpubError("too_large", str(declared))
            parent = os.path.dirname(os.path.abspath(dest_dir))
            _check_space(parent, declared, min_free_space)

            tmp_dir = dest_dir + ".part"
            _remove(tmp_dir)
            os.mkdir(tmp_dir)
            try:
                _Extractor(archive, tmp_dir, max_size, min_free_space).run(infos)
                os.rename(tmp_dir, dest_dir)
            except BaseException:
                _remove(tmp_dir)
                raise


def open_zip(f, max_entries=MAX_ENTRIES):
    """zipfile.ZipFile for the open binary file f, after checking the size
    of its central directory in the end record. Raises EpubError."""
    try:
        end = zipfile._EndRecData(f)
    except _CORRUPT:
        end = None
    # Entries total and size of the central directory, see zipfile._ECD_*.
    if end is not None and (end[4] > max_entries or end[5] > MAX_DIRECTORY):
        raise EpubError("too_many_files", str(end[4]))
    try:
        f.seek(0)
        return zipfile.ZipFile(f)
    except _CORRUPT as e:
        raise EpubError("not_zip", str(e))


def _check_mimetype(archive):
    try:
        info = archive.getinfo("mimetype")
    except KeyError:
        raise EpubError("not_epub", "no mimetype")
    try:
        with archive.open(info) as f:
            content = f.read(len(_MIMETYPE) + 2)
    except _CORRUPT as e:
        raise EpubError("not_zip", str(e))
    if content.strip() != _MIMETYPE:
        raise EpubError("not_epub", "wrong mimetype")


def _check_space(directory, needed, min_free_space):
    if shutil.disk_usage(directory).free - needed < min_free_space:
        raise EpubError("no_space", "{} bytes needed".format(needed))


class _Extractor(object):

    def __init__(self, archive, root, max_size, min_free_space):
        self.archive = archive
        self.root = root
        self.max_size = max_size
        self.min_free_space = min_free_space
        self.written = 0
        self.names = set()
        self.directories = set()

    def run(self, infos):
        for info in infos:
            name = _safe_name(info.filename)
            if stat.S_ISLNK(info.external_attr >> 16):
                continue
            if not name:
                if info.is_dir():
                    continue
                raise EpubError("unsafe_path", info.filename)
            if name in self.names:
                raise EpubError("unsafe_path", "duplicate " + info.filename)
            self.names.add(name)
            parts = name.split("/")
            try:
                if info.is_dir():
                    self._make_directories(parts)
                else:
                    self._make_directories(parts[:-1])
                    self._write_file(info, os.path.join(self.root, *parts))
            except (FileExistsError, NotADirectoryError, IsADirectoryError):
                # A file and a directory with the same name.
                raise EpubError("unsafe_path", info.filename)

    def _make_directories(self, parts):
        # One level at a time: os.makedirs recurses and its cost is unknown.
        for depth in range(1, len(parts) + 1):
            relative = "/".join(parts[:depth])
            if relative in self.directories:
                continue
            self._count(_DIRECTORY_COST, relative)
            os.mkdir(os.path.join(self.root, *parts[:depth]))
            self.directories.add(relative)

    def _write_file(self, info, target):
        _check_space(self.root, info.file_size, self.min_free_space)
        # Mode "xb" never overwrites, and permissions from the archive are
        # ignored on purpose.
        with self._open(info) as src, open(target, "xb") as dst:
            while True:
                try:
                    chunk = src.read(_CHUNK)
                except _CORRUPT as e:
                    raise EpubError("not_zip", "{}: {}".format(info.filename, e))
                if not chunk:
                    break
                # zipfile stops at the declared size; counting ourselves
                # keeps the limit should that ever change.
                self._count(len(chunk), info.filename)
                dst.write(chunk)

    def _open(self, info):
        try:
            return self.archive.open(info)
        except _CORRUPT as e:
            raise EpubError("not_zip", "{}: {}".format(info.filename, e))

    def _count(self, size, name):
        self.written += size
        if self.written > self.max_size:
            raise EpubError("too_large", name)


def _safe_name(name):
    """Return name as a clean relative path, or raise for unsafe names."""
    if (not name or len(name) > _MAX_NAME_LENGTH or name.startswith("/")
            or "\\" in name or ":" in name or "\0" in name):
        raise EpubError("unsafe_path", name[:100])
    parts = [p for p in name.split("/") if p not in ("", ".")]
    for part in parts:
        if part == ".." or len(part.encode("utf-8")) > _MAX_PART_BYTES:
            raise EpubError("unsafe_path", name[:100])
    return "/".join(parts)


def _remove(path):
    if os.path.islink(path) or os.path.isfile(path):
        os.remove(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)
