"""What an M4B (MPEG-4 audio) file says about itself: duration, Nero
chapters (chpl), tags, series and cover from the iTunes item list.

An MPEG-4 file is a tree of boxes ("atoms"), each with a size and a type.
Only the boxes needed are visited; the sample tables (trak) and the audio
(mdat) are passed over by seeking. Every size is checked against the box
around it, so a broken file ends the reading instead of looping.
"""

import struct

from . import audioutil
from .audioutil import AudioError, clean_text, open_regular, picture_type, read_exact

MAX_BOXES = 10000
MAX_BOX_READ = 1024 * 1024
MAX_PICTURE = 5 * 1024 * 1024
# Nero chapters count in a single byte; QuickTime chapter tracks, which
# can hold more, are not read. The largest book seen had 250 chapters.
_CHPL_UNIT = 10000  # 100 ns per unit, 10000 per ms

_ITEMS = {b"\xa9nam": "title", b"\xa9alb": "album", b"\xa9ART": "artist",
          b"aART": "albumartist"}
# Free-form items ("----") of iTunes by name (any case), and the movement.
_SERIES = {"SERIES": "series", "SERIES-PART": "part"}
_ITUNES = "com.apple.iTunes"
_MOVEMENT_NAME = b"\xa9mvn"
_MOVEMENT_PART = b"\xa9mvi"


def read(path, chapters=True):
    """{title, album, artist, albumartist, series, series_index, picture,
    duration, chapters} like mp3.read. Raises AudioError if the file is no MPEG-4 file, OSError if it
    cannot be read."""
    with open_regular(path) as f:
        boxes = _Boxes(f)
        moov = boxes.find_top(b"moov")
        info = {"title": "", "album": "", "artist": "", "albumartist": "", "picture": None,
                "duration": None, "chapters": []}
        series = {"series": "", "part": "", "movement": "", "movement_part": ""}
        mvhd = boxes.child(moov, b"mvhd")
        if mvhd is not None:
            info["duration"] = _duration(boxes.read(mvhd, 32))
        udta = boxes.child(moov, b"udta")
        if udta is not None:
            if chapters:
                chpl = boxes.child(udta, b"chpl")
                if chpl is not None:
                    info["chapters"] = _chapters(boxes.read(chpl, MAX_BOX_READ))
            ilst = _item_list(boxes, udta)
            if ilst is not None:
                for box in boxes.children(ilst):
                    name = _ITEMS.get(box[0])
                    if name is not None and not info[name]:
                        data = _data(boxes, box)
                        if data is not None and data[0] == 1:
                            info[name] = clean_text(data[1].decode("utf-8", errors="replace"))
                    elif box[0] == b"covr" and info["picture"] is None:
                        info["picture"] = _picture_kind(boxes, box)
                    elif box[0] in (b"----", _MOVEMENT_NAME, _MOVEMENT_PART):
                        _series_item(boxes, box, series)
        info["series"], info["series_index"] = audioutil.series(
            series["series"], series["part"], series["movement"], series["movement_part"])
    return info


def picture(path):
    """The bytes of the cover in the file's tags, or None."""
    with open_regular(path) as f:
        boxes = _Boxes(f)
        udta = boxes.child(boxes.find_top(b"moov"), b"udta")
        ilst = _item_list(boxes, udta) if udta is not None else None
        if ilst is None:
            return None
        covr = boxes.child(ilst, b"covr")
        if covr is None or _picture_kind(boxes, covr) is None:
            return None
        data = boxes.child(covr, b"data")
        if data is None or data[2] - data[1] - 8 > MAX_PICTURE:
            return None
        image = boxes.read((b"data", data[1] + 8, data[2]), MAX_PICTURE)
        return image if picture_type(image) else None


class _Boxes:
    """Boxes as (type, start of content, end), read from a file."""

    def __init__(self, f):
        self.f = f
        f.seek(0, 2)
        self.size = f.tell()

    def children(self, parent, skip=0):
        start = (0 if parent is None else parent[1]) + skip
        end = self.size if parent is None else parent[2]
        pos = start
        for _ in range(MAX_BOXES):
            if pos + 8 > end:
                return
            self.f.seek(pos)
            size, kind = struct.unpack(">I4s", read_exact(self.f, 8))
            head = 8
            if size == 1:
                size = struct.unpack(">Q", read_exact(self.f, 8))[0]
                head = 16
            elif size == 0:
                size = end - pos
            if size < head or pos + size > end:
                raise AudioError("not_audio", "bad box size")
            yield kind, pos + head, pos + size
            pos += size

    def child(self, parent, kind, skip=0):
        for box in self.children(parent, skip):
            if box[0] == kind:
                return box
        return None

    def find_top(self, kind):
        first = True
        for box in self.children(None):
            if first and box[0] != b"ftyp":
                raise AudioError("not_audio", "not an MPEG-4 file")
            first = False
            if box[0] == kind:
                return box
        raise AudioError("not_audio", "no " + kind.decode("latin-1"))

    def read(self, box, limit):
        """The content of box, at most limit bytes."""
        self.f.seek(box[1])
        return self.f.read(min(box[2] - box[1], limit))


