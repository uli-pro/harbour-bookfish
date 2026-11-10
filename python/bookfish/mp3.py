"""What an MP3 file says about itself: ID3v2 tags (title, album, artists,
series, chapter marks, picture) and the duration, read from the frame headers
without decoding.

The files come from anywhere, so nothing is read whole: frame headers are
read one by one, and a frame's content only if it is wanted and small.
Every size is checked against the tag and the file. Frames that are
compressed, encrypted or unsynchronised are skipped; they are rare in
audiobooks, and the app then falls back to file names.
"""

import struct

from . import audioutil
from .audioutil import AudioError, clean_text, open_regular, picture_type, read_exact

MAX_TEXT = 64 * 1024
MAX_CHAPTER_FRAME = 1024 * 1024
MAX_PICTURE = 5 * 1024 * 1024
MAX_FRAMES = 10000
MAX_CHAPTERS = 5000
# How far after the tag the first audio frame is looked for: some files
# have padding or junk between them.
_SYNC_SEARCH = 64 * 1024

_TEXT = {"TIT2": "title", "TALB": "album", "TPE1": "artist", "TPE2": "albumartist",
         "TT2": "title", "TAL": "album", "TP1": "artist", "TP2": "albumartist"}
_PICTURE = ("APIC", "PIC")
# User text frames by description (any case), and iTunes' movement frames.
_USER_TEXT = ("TXXX", "TXX")
_SERIES = {"SERIES": "series", "SERIES-PART": "part"}
_MOVEMENT = {"MVNM": "movement", "MVIN": "movement_part"}

# kbit/s by version (1 or 2, 2.5 using 2) and layer, index 1 to 14.
_BITRATES = {
    (1, 1): (32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448),
    (1, 2): (32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384),
    (1, 3): (32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320),
    (2, 1): (32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256),
    (2, 2): (8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160),
    (2, 3): (8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160),
}
_SAMPLE_RATES = {1: (44100, 48000, 32000), 2: (22050, 24000, 16000), 25: (11025, 12000, 8000)}


def read(path, chapters=True):
    """{title, album, artist, albumartist, series, series_index, picture,
    duration, chapters} of the MP3 at path.

    Missing tags are ""; series_index a float or None (see
    audioutil.series); picture is "jpg", "png" or None; duration in ms or
    None if no audio frame was found; chapters [(begin ms, title)] as in
    the file, unchecked (see audioutil.chapter_list). Raises AudioError if
    the file is no MP3, OSError if it cannot be read.
    """
    with open_regular(path) as f:
        size = _file_size(f)
        tag = _Tag(f, size)
        info = tag.read(chapters)
        if not tag.version:
            _read_v1(f, size, info)
        info["duration"] = _duration(f, tag.end, size)
    if info["duration"] is None and not tag.found:
        raise AudioError("not_audio", "no ID3 tag and no MPEG frame")
    return info


def picture(path):
    """The bytes of the picture in the MP3's tag (the front cover if there
    are several), or None."""
    with open_regular(path) as f:
        return _Tag(f, _file_size(f)).picture()


def _file_size(f):
    f.seek(0, 2)
    return f.tell()


