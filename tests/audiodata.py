"""Builds small MP3 and M4B files for the tests: tags and frame headers as
the formats define them, silence as audio."""

import struct

JPEG = b"\xff\xd8\xff\xe0" + b"\0" * 60
PNG = b"\x89PNG\r\n\x1a\n" + struct.pack(">I4sII", 13, b"IHDR", 10, 20) + b"\0" * 40

# MPEG-1 Layer III, 128 kbit/s, 44100 Hz, stereo: 417 bytes, 1152 samples.
FRAME_HEADER = b"\xff\xfb\x90\x00"
FRAME_LENGTH = 417
FRAME_MS = 1152 * 1000 / 44100


def synchsafe(n):
    return bytes([(n >> 21) & 0x7f, (n >> 14) & 0x7f, (n >> 7) & 0x7f, n & 0x7f])


def frame(frame_id, data, version=3, flags=0):
    if version == 2:
        return frame_id.encode() + len(data).to_bytes(3, "big") + data
    size = synchsafe(len(data)) if version == 4 else struct.pack(">I", len(data))
    return frame_id.encode() + size + bytes([0, flags]) + data


def text(frame_id, value, version=3, encoding=3):
    codec = {0: "latin-1", 1: "utf-16", 2: "utf-16-be", 3: "utf-8"}[encoding]
    return frame(frame_id, bytes([encoding]) + value.encode(codec), version)


def txxx(description, value, version=3, encoding=3):
    codec = {0: "latin-1", 1: "utf-16", 2: "utf-16-be", 3: "utf-8"}[encoding]
    nul = b"\0\0" if encoding in (1, 2) else b"\0"
    return frame("TXX" if version == 2 else "TXXX",
                 bytes([encoding]) + description.encode(codec) + nul + value.encode(codec), version)


def apic(image, mime="image/jpeg", kind=3, description=b"", version=3):
    if version == 2:
        return frame("PIC", b"\0" + mime.encode() + bytes([kind]) + description + b"\0" + image,
                     version)
    return frame("APIC", b"\0" + mime.encode() + b"\0" + bytes([kind]) + description + b"\0"
                 + image, version)


def chap(element, begin, end, title=None, version=3):
    sub = text("TIT2", title, version) if title is not None else b""
    return frame("CHAP", element.encode() + b"\0" + struct.pack(">IIII", begin, end,
                                                                 0xffffffff, 0xffffffff) + sub,
                 version)


def tag(frames, version=3, flags=0, padding=16):
    body = b"".join(frames) + b"\0" * padding
    return b"ID3" + bytes([version, 0, flags]) + synchsafe(len(body)) + body


def audio(frames=10, xing=None):
    """frames of silence; xing: number of frames to put into a Xing header
    in the first one, which then holds no audio."""
    data = b""
    if xing is not None:
        first = bytearray(FRAME_HEADER + b"\0" * (FRAME_LENGTH - 4))
        first[36:48] = b"Xing" + struct.pack(">II", 1, xing)
        data += bytes(first)
    return data + (FRAME_HEADER + b"\0" * (FRAME_LENGTH - 4)) * frames


def mp3(frames=(), audio_frames=10, version=3, xing=None):
    return (tag(frames, version) if frames is not None else b"") + audio(audio_frames, xing)


def box(kind, payload):
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def item(kind, data, data_type=1):
    return box(kind, box(b"data", struct.pack(">II", data_type, 0) + data))


def freeform(name, value, mean="com.apple.iTunes", data_type=1):
    return box(b"----", box(b"mean", bytes(4) + mean.encode()) + box(b"name", bytes(4) + name.encode())
               + box(b"data", struct.pack(">II", data_type, 0) + value.encode()))


def chpl(chapters):
    payload = bytes([1, 0, 0, 0]) + b"\0\0\0\0" + bytes([len(chapters)])
    for begin_ms, title in chapters:
        encoded = title.encode()
        payload += struct.pack(">Q", begin_ms * 10000) + bytes([len(encoded)]) + encoded
    return box(b"chpl", payload)


def m4b(duration_ms=60000, chapters=(), items=(), meta_version=True):
    mvhd = box(b"mvhd", bytes(4) + struct.pack(">IIII", 0, 0, 1000, duration_ms) + bytes(80))
    hdlr = box(b"hdlr", bytes(8) + b"mdirappl" + bytes(9))
    meta = box(b"meta", (bytes(4) if meta_version else b"") + hdlr + box(b"ilst", b"".join(items)))
    udta = box(b"udta", (chpl(chapters) if chapters else b"") + meta)
    trak = box(b"trak", bytes(100))
    return (box(b"ftyp", b"M4B \0\0\0\0isom") + box(b"mdat", bytes(1000))
            + box(b"moov", mvhd + trak + udta))
