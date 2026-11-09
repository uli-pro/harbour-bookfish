import getpass
import json
import os
import threading
import time
import unittest
from unittest import mock

from bookfish import bridge, library

from . import audiodata as ad
from .helpers import TempDirTestCase, make_epub, mini_entries, write_files

SMIL = """<?xml version="1.0"?>
<smil xmlns="http://www.w3.org/ns/SMIL" version="3.0"><body>
  <par><text src="a.xhtml#s1"/><audio src="a.mp3" clipBegin="0s" clipEnd="1s"/></par>
  <par><text src="b.xhtml#s2"/><audio src="a.mp3" clipBegin="1s" clipEnd="2s"/></par>
  <par><text src="a.xhtml#s3"/><audio src="a.mp3" clipBegin="2s" clipEnd="3s"/></par>
  <par><text src="a.xhtml#s1"/><audio src="a.mp3" clipBegin="3s" clipEnd="4s"/></par>
  <par><text src="a.xhtml#s4"/><audio src="a.mp3" clipBegin="5s" clipEnd="4s"/></par>
</body></smil>"""

SMIL_NO_END = """<?xml version="1.0"?>
<smil xmlns="http://www.w3.org/ns/SMIL" version="3.0"><body>
  <par><text src="a.xhtml#s1"/><audio src="../Audio/a.mp3" clipBegin="1.5s"/></par>
</body></smil>"""


