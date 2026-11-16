import unittest

from bookfish.errors import EpubError
from bookfish.overlay import Fragment, parse_clock, read_overlay

from .helpers import MINI_DIR, TempDirTestCase, write_files

SMIL = """<?xml version="1.0"?>
<smil xmlns="http://www.w3.org/ns/SMIL" version="3.0"><body>{}</body></smil>"""


def par(text, audio=None, begin=None, end=None):
    attrs = ""
    if begin is not None:
        attrs += ' clipBegin="{}"'.format(begin)
    if end is not None:
        attrs += ' clipEnd="{}"'.format(end)
    audio_tag = '<audio src="{}"{}/>'.format(audio, attrs) if audio else ""
    return '<par><text src="{}"/>{}</par>'.format(text, audio_tag)


class ParseClockTest(unittest.TestCase):

    def test_valid(self):
        for text, ms in [("17.780s", 17780), ("0.000s", 0), ("01:40:08.79", 6008790),
                         ("21:58.97", 1318970), ("100:00:00", 360000000),
                         ("500ms", 500), ("2.5min", 150000), ("1h", 3600000),
                         ("17.78", 17780), (" 3s ", 3000), ("0.0004s", 0)]:
            with self.subTest(text=text):
                self.assertEqual(parse_clock(text), ms)

    def test_invalid(self):
        for text in ["", "abc", "1:2", "00:60:00", "00:00:60", "-1s", "1.s",
                     "1e3s", "1:00:00:00", "5 s", "5sec", "1" + "0" * 310 + "h",
                     "9" * 5000 + ":00:00", "\u0661s"]:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_clock(text)


class ReadOverlayTest(TempDirTestCase):

    def overlay(self, body):
        write_files(self.tmp, {"OPS/mo/c1.smil": SMIL.format(body)})
        return read_overlay(self.tmp, "OPS/mo/c1.smil")

    def assertFails(self, code, body):
        with self.assertRaises(EpubError) as cm:
            self.overlay(body)
        self.assertEqual(cm.exception.code, code)

    def test_mini(self):
        overlay = read_overlay(MINI_DIR, "OEBPS/MediaOverlays/chapter.smil")
        audio = "OEBPS/Audio/00001-00001.mp3"
        self.assertEqual(overlay.fragments, [
            Fragment("OEBPS/chapter.xhtml", "chapter-s0", audio, 0, 17780),
            Fragment("OEBPS/chapter.xhtml", "chapter-s1", audio, 17780, 29660),
            Fragment("OEBPS/chapter.xhtml", "chapter-s2", audio, 29660, 39000),
        ])

    def test_nested_seq_in_document_order(self):
        overlay = self.overlay(
            "<seq>" + par("../c1.xhtml#a", "../a.mp3", "0s", "1s")
            + "<seq>" + par("../c1.xhtml#b", "../a.mp3", "1s", "2s") + "</seq>"
            + par("../c1.xhtml#c", "../a.mp3", "2s", "3s") + "</seq>")
        self.assertEqual([f.text_id for f in overlay.fragments], ["a", "b", "c"])

    def test_unplayable_pars_skipped(self):
        overlay = self.overlay(
            par("../c1.xhtml#no-audio")
            + par("../c1.xhtml", "../a.mp3", "0s", "1s")          # no id
            + par("../c1.xhtml#web", "https://example.com/a.mp3", "0s", "1s")
            + par("../c1.xhtml#ok", "../a.mp3", "1s", "2s")
            + par("../c1.xhtml#bad-clock", "../a.mp3", "soon", "3s")
            + par("../c1.xhtml#empty", "../a.mp3", "3s", "3s")
            + par("../c1.xhtml#backwards", "../a.mp3", "4s", "3.5s")
            + '<par><text src="../c1.xhtml#no-src"/><audio/></par>'
            + par("../c1.xhtml#ok2", "../a.mp3", "4s", "5s")
            + par("../c1.xhtml#huge", "../a.mp3", "999999999s", "1000000000s")
            + par("../c1.xhtml#huge-end", "../a.mp3", "5s", "999999999s"))
        self.assertEqual([f.text_id for f in overlay.fragments], ["ok", "ok2"])
        self.assertEqual(overlay.skipped, 9)

    def test_open_clip(self):
        overlay = self.overlay(par("../c1.xhtml#a", "../a.mp3"))
        self.assertEqual(overlay.fragments, [
            Fragment("OPS/c1.xhtml", "a", "OPS/a.mp3", 0, None)])
        self.assertEqual(overlay.skipped, 0)

    def test_no_fragments(self):
        self.assertFails("bad_overlay", par("../c1.xhtml#a"))

    def test_only_broken_fragments(self):
        self.assertFails("bad_overlay", par("../c1.xhtml#a", "../a.mp3", "2s", "1s"))

    def test_audio_leaving_book(self):
        self.assertFails("unsafe_path",
                         par("../c1.xhtml#a", "../../../x.mp3", "0s", "1s"))

    def test_missing_file(self):
        with self.assertRaises(EpubError) as cm:
            read_overlay(self.tmp, "missing.smil")
        self.assertEqual(cm.exception.code, "bad_overlay")


