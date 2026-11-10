import os
import struct
import unittest

from bookfish import mp3, mp4
from bookfish.audioutil import AudioError, chapter_list, clean_text, natural_key, series

from . import audiodata as ad
from .helpers import TempDirTestCase


class Mp3Test(TempDirTestCase):

    def write(self, data, name="a.mp3"):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_tags_of_each_version(self):
        for version in (2, 3, 4):
            ids = (("TT2", "TAL", "TP1", "TP2") if version == 2
                   else ("TIT2", "TALB", "TPE1", "TPE2"))
            path = self.write(ad.mp3([ad.text(i, v, version)
                                      for i, v in zip(ids, ("Chapter", "Book", "Reader", "Writer"))],
                                     version=version))
            info = mp3.read(path)
            self.assertEqual((info["title"], info["album"], info["artist"], info["albumartist"]),
                             ("Chapter", "Book", "Reader", "Writer"), version)

    def test_text_encodings(self):
        for encoding in (0, 1, 2, 3):
            path = self.write(ad.mp3([ad.text("TIT2", "Grüße", encoding=encoding)]))
            self.assertEqual(mp3.read(path)["title"], "Grüße", encoding)

    def test_first_of_several_values_and_control_characters(self):
        path = self.write(ad.mp3([ad.text("TIT2", "One\0Two"), ad.text("TALB", "A\nB\x07")]))
        info = mp3.read(path)
        self.assertEqual((info["title"], info["album"]), ("One", "A B"))

    def test_long_text_cut(self):
        path = self.write(ad.mp3([ad.text("TIT2", "x" * 2000)]))
        self.assertEqual(len(mp3.read(path)["title"]), 500)

    def test_series(self):
        for version in (2, 3, 4):
            for encoding in (0, 1, 3):
                path = self.write(ad.mp3([ad.txxx("Other", "x", version, encoding),
                                          ad.txxx("series", "Die Känguru-Werke", version, encoding),
                                          ad.txxx("SERIES-PART", "4", version, encoding)],
                                         version=version))
                info = mp3.read(path)
                self.assertEqual((info["series"], info["series_index"]),
                                 ("Die Känguru-Werke", 4.0), (version, encoding))

    def test_series_in_utf16be_and_without_bom(self):
        path = self.write(ad.mp3([ad.txxx("SERIES", "Reihe", 4, 2), ad.txxx("SERIES-PART", "2", 4, 2)],
                                 version=4))
        self.assertEqual((mp3.read(path)["series"], mp3.read(path)["series_index"]), ("Reihe", 2.0))
        data = b"\x01" + "SERIES".encode("utf-16-le") + b"\0\0" + "Reihe".encode("utf-16-le")
        path = self.write(ad.mp3([ad.frame("TXXX", data)]))
        self.assertEqual(mp3.read(path)["series"], "Reihe")
        # No terminator after the description: no series, the rest is read.
        path = self.write(ad.mp3([ad.frame("TXXX", b"\x03SERIES"), ad.text("TIT2", "T")]))
        self.assertEqual((mp3.read(path)["series"], mp3.read(path)["title"]), ("", "T"))

    def test_series_from_movement_only_without_series(self):
        movement = [ad.text("MVNM", "Narnia"), ad.text("MVIN", "3/7")]
        path = self.write(ad.mp3(movement))
        info = mp3.read(path)
        self.assertEqual((info["series"], info["series_index"]), ("Narnia", 3.0))
        path = self.write(ad.mp3(movement + [ad.txxx("SERIES", "Chronicles")]))
        info = mp3.read(path)
        self.assertEqual((info["series"], info["series_index"]), ("Chronicles", None))
        path = self.write(ad.mp3([ad.txxx("SERIES-PART", "2")]))
        info = mp3.read(path)
        self.assertEqual((info["series"], info["series_index"]), ("", None))

    def test_duration_from_bitrate(self):
        path = self.write(ad.mp3([ad.text("TIT2", "T")], audio_frames=100))
        self.assertAlmostEqual(mp3.read(path)["duration"], 100 * ad.FRAME_MS, delta=30)

    def test_duration_from_xing_header(self):
        # The header counts the frames; the size would give twice as much.
        path = self.write(ad.mp3([ad.text("TIT2", "T")], audio_frames=100, xing=50))
        self.assertEqual(mp3.read(path)["duration"], int(50 * ad.FRAME_MS))

    def test_impossible_frame_count_ignored(self):
        for count in (10 ** 6, 0xffffffff):
            path = self.write(ad.mp3([ad.text("TIT2", "T")], audio_frames=100, xing=count))
            self.assertAlmostEqual(mp3.read(path)["duration"], 101 * ad.FRAME_MS, delta=30)

    def test_xing_header_after_crc(self):
        first = bytearray(b"\xff\xfa\x90\x00" + bytes(ad.FRAME_LENGTH - 4))
        first[38:50] = b"Xing" + struct.pack(">II", 1, 50)
        data = ad.tag([ad.text("TIT2", "T")]) + bytes(first) + ad.audio(100)
        self.assertEqual(mp3.read(self.write(data))["duration"], int(50 * ad.FRAME_MS))

    def test_duration_from_vbri_header(self):
        first = bytearray(ad.FRAME_HEADER + bytes(ad.FRAME_LENGTH - 4))
        first[36:54] = b"VBRI" + bytes(10) + struct.pack(">I", 40)
        data = bytes(first) + ad.audio(100)
        self.assertEqual(mp3.read(self.write(data))["duration"], int(40 * ad.FRAME_MS))

    def test_mpeg2_frames(self):
        # MPEG-2 Layer III, 64 kbit/s, 22050 Hz: 576 samples, 208 bytes a frame.
        frame = b"\xff\xf3\x80\x00" + bytes(204)
        info = mp3.read(self.write(frame * 100))
        self.assertAlmostEqual(info["duration"], 100 * 576 * 1000 / 22050, delta=30)

    def test_junk_before_the_first_frame_and_id3v1(self):
        data = ad.tag([ad.text("TIT2", "T")]) + b"\xff\x00junk" + ad.audio(100)
        data += b"TAG" + b"\0" * 125
        path = self.write(data)
        self.assertAlmostEqual(mp3.read(path)["duration"], 100 * ad.FRAME_MS, delta=30)

    def test_only_id3v1(self):
        v1 = b"TAG" + b"Title".ljust(30, b"\0") + b"Artist".ljust(30, b"\0") + b"Album".ljust(30, b"\0")
        path = self.write(ad.audio(10) + v1.ljust(128, b"\0"))
        info = mp3.read(path)
        self.assertEqual((info["title"], info["artist"], info["album"]), ("Title", "Artist", "Album"))

    def test_chapters(self):
        path = self.write(ad.mp3([ad.chap("c1", 5000, 9000, "Two"), ad.chap("c0", 0, 5000, "One"),
                                  ad.chap("c2", 9000, 12000)]))
        self.assertEqual(mp3.read(path)["chapters"], [(5000, "Two"), (0, "One"), (9000, "")])
        self.assertEqual(mp3.read(path, chapters=False)["chapters"], [])

    def test_picture_kind_by_its_bytes(self):
        # Old iTunes writes "PNG" as MIME type; another file claims JPEG for a TIFF.
        path = self.write(ad.mp3([ad.apic(ad.PNG, "PNG")]))
        self.assertEqual(mp3.read(path)["picture"], "png")
        self.assertEqual(mp3.picture(path), ad.PNG)
        path = self.write(ad.mp3([ad.apic(b"MM\0*" + bytes(20), "image/jpeg")]))
        self.assertIsNone(mp3.read(path)["picture"])
        self.assertIsNone(mp3.picture(path))

    def test_front_cover_preferred(self):
        path = self.write(ad.mp3([ad.apic(ad.PNG, "image/png", kind=0, description=b"back"),
                                  ad.apic(ad.JPEG, kind=3)]))
        self.assertEqual(mp3.read(path)["picture"], "jpg")
        self.assertEqual(mp3.picture(path), ad.JPEG)

    def test_picture_in_id3v22(self):
        path = self.write(ad.mp3([ad.apic(ad.JPEG, "JPG", version=2)], version=2))
        self.assertEqual(mp3.picture(path), ad.JPEG)

    def test_frame_flags(self):
        compressed = ad.frame("TIT2", b"\3x", flags=0x80)
        grouped = ad.frame("TALB", b"\x01\3Book", flags=0x20)
        info = mp3.read(self.write(ad.mp3([compressed, grouped])))
        self.assertEqual((info["title"], info["album"]), ("", "Book"))
        with_length = ad.frame("TIT2", struct.pack(">I", 6) + b"\3Title", version=4, flags=0x01)
        unsynchronised = ad.frame("TALB", b"\3Book", version=4, flags=0x02)
        info = mp3.read(self.write(ad.mp3([with_length, unsynchronised], version=4)))
        self.assertEqual((info["title"], info["album"]), ("Title", ""))

    def test_plain_sizes_in_id3v24(self):
        title = b"TIT2" + struct.pack(">I", 301) + b"\0\0\3" + b"x" * 300
        info = mp3.read(self.write(ad.mp3([title, ad.text("TALB", "Book", 4)], version=4)))
        self.assertEqual((len(info["title"]), info["album"]), (300, "Book"))

    def test_extended_header_and_footer(self):
        frames = ad.text("TIT2", "T3")
        body = struct.pack(">I", 6) + bytes(6) + frames
        data = b"ID3\3\0\x40" + ad.synchsafe(len(body)) + body + ad.audio(5)
        self.assertEqual(mp3.read(self.write(data))["title"], "T3")
        frames = ad.text("TIT2", "T4", 4)
        body = ad.synchsafe(6) + b"\1\0" + frames
        data = (b"ID3\4\0\x50" + ad.synchsafe(len(body)) + body
                + b"3DI\4\0\x50" + ad.synchsafe(len(body)) + ad.audio(5))
        info = mp3.read(self.write(data))
        self.assertEqual(info["title"], "T4")
        self.assertAlmostEqual(info["duration"], 5 * ad.FRAME_MS, delta=30)

    def test_picture_with_utf16_description(self):
        frame = ad.frame("APIC", b"\1image/jpeg\0\3" + "Bild".encode("utf-16") + b"\0\0" + ad.JPEG)
        self.assertEqual(mp3.picture(self.write(ad.mp3([frame]))), ad.JPEG)

    def test_many_chapters_with_sub_frames(self):
        chapters = [ad.chap("c%d" % i, i * 1000, i * 1000 + 1000, "Kapitel %d" % i, version=4)
                    for i in range(300)]
        info = mp3.read(self.write(ad.mp3(chapters, version=4)))
        self.assertEqual(info["chapters"][299], (299000, "Kapitel 299"))

    def test_unsynchronised_tag_not_read(self):
        data = bytearray(ad.mp3([ad.text("TIT2", "T")]))
        data[5] = 0x80
        info = mp3.read(self.write(bytes(data)))
        self.assertEqual(info["title"], "")
        self.assertIsNotNone(info["duration"])

    def test_frame_larger_than_tag_ends_reading(self):
        bad = b"TIT2" + struct.pack(">I", 10 ** 6) + b"\0\0\3x"
        info = mp3.read(self.write(ad.mp3([ad.text("TALB", "Book"), bad])))
        self.assertEqual((info["album"], info["title"]), ("Book", ""))

    def test_tag_larger_than_file(self):
        data = b"ID3\3\0\0" + ad.synchsafe(10 ** 7) + ad.text("TIT2", "T")
        self.assertEqual(mp3.read(self.write(data))["title"], "T")

    def test_not_audio(self):
        with self.assertRaises(AudioError):
            mp3.read(self.write(b"just some text " * 100))
        with self.assertRaises(AudioError):
            mp3.read(self.write(b""))

    def test_fifo_not_opened(self):
        path = os.path.join(self.tmp, "fifo.mp3")
        os.mkfifo(path)
        with self.assertRaises(AudioError):
            mp3.read(path)