class BridgeTest(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.cache_dir = os.path.join(self.tmp, "cache")
        self.epub = os.path.join(self.tmp, "happy-prince.epub")
        make_epub(self.epub, mini_entries())

    def test_default_folders(self):
        user = getpass.getuser()
        write_files(self.tmp, {"media/" + user + "/card/x": ""})
        with mock.patch.object(bridge, "_MEDIA_ROOT", os.path.join(self.tmp, "media")):
            self.assertEqual(bridge.default_folders("/home/user/Documents"),
                             ["/home/user/Documents",
                              os.path.join(self.tmp, "media", user, "card")])

    def test_open_book(self):
        book = bridge.open_book(self.epub, self.cache_dir)
        json.dumps(book)  # QML gets only plain values
        self.assertEqual(os.path.dirname(book["root"]), self.cache_dir)
        self.assertEqual(book["key"], "urn:uuid:4f1c2a9e-6b0d-4d5e-9a57-3c8e2f7b1d60")
        self.assertEqual(book["path"], self.epub)
        self.assertEqual(book["title"], "The Happy Prince")
        self.assertEqual(book["authors"], ["Wilde, Oscar"])
        self.assertEqual(book["language"], "en")
        self.assertEqual(book["duration"], 39000)
        self.assertEqual(book["cover"], "OEBPS/cover.svg")
        self.assertEqual(book["activeClass"], "-epub-media-overlay-active")
        self.assertEqual(book["spine"], [
            {"path": "OEBPS/title.xhtml", "overlay": None, "linear": True},
            {"path": "OEBPS/chapter.xhtml",
             "overlay": "OEBPS/MediaOverlays/chapter.smil", "linear": True}])
        self.assertEqual(book["toc"], [
            {"title": "Title Page", "path": "OEBPS/title.xhtml", "fragment": "",
             "level": 0, "spine": 0},
            {"title": "The Happy Prince.", "path": "OEBPS/chapter.xhtml",
             "fragment": "chap01", "level": 0, "spine": 1}])

    def test_missing_cover(self):
        make_epub(self.epub, [entry for entry in mini_entries() if entry[0] != "OEBPS/cover.svg"])
        self.assertIsNone(bridge.open_book(self.epub, self.cache_dir)["cover"])

    def test_toc_entry_outside_spine(self):
        entries = [(name, data.replace(b'href="title.xhtml"', b'href="extra.xhtml"'))
                   if name == "OEBPS/nav.xhtml" else (name, data)
                   for name, data in mini_entries()]
        make_epub(self.epub, entries)
        toc = bridge.open_book(self.epub, self.cache_dir)["toc"]
        self.assertEqual((toc[0]["path"], toc[0]["spine"]), ("OEBPS/extra.xhtml", -1))

    def test_key_falls_back_to_file_name(self):
        entries = [(name, data.replace(b"<dc:identifier", b"<dc:source")
                    .replace(b"</dc:identifier>", b"</dc:source>"))
                   if name == "OEBPS/content.opf" else (name, data)
                   for name, data in mini_entries()]
        make_epub(self.epub, entries)
        self.assertEqual(bridge.open_book(self.epub, self.cache_dir)["key"],
                         "happy-prince.epub")

    def test_huge_identifier_gives_short_key(self):
        entries = [(name, data.replace(b"urn:uuid:4f1c2a9e-6b0d-4d5e-9a57-3c8e2f7b1d60",
                                       b"x" * 100000))
                   if name == "OEBPS/content.opf" else (name, data)
                   for name, data in mini_entries()]
        make_epub(self.epub, entries)
        key = bridge.open_book(self.epub, self.cache_dir)["key"]
        self.assertTrue(key.startswith("sha1:"))
        self.assertEqual(len(key), 45)

    def test_broken_book(self):
        with open(self.epub, "wb") as f:
            f.write(b"not a zip")
        result = bridge.open_book(self.epub, self.cache_dir)
        self.assertEqual(result["error"], "not_zip")

    def test_missing_file(self):
        result = bridge.open_book(os.path.join(self.tmp, "missing.epub"), self.cache_dir)
        self.assertEqual(result["error"], "io")

    def test_chapter_lengths(self):
        root = bridge.open_book(self.epub, self.cache_dir)["root"]
        paths = ["OEBPS/title.xhtml", "OEBPS/chapter.xhtml", "OEBPS/title.xhtml",
                 "OEBPS/missing.xhtml"]
        self.assertEqual(bridge.chapter_lengths(root, paths), [31, 233, 31, 0])

    def test_read_chapter(self):
        book = bridge.open_book(self.epub, self.cache_dir)
        chapter = book["spine"][1]
        self.assertEqual(
            bridge.read_chapter(book["root"], chapter["path"], chapter["overlay"]),
            {"ids": ["chapter-s0", "chapter-s1", "chapter-s2"],
             "sentences": [
                 {"id": "chapter-s0", "audio": "OEBPS/Audio/00001-00001.mp3",
                  "begin": 0, "end": 17780},
                 {"id": "chapter-s1", "audio": "OEBPS/Audio/00001-00001.mp3",
                  "begin": 17780, "end": 29660},
                 {"id": "chapter-s2", "audio": "OEBPS/Audio/00001-00001.mp3",
                  "begin": 29660, "end": 39000}],
             "skipped": 0})

    def test_read_chapter_keeps_ids_of_this_chapter_once(self):
        write_files(self.tmp, {"book/a.smil": SMIL})
        root = os.path.join(self.tmp, "book")
        result = bridge.read_chapter(root, "a.xhtml", "a.smil")
        self.assertEqual(result["ids"], ["s1", "s3"])
        self.assertEqual(result["skipped"], 1)
        # Every clip is played, also one whose element came before.
        self.assertEqual([(s["id"], s["begin"]) for s in result["sentences"]],
                         [("s1", 0), ("s3", 2000), ("s1", 3000)])

    def test_read_chapter_sentence_without_end(self):
        write_files(self.tmp, {"book/Text/a.smil": SMIL_NO_END})
        root = os.path.join(self.tmp, "book")
        result = bridge.read_chapter(root, "Text/a.xhtml", "Text/a.smil")
        json.dumps(result)
        self.assertEqual(result["sentences"], [
            {"id": "s1", "audio": "Audio/a.mp3", "begin": 1500, "end": None}])

    def test_read_chapter_errors(self):
        write_files(self.tmp, {"book/bad.smil": "<smil"})
        root = os.path.join(self.tmp, "book")
        self.assertEqual(bridge.read_chapter(root, "a.xhtml", "bad.smil")["error"],
                         "bad_xml")
        self.assertEqual(bridge.read_chapter(root, "a.xhtml", "missing.smil")["error"],
                         "bad_overlay")

    def test_positions(self):
        path = os.path.join(self.tmp, "positions.json")
        self.assertIsNone(bridge.load_position(path, "book"))
        position = {"spine": 1, "id": "chapter-s1", "fraction": 0.5, "heard": True, "offset": -1}
        self.assertIs(bridge.save_position(path, "book", position), True)
        self.assertEqual(bridge.load_position(path, "book"), position)
        with mock.patch.object(bridge.time, "time", return_value=1700000000.5):
            self.assertIs(bridge.save_position(path, "book", position, True), True)
        self.assertEqual(bridge.load_position(path, "book"), dict(position, time=1700000000))

    def test_last_book(self):
        path = os.path.join(self.tmp, "positions.json")
        self.assertIsNone(bridge.load_last_book(path))
        self.assertIs(bridge.save_last_book(path, self.epub), True)
        self.assertEqual(bridge.load_last_book(path), self.epub)
        open(os.path.join(self.tmp, "file"), "w").close()
        broken = os.path.join(self.tmp, "file", "positions.json")
        self.assertEqual(bridge.save_last_book(broken, self.epub)["error"], "io")

    def test_save_position_creates_folder(self):
        path = os.path.join(self.tmp, "new", "positions.json")
        position = {"spine": 0, "id": "", "fraction": 0}
        self.assertIs(bridge.save_position(path, "book", position), True)

    def test_save_position_io_error(self):
        open(os.path.join(self.tmp, "file"), "w").close()
        path = os.path.join(self.tmp, "file", "positions.json")
        result = bridge.save_position(path, "book", {"spine": 0, "id": "", "fraction": 0})
        self.assertEqual(result["error"], "io")


def entry(path, title, authors=(), sort="", series="", index=None, identifier="", audio=False,
          kind="epub"):
    return {"path": path, "stamp": [1, 2], "info": {
        "identifier": identifier, "title": title, "authors": list(authors), "sort": sort,
        "series": series, "index": index, "cover": None, "audio": audio, "broken": False,
        "kind": kind}}


class LibraryViewTest(TempDirTestCase):

    def test_order_and_authors(self):
        view = bridge.library_view([
            entry("/b/1", "Zoo", ["Ann Ärger"], "Ärger, Ann"),
            entry("/b/2", "Book 2", ["Ann Ärger"], "Ärger, Ann", "Saga", 2.0),
            entry("/b/3", "Book 10", ["Ärger, Ann"], "", "Saga", 10.0),
            entry("/b/4", "Alpha", ["Ann Ärger"], "Ärger, Ann"),
            entry("/b/5", "Nobody's", []),
            entry("/b/7", "Quotes", ["«Q»"], "«Q»"),
            entry("/b/6", "Other", ["bob Brown"], "Brown, Bob", "Alpha Series", None),
        ])
        self.assertEqual([b["path"] for b in view["books"]],
                         ["/b/7", "/b/2", "/b/3", "/b/4", "/b/1", "/b/6", "/b/5"])
        self.assertEqual([(a["name"], a["letter"], a["count"]) for a in view["authors"]],
                         [("«Q»", "#", 1), ("Ann Ärger", "A", 4), ("bob Brown", "B", 1),
                          ("", "", 1)])
        self.assertEqual(view["books"][1]["search"], "ann arger book 2 saga")
        coauthored = bridge.library_view([entry("/b/8", "T", ["Child, Lee", "Child, Andrew", "Prince"])])
        self.assertEqual(coauthored["books"][0]["coauthors"], ["Andrew Child", "Prince"])
        for name in ("Sammy Davis, Jr.", "King, Jr., Martin"):
            self.assertEqual(bridge._natural(name), name)
        json.dumps(view)

    def test_replaced_and_copies(self):
        view = bridge.library_view([
            entry("/card/a", "T", ["A"], identifier="urn:uuid:x"),
            entry("/card/b", "T", ["A"], identifier="uuid:x", audio=True),
            entry("/card/c", "U", ["A"], identifier="y"),
            entry("/home/c", "U", ["A"], identifier="y"),
        ])
        self.assertEqual([(b["path"], b["duplicate"]) for b in view["books"]],
                         [("/card/b", False), ("/card/c", True), ("/home/c", True)])

    def test_kinds_and_audiobooks(self):
        epub = entry("/l/A/x.epub", "X", ["A"], identifier="i")
        epub["info"]["cover"] = "OPS/c.jpg"
        audio = entry("/l/A/x.m4b", "x (Unabridged)", ["Reader"], kind="audiobook")
        audio["info"]["cover"] = "embedded.jpg"
        lone = entry("/l/A/talk.mp3", "Talk", ["Tag Author"], kind="audiobook")
        lone["info"]["cover"] = "embedded.png"
        narrated = entry("/l/A/y.epub", "Y", ["A"], identifier="j", audio=True)
        view = bridge.library_view([audio, lone, narrated, epub])
        self.assertEqual([(b["path"], b["kind"], b["title"], b["author"], b["coverPath"], b["cover"])
                          for b in view["books"]], [
            ("/l/A/talk.mp3", "audiobook", "Talk", "A", "/l/A/talk.mp3", "embedded.png"),
            ("/l/A/x.epub", "epub", "X", "A", "/l/A/x.epub", "OPS/c.jpg"),
            ("/l/A/x.m4b", "audiobook", "X", "A", "/l/A/x.epub", "OPS/c.jpg"),
            ("/l/A/y.epub", "readaloud", "Y", "A", "/l/A/y.epub", None)])
        self.assertEqual(view["books"][1]["key"], view["books"][2]["key"])
        # The EPUB has no cover: the audiobook shows its own.
        epub["info"]["cover"] = None
        book = [b for b in bridge.library_view([audio, epub])["books"] if b["kind"] == "audiobook"][0]
        self.assertEqual((book["coverPath"], book["cover"]), ("/l/A/x.m4b", "embedded.jpg"))

    def test_audiobook_cover(self):
        folder = os.path.join(self.tmp, "book")
        write_files(folder, {"01.mp3": ad.mp3([ad.apic(ad.PNG)])})
        covers = os.path.join(self.tmp, "covers")
        path = bridge.cover(folder, "embedded.png", "0123456789abcdef", covers)
        self.assertEqual(path, os.path.join(covers, "0123456789abcdef.png"))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), ad.PNG)

    def test_cover(self):
        epub = os.path.join(self.tmp, "b.epub")
        make_epub(epub, mini_entries() + [("OEBPS/cover.jpg", b"JPEG")])
        covers = os.path.join(self.tmp, "covers")
        name = "0123456789abcdef"
        with mock.patch.object(bridge, "_covers") as worker:
            self.assertEqual(bridge.request_cover(epub, "OEBPS/cover.jpg", name, covers), "")
            worker.submit.assert_called_once_with(name, epub, "OEBPS/cover.jpg", covers)
        path = bridge.cover(epub, "OEBPS/cover.jpg", name, covers)
        self.assertEqual(path, os.path.join(covers, name + ".jpg"))
        self.assertEqual(bridge.request_cover(epub, "OEBPS/cover.jpg", name, covers), path)
        for cover in ("OEBPS/cover.svg", "OEBPS/chapter.xhtml", None):
            self.assertEqual(bridge.cover(epub, cover, name, covers), "")

    def test_scan_now(self):
        books = os.path.join(self.tmp, "books")
        os.makedirs(books)
        make_epub(os.path.join(books, "b.epub"), mini_entries())
        covers = os.path.join(self.tmp, "covers")
        os.makedirs(covers)
        open(os.path.join(covers, "fedcba9876543210.png"), "w").close()
        cache_file = os.path.join(self.tmp, "library.json")
        view = bridge.scan_now([books], cache_file, covers)
        self.assertEqual([b["title"] for b in view["books"]], ["The Happy Prince"])
        self.assertEqual(os.listdir(covers), [])
        self.assertEqual(bridge.scan_now([books], cache_file, covers), {"unchanged": True})
        self.assertEqual(bridge.cached_library(cache_file, [books]), view)
        self.assertEqual(bridge.cached_library(cache_file, [books + "x"])["books"], [])