class _Tag:
    """The ID3v2 tag at the start of a file."""

    def __init__(self, f, file_size):
        self.f = f
        self.found = False
        self.end = 0
        self.frames_start = self.frames_end = 0
        self.version = 0
        f.seek(0)
        header = f.read(10)
        if len(header) < 10 or header[:3] != b"ID3":
            return
        version, flags = header[3], header[5]
        size = _synchsafe(header[6:10])
        if version not in (2, 3, 4) or size is None:
            return
        self.found = True
        self.end = min(10 + size + (10 if version == 4 and flags & 0x10 else 0), file_size)
        # Unsynchronised tags, and compressed ones in 2.2, are not read.
        if flags & 0x80 or (version == 2 and flags & 0x40):
            return
        start = 10
        if version > 2 and flags & 0x40:
            ext = read_exact(f, 4)
            if version == 3:
                start += 4 + struct.unpack(">I", ext)[0]
            else:
                ext_size = _synchsafe(ext)
                if ext_size is None:
                    return
                start += ext_size
        self.version = version
        self.frames_start = start
        self.frames_end = min(10 + size, file_size)

    def frames(self, start=None, end=None):
        """(id, offset of the content, size) of the frames between start and
        end, those that cannot be read left out."""
        if not self.version:
            return
        pos = self.frames_start if start is None else start
        end = self.frames_end if end is None else end
        head = 6 if self.version == 2 else 10
        for _ in range(MAX_FRAMES):
            if pos + head > end:
                return
            self.f.seek(pos)
            header = read_exact(self.f, head)
            if self.version == 2:
                frame_id = header[:3]
                size = int.from_bytes(header[3:6], "big")
                flags = 0
            else:
                frame_id = header[:4]
                size = self._frame_size(header[4:8], pos + head, end)
                flags = header[9]
            if not _frame_id(frame_id):
                return  # padding, or garbage
            content = pos + head
            if content + size > end:
                return
            pos = content + size
            usable, skip = _frame_flags(flags, self.version)
            if usable and size >= skip:
                yield frame_id.decode("ascii"), content + skip, size - skip

    def _frame_size(self, data, content, end):
        plain = struct.unpack(">I", data)[0]
        if self.version == 3:
            return plain
        size = _synchsafe(data)
        if size is None:
            return plain
        # Some writers (old iTunes) put plain sizes into 2.4 tags; the size
        # that leads to the next frame or to the end is the right one.
        if size != plain and not self._frame_follows(content + size, end) \
                and self._frame_follows(content + plain, end):
            return plain
        return size

    def _frame_follows(self, pos, end):
        if pos == end:
            return True
        if pos + 4 > end:
            return False
        self.f.seek(pos)
        following = self.f.read(4)
        return following[:1] == b"\0" or _frame_id(following)

    def read(self, chapters):
        info = {"title": "", "album": "", "artist": "", "albumartist": "", "picture": None,
                "chapters": []}
        series = {"series": "", "part": "", "movement": "", "movement_part": ""}
        front = False
        for frame_id, offset, size in self.frames():
            if frame_id in _TEXT:
                if not info[_TEXT[frame_id]] and size <= MAX_TEXT:
                    info[_TEXT[frame_id]] = clean_text(_text(self._content(offset, size)))
            elif frame_id in _USER_TEXT and size <= MAX_TEXT:
                description, value = _user_text(self._content(offset, size))
                field = _SERIES.get(description.strip().upper())
                if field is not None and not series[field]:
                    series[field] = value
            elif frame_id in _MOVEMENT and size <= MAX_TEXT:
                if not series[_MOVEMENT[frame_id]]:
                    series[_MOVEMENT[frame_id]] = _text(self._content(offset, size))
            elif frame_id in _PICTURE and not front:
                found = self._picture(frame_id, offset, size)
                if found is not None:
                    info["picture"], front = found[0], found[1]
            elif frame_id == "CHAP" and chapters and size <= MAX_CHAPTER_FRAME:
                if len(info["chapters"]) < MAX_CHAPTERS:
                    chapter = self._chapter(offset, size)
                    if chapter is not None:
                        info["chapters"].append(chapter)
        info["series"], info["series_index"] = audioutil.series(
            series["series"], series["part"], series["movement"], series["movement_part"])
        return info

    def picture(self):
        """The bytes of the front cover, else of the first picture."""
        chosen = None
        for frame_id, offset, size in self.frames():
            if frame_id in _PICTURE:
                found = self._picture(frame_id, offset, size)
                if found is not None and (chosen is None or found[1]):
                    chosen = found
                    if found[1]:
                        break
        if chosen is None or chosen[3] > MAX_PICTURE:
            return None
        return self._content(chosen[2], chosen[3])

    def _content(self, offset, size):
        self.f.seek(offset)
        return read_exact(self.f, size)

    def _picture(self, frame_id, offset, size):
        """(type "jpg" or "png", front cover?, offset, size) of the image in
        a picture frame, or None for other images. The type is told by the
        image itself: the MIME type in the frame may be "PNG" or wrong."""
        head = self._content(offset, min(size, 64 * 1024))
        if len(head) < 5:
            return None
        if frame_id == "PIC":
            kind_at = 4
        else:
            kind_at = head.find(b"\0", 1) + 1
            if kind_at <= 0 or kind_at >= len(head):
                return None
        start = _terminator(head, kind_at + 1, head[0])
        if start is None:
            return None
        image = self._content(offset + start, min(8, size - start))
        kind = picture_type(image)
        if kind is None:
            return None
        return kind, head[kind_at] == 3, offset + start, size - start

    def _chapter(self, offset, size):
        data = self._content(offset, size)
        id_end = data.find(b"\0")
        if id_end < 0 or len(data) < id_end + 17:
            return None
        begin = struct.unpack(">I", data[id_end + 1:id_end + 5])[0]
        # Sub-frames, laid out like the frames of the tag; read from the
        # frame's content, not the file, as there may be thousands.
        pos = id_end + 17
        while pos + 10 <= len(data) and _frame_id(data[pos:pos + 4]):
            sub_size = (_synchsafe(data[pos + 4:pos + 8]) if self.version == 4 else None)
            if sub_size is None:
                sub_size = struct.unpack(">I", data[pos + 4:pos + 8])[0]
            content = pos + 10
            if content + sub_size > len(data):
                break
            if data[pos:pos + 4] == b"TIT2":
                usable, skip = _frame_flags(data[pos + 9], self.version)
                if usable and sub_size >= skip and sub_size <= MAX_TEXT:
                    return begin, clean_text(_text(data[content + skip:content + sub_size]))
                break
            pos = content + sub_size
        return begin, ""