class Mp4Test(TempDirTestCase):

    def write(self, data):
        path = os.path.join(self.tmp, "a.m4b")
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_duration_chapters_tags_cover(self):
        path = self.write(ad.m4b(3600000, [(0, "Intro"), (60000, "Kapitel 1")], [
            ad.item(b"\xa9nam", "Title".encode()), ad.item(b"\xa9alb", "Album".encode()),
            ad.item(b"\xa9ART", "Reader".encode()), ad.item(b"aART", "Müller, Anna".encode()),
            ad.item(b"covr", ad.PNG, 14)]))
        info = mp4.read(path)
        self.assertEqual(info, {"title": "Title", "album": "Album", "artist": "Reader",
                                "albumartist": "Müller, Anna", "picture": "png",
                                "series": "", "series_index": None, "duration": 3600000,
                                "chapters": [(0, "Intro"), (60000, "Kapitel 1")]})
        self.assertEqual(mp4.picture(path), ad.PNG)

    def test_series(self):
        movement = [ad.item(b"\xa9mvn", "Löwenthals".encode()),
                    ad.item(b"\xa9mvi", struct.pack(">h", 3), 21)]
        info = mp4.read(self.write(ad.m4b(items=movement)))
        self.assertEqual((info["series"], info["series_index"]), ("Löwenthals", 3.0))
        info = mp4.read(self.write(ad.m4b(items=movement + [
            ad.freeform("SERIES", "Other", mean="com.example"), ad.freeform("series", "Das Erbe"),
            ad.freeform("SERIES-PART", "2.5")])))
        self.assertEqual((info["series"], info["series_index"]), ("Das Erbe", 2.5))
        info = mp4.read(self.write(ad.m4b(items=[ad.item(b"\xa9mvn", "Ryan".encode()),
                                                 ad.item(b"\xa9mvi", b"\xff", 21)])))
        self.assertEqual((info["series"], info["series_index"]), ("Ryan", None))

    def test_broken_series_items_passed_over(self):
        broken_name = ad.box(b"----", ad.box(b"mean", bytes(4) + b"com.apple.iTunes")
                             + struct.pack(">I4s", 999, b"name"))
        broken_movement = ad.box(b"\xa9mvn", struct.pack(">I4s", 999, b"data"))
        no_name = ad.box(b"----", ad.box(b"mean", bytes(4) + b"com.apple.iTunes"))
        for item in (broken_name, broken_movement, no_name):
            info = mp4.read(self.write(ad.m4b(items=[ad.item(b"\xa9nam", b"T"), item])))
            self.assertEqual((info["title"], info["series"]), ("T", ""))
        info = mp4.read(self.write(ad.m4b(items=[ad.freeform("SERIES", "S"),
                                                 ad.freeform("SERIES-PART", "7", data_type=21)])))
        self.assertEqual((info["series"], info["series_index"]), ("S", None))

    def test_meta_written_like_quicktime(self):
        path = self.write(ad.m4b(items=[ad.item(b"\xa9nam", b"T")], meta_version=False))
        self.assertEqual(mp4.read(path)["title"], "T")

    def test_cover_type_by_its_bytes(self):
        path = self.write(ad.m4b(items=[ad.item(b"covr", b"MM\0*" + bytes(20), 13)]))
        self.assertIsNone(mp4.read(path)["picture"])
        self.assertIsNone(mp4.picture(path))
        # Type code JPEG, or none at all, for a PNG.
        for code in (13, 0):
            path = self.write(ad.m4b(items=[ad.item(b"covr", ad.PNG, code)]))
            self.assertEqual(mp4.read(path)["picture"], "png")
            self.assertEqual(mp4.picture(path), ad.PNG)

    def test_64_bit_box_size_and_chpl_version_0(self):
        chpl = ad.box(b"chpl", b"\0\0\0\0\1" + struct.pack(">Q", 5 * 10000000) + b"\1A")
        moov_content = ad.box(b"udta", chpl)
        moov = struct.pack(">I4sQ", 1, b"moov", 16 + len(moov_content)) + moov_content
        info = mp4.read(self.write(ad.box(b"ftyp", b"M4B ") + moov))
        self.assertEqual(info["chapters"], [(5000, "A")])

    def test_unknown_duration(self):
        mvhd = ad.box(b"mvhd", bytes(4) + struct.pack(">IIII", 0, 0, 1000, 0xffffffff) + bytes(80))
        data = ad.box(b"ftyp", b"M4B ") + ad.box(b"moov", mvhd)
        self.assertIsNone(mp4.read(self.write(data))["duration"])

    def test_without_udta(self):
        data = ad.box(b"ftyp", b"M4B ") + ad.box(b"moov", ad.box(
            b"mvhd", bytes(4) + struct.pack(">IIII", 0, 0, 600, 6000) + bytes(80)))
        info = mp4.read(self.write(data))
        self.assertEqual((info["duration"], info["chapters"], info["title"]), (10000, [], ""))

    def test_mvhd_version_1(self):
        mvhd = ad.box(b"mvhd", b"\1\0\0\0" + struct.pack(">QQIQ", 0, 0, 1000, 2 ** 33) + bytes(80))
        data = ad.box(b"ftyp", b"M4B ") + ad.box(b"moov", mvhd)
        self.assertEqual(mp4.read(self.write(data))["duration"], 2 ** 33)

    def test_chapter_list_cut_short(self):
        data = bytearray(ad.m4b(chapters=[(0, "One"), (1000, "Two")]))
        pos = data.find(b"chpl") + 4 + 8
        data[pos] = 50  # claims 50 chapters
        self.assertEqual(mp4.read(self.write(bytes(data)))["chapters"], [(0, "One"), (1000, "Two")])

    def test_not_mpeg4(self):
        with self.assertRaises(AudioError):
            mp4.read(self.write(ad.mp3([ad.text("TIT2", "T")])))
        with self.assertRaises(AudioError):
            mp4.read(self.write(ad.box(b"ftyp", b"M4B ")))

    def test_box_sizes_checked(self):
        for bad in (struct.pack(">I4s", 4, b"moov"),           # smaller than its header
                    struct.pack(">I4s", 10 ** 6, b"moov"),       # beyond the file
                    struct.pack(">I4sQ", 1, b"moov", 2 ** 60)):  # 64-bit, beyond the file
            with self.assertRaises(AudioError):
                mp4.read(self.write(ad.box(b"ftyp", b"M4B ") + bad + bytes(16)))

    def test_size_zero_runs_to_the_end(self):
        moov = ad.box(b"moov", ad.box(b"mvhd", bytes(4) + struct.pack(">IIII", 0, 0, 1000, 5)
                                      + bytes(80)))
        data = ad.box(b"ftyp", b"M4B ") + moov + struct.pack(">I4s", 0, b"mdat") + bytes(100)
        self.assertEqual(mp4.read(self.write(data))["duration"], 5)


