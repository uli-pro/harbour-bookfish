"""Helpers shared by the audio file readers."""

import os
import re
import stat

from .errors import EpubError

MAX_TEXT_LENGTH = 500
_CONTROL = re.compile("[\x00-\x1f\x7f]+")
_NUMBER = re.compile(r"(\d+)")
_PART = re.compile(r"\d{1,6}(\.\d{1,3})?")


class AudioError(EpubError):
    """An audio file cannot be used; code "not_audio"."""


def open_regular(path):
    """Open path for reading only if it is a regular file. Opened without
    blocking first: a FIFO put in place of a file would block forever."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise AudioError("not_audio", "not a regular file")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def read_exact(f, size):
    data = f.read(size)
    if len(data) != size:
        raise AudioError("not_audio", "file ends early")
    return data


def clean_text(text):
    """text from a tag for display: control characters out, at most
    MAX_TEXT_LENGTH characters."""
    return _CONTROL.sub(" ", text).strip()[:MAX_TEXT_LENGTH].strip()


def series(name, part, movement, movement_part):
    """(name, index) of the series from the tags SERIES and SERIES-PART,
    else from iTunes' movement tags; ("", None) without either. index is
    None if the part is no plain number ("1-3")."""
    for found, number in ((name, part), (movement, movement_part)):
        found = clean_text(found)
        if found:
            # MVIN may say "3/7".
            number = number.split("/")[0].strip()
            return found, float(number) if _PART.fullmatch(number) else None
    return "", None


def picture_type(data):
    """ "jpg" or "png" by the first bytes of data, else None."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    return None


def natural_key(name):
    """Sort key putting "part-2" before "part-10": numbers by value, the
    rest without regard to case."""
    parts = _NUMBER.split(name.casefold())
    return [(0, int(part), part) if i % 2 else (1, 0, part) for i, part in enumerate(parts)]


def chapter_list(marks, duration):
    """Chapters [(begin, end, title)] in ms from marks [(begin, title)] as
    found in a file: sorted, within the file, each ending where the next
    begins, the last with end None (the end of the file). The first begins
    at 0, so nothing before it is without a chapter. [] if no mark is
    usable."""
    begins = {}
    for begin, title in marks:
        if begin < 0 or (duration is not None and begin >= duration):
            continue
        begins.setdefault(begin, title)
    order = sorted(begins)
    chapters = []
    for i, begin in enumerate(order):
        end = order[i + 1] if i + 1 < len(order) else None
        chapters.append((0 if i == 0 else begin, end, begins[begin]))
    return chapters