def _read_v1(f, size, info):
    """Title, artist and album from an ID3v1 tag at the end of the file,
    for files with nothing else."""
    if size < 128:
        return
    f.seek(size - 128)
    data = f.read(128)
    if data[:3] != b"TAG":
        return
    for field, start in (("title", 3), ("artist", 33), ("album", 63)):
        info[field] = clean_text(data[start:start + 30].split(b"\0")[0].decode("latin-1"))


def _synchsafe(data):
    if any(b & 0x80 for b in data):
        return None
    return (data[0] << 21) | (data[1] << 14) | (data[2] << 7) | data[3]


def _frame_id(data):
    """True for a frame id: capital letters and digits."""
    return (len(data) in (3, 4) and data.isalnum()
            and all(c in b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" for c in data))


def _frame_flags(flags, version):
    """(usable, bytes before the content) for the format flags of a frame."""
    if version == 3:
        # compression 0x80, encryption 0x40, grouping 0x20
        return not flags & 0xc0, 1 if flags & 0x20 else 0
    if version == 4:
        # grouping 0x40, compression 0x08, encryption 0x04,
        # unsynchronisation 0x02, data length indicator 0x01
        skip = (1 if flags & 0x40 else 0) + (4 if flags & 0x01 else 0)
        return not flags & 0x0e, skip
    return True, 0


def _text(data):
    """The first value of a text frame."""
    if not data:
        return ""
    encoding, body = data[0], data[1:]
    end = _terminator(body, 0, encoding)
    if end is not None:
        body = body[:end - (2 if encoding in (1, 2) else 1)]
    return _decode(body, encoding)


def _user_text(data):
    """(description, first value) of a TXXX frame."""
    if not data:
        return "", ""
    encoding = data[0]
    end = _terminator(data, 1, encoding)
    if end is None:
        return "", ""
    description = _decode(data[1:end - (2 if encoding in (1, 2) else 1)], encoding)
    return description, _text(bytes([encoding]) + data[end:])


def _terminator(data, start, encoding):
    """Offset after the NUL that ends the string at start, or None."""
    if encoding in (1, 2):
        pos = start
        while pos + 1 < len(data):
            if data[pos] == 0 and data[pos + 1] == 0:
                return pos + 2
            pos += 2
        return None
    pos = data.find(b"\0", start)
    return pos + 1 if pos >= 0 else None


def _decode(data, encoding):
    codec = {0: "latin-1", 1: "utf-16", 2: "utf-16-be", 3: "utf-8"}.get(encoding)
    if codec is None:
        return ""
    if codec == "utf-16" and data[:2] not in (b"\xff\xfe", b"\xfe\xff"):
        codec = "utf-16-le"
    return data.decode(codec, errors="replace")


def _duration(f, start, file_size):
    """Duration in ms from the first MPEG audio frame after start, or None."""
    f.seek(start)
    data = f.read(_SYNC_SEARCH)
    pos = 0
    while True:
        pos = data.find(b"\xff", pos)
        if pos < 0 or pos + 4 > len(data):
            return None
        frame = _frame_header(data[pos:pos + 4])
        if frame is not None:
            following = pos + frame["length"]
            # A second frame right after it: not a stray 0xFF in junk.
            if following + 4 > len(data) or _frame_header(data[following:following + 4]):
                break
        pos += 1
    end = file_size
    if file_size >= 128:
        f.seek(file_size - 128)
        if f.read(3) == b"TAG":
            end -= 128
    audio = max(0, end - start - pos)
    frames = _vbr_frames(data[pos:pos + 200], frame)
    if frames is not None:
        duration = frames * frame["samples"] * 1000 // frame["rate"]
        # Not longer than the audio at the lowest bitrate (8 kbit/s, one
        # byte per ms): the count may be garbage.
        if duration <= audio:
            return duration
    return audio * 8000 // frame["bitrate"]


def _frame_header(data):
    """{bitrate (bit/s), rate, samples, length, mono, version} of an MPEG audio
    frame header, or None if data is none."""
    if data[0] != 0xff or data[1] & 0xe0 != 0xe0:
        return None
    version = {0: 25, 2: 2, 3: 1}.get((data[1] >> 3) & 3)
    layer = {1: 3, 2: 2, 3: 1}.get((data[1] >> 1) & 3)
    bitrate_index = data[2] >> 4
    rate_index = (data[2] >> 2) & 3
    if version is None or layer is None or not 0 < bitrate_index < 15 or rate_index == 3:
        return None
    bitrate = _BITRATES[(min(version, 2), layer)][bitrate_index - 1] * 1000
    rate = _SAMPLE_RATES[version][rate_index]
    padding = (data[2] >> 1) & 1
    if layer == 1:
        samples = 384
        length = (12 * bitrate // rate + padding) * 4
    else:
        samples = 576 if layer == 3 and version != 1 else 1152
        length = samples // 8 * bitrate // rate + padding
    return {"bitrate": bitrate, "rate": rate, "samples": samples, "length": length,
            "mono": (data[3] >> 6) == 3, "version": version, "crc": not data[1] & 1}


def _vbr_frames(data, frame):
    """The number of frames from a Xing, Info or VBRI header in the first
    frame, or None."""
    if frame["version"] == 1:
        side = 17 if frame["mono"] else 32
    else:
        side = 9 if frame["mono"] else 17
    xing = 4 + side + (2 if frame["crc"] else 0)
    if data[xing:xing + 4] in (b"Xing", b"Info") and len(data) >= xing + 12:
        flags = struct.unpack(">I", data[xing + 4:xing + 8])[0]
        if flags & 1:
            frames = struct.unpack(">I", data[xing + 8:xing + 12])[0]
            return frames if 0 < frames < 0xffffffff else None
        return None
    if data[36:40] == b"VBRI" and len(data) >= 54:
        frames = struct.unpack(">I", data[50:54])[0]
        return frames if 0 < frames < 0xffffffff else None
    return None