class AudioUtilTest(unittest.TestCase):

    def test_natural_order(self):
        names = ["Part-10.mp3", "part-2.mp3", "2-01.mp3", "1-02.mp3", "1-01.mp3", "Book-001.mp3"]
        self.assertEqual(sorted(names, key=natural_key),
                         ["1-01.mp3", "1-02.mp3", "2-01.mp3", "Book-001.mp3", "part-2.mp3",
                          "Part-10.mp3"])

    def test_chapter_list(self):
        marks = [(9000, "C"), (2000, "A"), (5000, "B"), (5000, "dup"), (70000, "beyond")]
        self.assertEqual(chapter_list(marks, 60000),
                         [(0, 5000, "A"), (5000, 9000, "B"), (9000, None, "C")])
        self.assertEqual(chapter_list([(70000, "beyond")], 60000), [])
        self.assertEqual(chapter_list([], None), [])

    def test_series_index(self):
        for part, index in (("4", 4.0), (" 04 ", 4.0), ("1.5", 1.5), ("3/7", 3.0), ("", None),
                            ("1-3", None), ("x", None), ("-1", None), ("inf", None), ("1e5", None)):
            self.assertEqual(series("S", part, "", ""), ("S", index), part)
        self.assertEqual(series(" ", "1", "M", "2"), ("M", 2.0))
        self.assertEqual(series("", "", "", "1"), ("", None))

    def test_clean_text(self):
        self.assertEqual(clean_text("  a\tb\x00c  "), "a b c")


class DamagedFilesTest(TempDirTestCase):
    """Damaged files only ever raise AudioError or OSError, and quickly."""

    def test_cut_and_flipped(self):
        import random
        rng = random.Random(7)
        samples = [ad.mp3([ad.text("TIT2", "Title"), ad.apic(ad.JPEG), ad.chap("c", 0, 9, "C")],
                          audio_frames=3, version=v, xing=2) for v in (2, 3, 4)]
        samples.append(ad.m4b(60000, [(0, "A"), (100, "B")],
                              [ad.item(b"\xa9nam", b"T"), ad.item(b"covr", ad.PNG, 14)]))
        path = os.path.join(self.tmp, "damaged")
        for n in range(600):
            data = bytearray(samples[n % len(samples)])
            for _ in range(rng.randint(1, 8)):
                data[rng.randrange(len(data))] = rng.randrange(256)
            data = bytes(data[:rng.randint(0, len(data))] if n % 3 == 0 else data)
            with open(path, "wb") as f:
                f.write(data)
            reader = mp4 if n % len(samples) == 3 else mp3
            for call in (reader.read, reader.picture):
                try:
                    call(path)
                except AudioError:
                    pass
