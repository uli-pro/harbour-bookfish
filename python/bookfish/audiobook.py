"""An audiobook opened for listening: its chapters in order, each with the
file it is in, where in the file it begins and how long it is.

A single file (MP3 or M4B) has the chapter marks of its tags, or is one
chapter. In a folder each MP3 file is a chapter; their own marks are not
read, as they often belong to the whole book. Reading hundreds of files
from a memory card took up to a minute on the device (single reads hang for
seconds), so a folder opens at once with lengths estimated from the file
sizes and names from the files; the tags are read afterwards and kept in a
cache, which is used as long as no file has changed.
"""

import hashlib
import os

from . import jsonfile, mp3, mp4
from .audioutil import AudioError, chapter_list
from .library import audio_files

MAX_CACHE_SIZE = 4 * 1024 * 1024
_CACHE_VERSION = 1
# When not even the first file of a folder can be read: 128 kbit/s, usual
# for audiobooks.
_FALLBACK_BYTES_PER_MS = 16


def open_audiobook(path, cache_dir, files=None):
    """The audiobook at path, a file or a folder: {root, chapters, duration,
    complete}. files are the audio files of an album in a folder (see
    library.album_files); path then names that album.

    root is the folder of the audio files. chapters are in order, each
    {title, file, begin, end, length, start}: file is the name of its audio
    file in root, begin and end the place in that file in ms (end None: to
    the end of the file), length its duration and start where it begins in
    the whole book. title is "" if the tags have none. duration is the sum
    of all lengths. complete is false for a folder not read yet: lengths are
    estimates and titles file names until read_folder has read the files.

    Raises AudioError if there is nothing to play, OSError if the files
    cannot be read.
    """
    if files is None and not os.path.isdir(path):
        info = _read(path, True)
        return _assemble(os.path.dirname(path), [os.path.basename(path)], [info], True, True)
    root, files = _files(path, files)
    stamps = _stamps(files)
    cached = _load_cache(_cache_file(cache_dir, path), stamps)
    if cached is not None:
        return _assemble(root, _names(files), cached, False, True)
    return _assemble(root, _names(files), _estimated(files, stamps), False, False)


def read_folder(path, cache_dir, files=None):
    """The audiobook folder at path as open_audiobook gives it, with every
    file read; the result is kept in the cache. A file that cannot be read
    is a chapter of unknown length named by the file."""
    root, files = _files(path, files)
    stamps = _stamps(files)
    infos = []
    for file in files:
        try:
            infos.append(_read(file, False))
        except Exception:
            # Whatever is wrong with one file, the others are read; an
            # error here would leave the folder unread at every opening.
            infos.append({"title": "", "duration": None})
    _save_cache(_cache_file(cache_dir, path), stamps, infos)
    return _assemble(root, _names(files), infos, False, True)


def _files(path, files):
    """(folder, files) of the audiobook at path: the given files of an
    album, else those of the folder path."""
    if files is None:
        files = audio_files(path)
    if not files:
        raise AudioError("not_audio", "no audio files")
    return os.path.dirname(files[0]), list(files)


def _names(files):
    return [os.path.basename(file) for file in files]


def _stamps(files):
    """[name, size, modification time] of each file: the cache is used only
    if all are the same."""
    stamps = []
    for file in files:
        st = os.stat(file)
        stamps.append([os.path.basename(file), st.st_size, st.st_mtime_ns])
    return stamps


def _read(file, chapters):
    reader = mp4 if file.lower().endswith(".m4b") else mp3
    tags = reader.read(file, chapters)
    info = {"title": tags["title"], "duration": tags["duration"]}
    if chapters:
        info["chapters"] = tags["chapters"]
    return info


def _estimated(files, stamps):
    """Lengths from the file sizes at the rate of the first file, which is
    exact for files of one constant bitrate; names from the files. The tag
    of the first file is taken off every file: the files of a folder
    usually carry the same picture, which may be larger than a short
    first file's audio."""
    try:
        first = _read(files[0], False)["duration"]
        tag = _tag_size(files[0])
    except (AudioError, OSError):
        first, tag = None, 0
    audio = stamps[0][1] - tag
    if not first or audio <= 0:
        tag, per_ms = 0, _FALLBACK_BYTES_PER_MS
    else:
        per_ms = audio / first
    return [{"title": "", "duration": int(max(0, stamp[1] - tag) / per_ms)} for stamp in stamps]


def _tag_size(file):
    """The size of the ID3v2 tag at the start of file, 0 if there is none."""
    with open(file, "rb") as f:
        head = f.read(10)
    if len(head) < 10 or head[:3] != b"ID3" or any(b & 0x80 for b in head[6:10]):
        return 0
    size = (head[6] << 21) | (head[7] << 14) | (head[8] << 7) | head[9]
    return 10 + size + (10 if head[5] & 0x10 else 0)


def _assemble(root, names, infos, single, complete):
    chapters = []
    start = 0
    for name, info in zip(names, infos):
        duration = info["duration"]
        marks = chapter_list(info.get("chapters", []), duration) if single else []
        if not marks:
            # One chapter for the file: in a folder named by its tag or the
            # file; a single file without marks has the book's title.
            title = "" if single else info["title"] or os.path.splitext(name)[0]
            marks = [(0, None, title)]
        for begin, end, title in marks:
            length = max(0, (end if end is not None else duration or 0) - begin)
            chapters.append({"title": title, "file": name, "begin": begin, "end": end,
                             "length": length, "start": start})
            start += length
    return {"root": root, "chapters": chapters, "duration": start, "complete": complete}


def _cache_file(cache_dir, path):
    name = hashlib.sha1(path.encode("utf-8", "surrogateescape")).hexdigest()[:16]
    return os.path.join(cache_dir, name + ".json")


def _load_cache(cache_file, stamps):
    """The infos of the files if the cache holds them for these stamps."""
    stored = jsonfile.read(cache_file, MAX_CACHE_SIZE)
    if (not isinstance(stored, dict) or stored.get("version") != _CACHE_VERSION
            or stored.get("stamps") != stamps):
        return None
    files = stored.get("files")
    if not isinstance(files, list) or len(files) != len(stamps):
        return None
    infos = []
    for info in files:
        if not isinstance(info, dict):
            return None
        title = info.get("title")
        duration = info.get("duration")
        if (not isinstance(title, str) or len(title) > 1000
                or not (duration is None or isinstance(duration, int)
                        and not isinstance(duration, bool) and duration >= 0)):
            return None
        infos.append({"title": title, "duration": duration})
    return infos


def _save_cache(cache_file, stamps, infos):
    try:
        jsonfile.write(cache_file, {"version": _CACHE_VERSION, "stamps": stamps,
                                    "files": [{"title": i["title"], "duration": i["duration"]}
                                              for i in infos]})
    except OSError:
        pass  # without a cache the folder is read again next time