class PartnerTest(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.cache = os.path.join(self.tmp, "library.json")
        self.positions = os.path.join(self.tmp, "positions.json")

    def library(self, *entries):
        library._save_cache(self.cache, list(entries))

    def partner(self, path):
        return bridge.partner(path, self.cache, self.positions)

    def test_both_ways(self):
        self.library(entry("/l/A/x.epub", "X", ["A"], identifier="urn:isbn:1"),
                     entry("/l/A/x.m4b", "x", ["R"], kind="audiobook"),
                     entry("/l/A/talk.mp3", "Talk", kind="audiobook"),
                     entry("/l/A/y.epub", "Y", ["A"]))
        self.assertEqual(self.partner("/l/A/x.epub"), {
            "path": "/l/A/x.m4b", "key": "audio:x.m4b", "kind": "audiobook",
            "progress": -1, "time": 0})
        bridge.positions.save(self.positions, "urn:isbn:1",
                              {"spine": 2, "id": "", "fraction": 0, "progress": 0.25}, now=50)
        self.assertEqual(self.partner("/l/A/x.m4b"), {
            "path": "/l/A/x.epub", "key": "urn:isbn:1", "kind": "epub",
            "progress": 0.25, "time": 50})
        for alone in ("/l/A/talk.mp3", "/l/A/y.epub", "/l/A/gone.epub"):
            self.assertIsNone(self.partner(alone), alone)

    def test_key_of_an_epub_without_identifier(self):
        self.library(entry("/l/A/x.epub", "X"), entry("/l/A/x", "x", kind="audiobook"))
        self.assertEqual(self.partner("/l/A/x")["key"], "x.epub")
        self.assertEqual(self.partner("/l/A/x.epub")["key"], "audio:x")

    def test_readaloud_has_none(self):
        self.library(entry("/l/A/x.epub", "X", identifier="i"),
                     entry("/l/A/x-readaloud.epub", "X", identifier="i", audio=True),
                     entry("/l/A/x.mp3", "x", kind="audiobook"))
        for path in ("/l/A/x.epub", "/l/A/x-readaloud.epub", "/l/A/x.mp3"):
            self.assertIsNone(self.partner(path), path)

    def test_two_audiobooks_the_one_used_last(self):
        self.library(entry("/l/A/x.epub", "X", identifier="i"),
                     entry("/l/A/x.mp3", "x", kind="audiobook"),
                     entry("/l/A/x", "x", kind="audiobook"))
        bridge.positions.save(self.positions, "audio:x", {"file": "1.mp3", "ms": 0}, now=10)
        self.assertEqual(self.partner("/l/A/x.epub")["path"], "/l/A/x")
        bridge.positions.save(self.positions, "audio:x.mp3", {"file": "x.mp3", "ms": 0}, now=20)
        self.assertEqual(self.partner("/l/A/x.epub")["path"], "/l/A/x.mp3")
        # One with a progress before one used later without.
        bridge.positions.save(self.positions, "audio:x",
                              {"file": "1.mp3", "ms": 0, "progress": 0.5}, now=10)
        self.assertEqual(self.partner("/l/A/x.epub")["path"], "/l/A/x")

    def test_no_library_yet(self):
        self.assertIsNone(self.partner("/l/A/x.epub"))


class SearchTest(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.addCleanup(setattr, bridge, "_index", None)
        self.addCleanup(bridge._closed.clear)
        self.root = bridge.open_book(self._epub(), os.path.join(self.tmp, "cache"))["root"]

    def _epub(self):
        epub = os.path.join(self.tmp, "book.epub")
        make_epub(epub, mini_entries())
        return epub

    def run_search(self, key, root, query="", here=None, serial=0):
        with mock.patch.object(bridge, "_send") as send:
            bridge._search(key, root, serial, query, here)
        return send.call_args_list

    def test_search_sends_result(self):
        calls = self.run_search("search", self.root, "happy prince", {"spine": 0, "id": "", "fraction": 0}, 7)
        self.assertEqual(len(calls), 1)
        event, serial, result = calls[0][0]
        self.assertEqual((event, serial), ("search", 7))
        self.assertGreater(result["total"], 0)
        self.assertEqual(result["hits"][0]["chapter"], "Title Page")

    def test_prepare_builds_index_quietly(self):
        self.assertEqual(self.run_search("prepare", self.root), [])
        index = bridge._index
        self.assertEqual(index[0], self.root)
        self.run_search("search", self.root, "prince")
        self.assertIs(bridge._index, index)
        bridge.drop_search("/other")
        self.assertIs(bridge._index, index)
        bridge.drop_search(self.root)
        self.assertIsNone(bridge._index)

    def test_unexpected_error_still_answers(self):
        with mock.patch.object(bridge, "BookIndex", side_effect=ValueError("bad")), \
                mock.patch("traceback.print_exc"):
            calls = self.run_search("search", self.root + "x", "x", None, 2)
        self.assertEqual(calls[0][0][:2], ("search", 2))
        self.assertEqual(calls[0][0][2]["error"], "internal")

    def test_index_of_a_book_closed_meanwhile_is_not_kept(self):
        bridge.drop_search(self.root)
        self.run_search("prepare", self.root)
        self.assertIsNone(bridge._index)
        # Opened again: kept.
        with mock.patch.object(bridge._searcher, "submit"):
            bridge.prepare_search(self.root)
        self.run_search("prepare", self.root)
        self.assertEqual(bridge._index[0], self.root)

    def test_unreadable_book(self):
        calls = self.run_search("search", self.tmp, "x", None, 1)
        self.assertEqual(calls[0][0][2]["error"], "not_epub")


class HistoryTest(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.addCleanup(setattr, bridge, "_index", None)
        self.addCleanup(bridge._closed.clear)
        epub = os.path.join(self.tmp, "book.epub")
        make_epub(epub, mini_entries())
        self.root = bridge.open_book(epub, os.path.join(self.tmp, "cache"))["root"]
        self.path = os.path.join(self.tmp, "history.json")

    def run_history(self, root, serial=0):
        with mock.patch.object(bridge, "_send") as send:
            bridge._search("history", root, serial, self.path, "book")
        return send.call_args_list

    def test_add_history(self):
        with mock.patch("time.time", return_value=1000.7):
            self.assertIs(bridge.add_history(self.path, "book", "start", {"spine": 1, "id": "chapter-s1"}), True)
        with open(self.path) as f:
            self.assertEqual(json.load(f), {"books": {"book": [
                {"time": 1000, "kind": "start", "spine": 1, "id": "chapter-s1"}]}})
        self.assertEqual(bridge.add_history(self.path, "book", "nap", {"spine": 1, "id": ""})["error"], "invalid")
        self.assertEqual(bridge.add_history(self.tmp, "book", "start", {"spine": 1, "id": ""})["error"], "io")

    def test_history_with_sentences_and_chapters(self):
        with mock.patch("time.time", side_effect=[100, 200, 300]):
            for kind, ident in (("start", "chapter-s0"), ("timer", "chapter-s2"), ("start", "gone")):
                bridge.add_history(self.path, "book", kind, {"spine": 1, "id": ident})
        calls = self.run_history(self.root, 4)
        self.assertEqual(len(calls), 1)
        event, serial, result = calls[0][0]
        self.assertEqual((event, serial), ("history", 4))
        sessions = result["sessions"]
        self.assertEqual([(s["start"], s["end"]) for s in sessions], [(300, 300), (100, 200)])
        gone = sessions[0]["entries"][0]
        self.assertEqual((gone["kind"], gone["offset"], gone["chapter"]), ("start", -1, "Title Page"))
        timer, start = sessions[1]["entries"]
        self.assertEqual((timer["time"], timer["kind"], timer["spine"]), (200, "timer", 1))
        self.assertEqual(start["chapter"], "The Happy Prince.")
        self.assertTrue(start["line"])
        self.assertGreater(timer["offset"], start["offset"])

    def test_history_with_pages_read(self):
        with mock.patch("time.time", side_effect=[100, 200, 300]):
            bridge.add_history(self.path, "book", "read", {"spine": 1, "offset": 0})
            bridge.add_history(self.path, "book", "jump", {"spine": 1, "offset": 10 ** 6})
            bridge.add_history(self.path, "book", "start", {"spine": 1, "id": "chapter-s0"})
        sessions = self.run_history(self.root)[0][0][2]["sessions"]
        self.assertEqual([s["mode"] for s in sessions], ["listening", "reading"])
        gone, read = sessions[1]["entries"]
        self.assertEqual((gone["kind"], gone["offset"]), ("jump", -1))
        self.assertEqual((read["kind"], read["chapter"]), ("read", "The Happy Prince."))
        self.assertGreaterEqual(read["offset"], 0)
        self.assertTrue(read["text"] and read["line"].startswith(read["text"]))

    def test_history_of_unreadable_book(self):
        # Without entries the book is not read at all.
        self.assertEqual(self.run_history(self.tmp, 1)[0][0][2], {"sessions": []})
        bridge.add_history(self.path, "book", "read", {"spine": 0, "offset": 0})
        calls = self.run_history(self.tmp, 1)
        self.assertEqual(calls[0][0][:2], ("history", 1))
        self.assertEqual(calls[0][0][2]["error"], "not_epub")

    def test_no_history(self):
        self.assertEqual(self.run_history(self.root)[0][0][2], {"sessions": []})


class WorkerTest(unittest.TestCase):

    def test_newest_first_once_per_key_within_limit(self):
        ran = []
        gate = threading.Event()
        done = threading.Event()

        def run(key, value):
            if key == "first":
                gate.wait(5)
            ran.append(value)
            if len(ran) == 4:
                done.set()

        worker = bridge.Worker(run, limit=3)
        worker.submit("first", 0)
        time.sleep(0.1)  # the thread is busy with "first" now
        for key, value in (("a", 1), ("b", 2), ("a", 3), ("c", 4), ("d", 5)):
            worker.submit(key, value)
        gate.set()
        self.assertTrue(done.wait(5))
        # "a" replaced by its newer request, "b" dropped over the limit.
        self.assertEqual(ran, [0, 5, 4, 3])