def _duration(data):
    if len(data) < 4:
        return None
    if data[0] == 1:
        if len(data) < 32:
            return None
        scale, length = struct.unpack(">IQ", data[20:32])
        unknown = 0xffffffffffffffff
    else:
        if len(data) < 20:
            return None
        scale, length = struct.unpack(">II", data[12:20])
        unknown = 0xffffffff
    return length * 1000 // scale if scale and 0 < length < unknown else None


def _chapters(data):
    """[(begin ms, title)] of a chpl box."""
    if len(data) < 5:
        return []
    pos = 4 + (4 if data[0] == 1 else 0)
    if pos >= len(data):
        return []
    count = data[pos]
    pos += 1
    marks = []
    for _ in range(count):
        if pos + 9 > len(data):
            break
        begin = struct.unpack(">Q", data[pos:pos + 8])[0] // _CHPL_UNIT
        length = data[pos + 8]
        title = data[pos + 9:pos + 9 + length]
        pos += 9 + length
        marks.append((begin, clean_text(title.decode("utf-8", errors="replace"))))
    return marks


def _item_list(boxes, udta):
    meta = boxes.child(udta, b"meta")
    if meta is None:
        return None
    # meta is a "full box" with 4 bytes of version and flags, except in
    # files written like QuickTime ones, where hdlr follows at once.
    head = boxes.read(meta, 8)
    skip = 0 if head[4:8] == b"hdlr" else 4
    return boxes.child(meta, b"ilst", skip)


def _data(boxes, item):
    """(type, value) of the data box of an item, or None."""
    data = boxes.child(item, b"data")
    if data is None or data[2] - data[1] < 8 or data[2] - data[1] > 64 * 1024:
        return None
    content = boxes.read(data, 64 * 1024)
    return struct.unpack(">I", content[:4])[0] & 0xffffff, content[8:]


def _series_item(boxes, item, series):
    """Note what the item says about the series in series. A broken item
    is passed over: the book is still usable without its series."""
    try:
        if item[0] == b"----":
            field = _SERIES.get(_freeform_name(boxes, item).upper())
            if field is not None and not series[field]:
                series[field] = _text(boxes, item, (0, 1))
        elif item[0] == _MOVEMENT_NAME and not series["movement"]:
            series["movement"] = _text(boxes, item, (1,))
        elif item[0] == _MOVEMENT_PART and not series["movement_part"]:
            series["movement_part"] = _integer(boxes, item)
    except AudioError:
        pass


def _text(boxes, item, types):
    """The text of an item whose data box has one of types, else ""."""
    data = _data(boxes, item)
    if data is None or data[0] not in types:
        return ""
    return data[1].decode("utf-8", errors="replace")


def _integer(boxes, item):
    """The number in an item of type integer (21) as text, else ""."""
    data = _data(boxes, item)
    if data is None or data[0] not in (0, 21) or len(data[1]) not in (1, 2, 4, 8):
        return ""
    return str(int.from_bytes(data[1], "big", signed=True))


def _freeform_name(boxes, item):
    """The name of a free-form item of iTunes ("SERIES"), else "". mean and
    name are full boxes: 4 bytes of version and flags, then the text."""
    mean = boxes.child(item, b"mean")
    name = boxes.child(item, b"name")
    if mean is None or name is None:
        return ""
    if boxes.read(mean, 4 + 256)[4:].decode("utf-8", errors="replace") != _ITUNES:
        return ""
    return boxes.read(name, 4 + 256)[4:].decode("utf-8", errors="replace")


def _picture_kind(boxes, covr):
    """ "jpg" or "png" by the first bytes of the image: the type code in the
    data box may be wrong or 0."""
    data = boxes.child(covr, b"data")
    if data is None or data[2] - data[1] < 16:
        return None
    return picture_type(boxes.read((b"data", data[1] + 8, data[2]), 8))
