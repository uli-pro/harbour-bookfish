"""Media overlays (SMIL): which sentence is spoken when."""

import collections
import re

from .errors import EpubError
from .paths import local_path, resolve
from .xmlutil import parse_xml

_SMIL = "{http://www.w3.org/ns/SMIL}"

# Times are whole milliseconds, like QML Audio.position, so comparisons such
# as begin <= position are exact.
Fragment = collections.namedtuple(
    "Fragment", "text_path text_id audio_path begin end")
Fragment.__doc__ = "One sentence; end None means: to the end of the file."

# Digit counts are bounded so huge numbers cannot overflow float or make
# int() slow; nine digits of hours or seconds are far beyond any book.
_CLOCK = re.compile(r"^(?:([0-9]{1,6}):)?([0-5][0-9]):"
                    r"([0-5][0-9](?:\.[0-9]{1,9})?)$")
_TIMECOUNT = re.compile(r"^([0-9]{1,9}(?:\.[0-9]{1,9})?)(h|min|s|ms)?$")
_UNIT_MS = {"h": 3600000, "min": 60000, "s": 1000, "ms": 1, None: 1000}
MAX_TIME = 2 ** 31 - 1


def parse_clock(text):
    """Return a SMIL clock value in milliseconds.

    Accepts full clocks (01:40:08.79), partial clocks (21:58.97) and
    timecounts (17.780s, 500ms, 2.5min, 1h, 17.78).
    """
    text = text.strip()
    match = _CLOCK.match(text)
    if match:
        hours, minutes, seconds = match.groups()
        total = int(hours or 0) * 3600 + int(minutes) * 60 + float(seconds)
        return int(round(total * 1000))
    match = _TIMECOUNT.match(text)
    if match:
        value, unit = match.groups()
        return int(round(float(value) * _UNIT_MS[unit]))
    raise ValueError("bad clock value: " + text)


def read_overlay(root, smil_path):
    """Read the SMIL file smil_path of the book unpacked at root.

    Sentences that cannot be played are skipped and counted in
    Overlay.skipped; references leaving the book still raise EpubError.
    """
    try:
        doc = parse_xml(local_path(root, smil_path))
    except OSError:
        raise EpubError("bad_overlay", "missing " + smil_path)
    fragments = []
    skipped = 0
    for par in doc.iter(_SMIL + "par"):
        fragment = _read_par(par, smil_path)
        if fragment is None:
            skipped += 1
        else:
            fragments.append(fragment)
    if not fragments:
        raise EpubError("bad_overlay", "{}: no fragments".format(smil_path))
    return Overlay(fragments, skipped)


def _read_par(par, smil_path):
    """Return the Fragment for one <par>, or None if it cannot be played."""
    text = par.find(_SMIL + "text")
    audio = par.find(_SMIL + "audio")
    if text is None or audio is None or not audio.get("src"):
        return None
    target = resolve(smil_path, text.get("src", ""))
    sound = resolve(smil_path, audio.get("src"))
    if not target or not target[1] or not sound:
        return None
    # Aligners make mistakes: Storyteller gave one unread sentence of 4359
    # in a real book an end before its begin. Losing one sentence is better
    # than losing the chapter.
    try:
        begin = parse_clock(audio.get("clipBegin", "0"))
        end = audio.get("clipEnd")
        end = parse_clock(end) if end is not None else None
    except ValueError:
        return None
    if end is not None and end <= begin:
        return None
    # QML keeps times in 32-bit ints; nearly 600 hours is beyond any book.
    if max(begin, end or 0) > MAX_TIME:
        return None
    return Fragment(target[0], target[1], sound[0], begin, end)


class Overlay(object):
    """The sentences of one chapter in reading order.

    skipped counts the sentences of the SMIL file that could not be played.
    """

    def __init__(self, fragments, skipped=0):
        self.fragments = list(fragments)
        self.skipped = skipped
