import json
import os
import unittest

from bookfish import bookmarks, bridge

from .helpers import TempDirTestCase


def mark(spine=1, offset=100, text="the cold shoulder", note=""):
    return {"spine": spine, "offset": offset, "length": len(text), "raw": text,
            "quote": text, "note": note}


class BookmarksTest(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.path = os.path.join(self.tmp, "bookmarks.json")

    def write(self, content):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(content)

    def test_add_and_load(self):
        first = bookmarks.add(self.path, "book", mark(), 1000)
        self.assertEqual(first, {"id": 1, "created": 1000, "changed": 1000, "spine": 1, "offset": 100,
                                 "length": 17, "raw": "the cold shoulder",
                                 "quote": "the cold shoulder", "note": ""})
        second = bookmarks.add(self.path, "book", mark(note="Idiom"), 1001)
        self.assertEqual(second["id"], 2)
        self.assertEqual(bookmarks.load(self.path, "book"), [first, second])
        self.assertEqual(bookmarks.load(self.path, "other"), [])
        self.assertEqual(os.listdir(self.tmp), ["bookmarks.json"])

    def test_order_of_the_book(self):
        bookmarks.add(self.path, "book", mark(spine=3, offset=0), 1)
        bookmarks.add(self.path, "book", mark(spine=1, offset=500), 2)
        bookmarks.add(self.path, "book", mark(spine=1, offset=20), 3)
        bookmarks.add(self.path, "book", mark(spine=1, offset=20), 4)
        self.assertEqual([(m["spine"], m["offset"], m["id"]) for m in bookmarks.load(self.path, "book")],
                         [(1, 20, 3), (1, 20, 4), (1, 500, 2), (3, 0, 1)])

    def test_books_apart(self):
        bookmarks.add(self.path, "a", mark(), 1)
        bookmarks.add(self.path, "b", mark(offset=7), 2)
        self.assertEqual([m["id"] for m in bookmarks.load(self.path, "b")], [1])
        self.assertTrue(bookmarks.delete(self.path, "a", 1))
        self.assertEqual(bookmarks.load(self.path, "a"), [])
        self.assertEqual(len(bookmarks.load(self.path, "b")), 1)

    def test_set_note(self):
        bookmarks.add(self.path, "book", mark(), 1000)
        changed = bookmarks.set_note(self.path, "book", 1, "Grüße 🐟\nzweite Zeile", 2000)
        self.assertEqual((changed["note"], changed["created"], changed["changed"]),
                         ("Grüße 🐟\nzweite Zeile", 1000, 2000))
        self.assertEqual(bookmarks.load(self.path, "book"), [changed])
        self.assertIsNone(bookmarks.set_note(self.path, "book", 9, "x", 3000))
        self.assertEqual(bookmarks.set_note(self.path, "book", 1, "", 3000)["note"], "")

    def test_delete(self):
        bookmarks.add(self.path, "book", mark(), 1)
        bookmarks.add(self.path, "book", mark(offset=5), 2)
        self.assertTrue(bookmarks.delete(self.path, "book", 1))
        self.assertFalse(bookmarks.delete(self.path, "book", 1))
        self.assertEqual([m["id"] for m in bookmarks.load(self.path, "book")], [2])
        # Ids are not used again while a later one exists.
        self.assertEqual(bookmarks.add(self.path, "book", mark(), 3)["id"], 3)

    def test_numbers_from_qml_come_as_floats(self):
        stored = bookmarks.add(self.path, "book", dict(mark(), spine=2.0, offset=40.0, length=17.0), 1.5)
        self.assertEqual((stored["spine"], stored["offset"], stored["length"]), (2, 40, 17))

    def test_invalid_bookmarks_are_refused(self):
        cases = [dict(mark(), spine=-1), dict(mark(), spine=True), dict(mark(), offset="3"),
                 dict(mark(), length=0), dict(mark(), length=bookmarks.MAX_TEXT + 1),
                 dict(mark(), raw=""), dict(mark(), raw=None), dict(mark(), quote=5),
                 dict(mark(), note="x" * (bookmarks.MAX_NOTE + 1)), dict(mark(), spine=1.5)]
        for case in cases:
            with self.assertRaises(ValueError, msg=case):
                bookmarks.add(self.path, "book", case, 1)
        self.assertFalse(os.path.exists(self.path))
        bookmarks.add(self.path, "book", mark(), 1)
        with self.assertRaises(ValueError):
            bookmarks.set_note(self.path, "book", 1, "x" * (bookmarks.MAX_NOTE + 1), 2)
        with self.assertRaises(ValueError):
            bookmarks.set_note(self.path, "book", 1, None, 2)

    def test_limit_per_book(self):
        books = {"book": [dict(mark(offset=i), id=i + 1, created=1, changed=1)
                          for i in range(bookmarks.MAX_PER_BOOK)]}
        self.write(json.dumps({"books": books}))
        with self.assertRaises(ValueError):
            bookmarks.add(self.path, "book", mark(), 2)
        bookmarks.add(self.path, "other", mark(), 2)

    def test_file_too_large_is_refused(self):
        big = "x" * bookmarks.MAX_NOTE
        bookmarks.MAX_SIZE, saved = 3 * len(big), bookmarks.MAX_SIZE
        try:
            bookmarks.add(self.path, "book", mark(note=big), 1)
            bookmarks.add(self.path, "book", mark(note=big), 2)
            with self.assertRaises(ValueError):
                bookmarks.add(self.path, "book", mark(note=big), 3)
            self.assertEqual(len(bookmarks.load(self.path, "book")), 2)
        finally:
            bookmarks.MAX_SIZE = saved

    def test_damaged_file_is_put_aside(self):
        self.write('{"books": {"book": [')
        self.assertEqual(bookmarks.load(self.path, "book"), [])
        # Reading leaves it alone.
        self.assertEqual(os.listdir(self.tmp), ["bookmarks.json"])
        bookmarks.add(self.path, "book", mark(), 1)
        names = sorted(os.listdir(self.tmp))
        self.assertEqual(len(names), 2)
        self.assertTrue(names[1].startswith("bookmarks.json.damaged-"))
        with open(os.path.join(self.tmp, names[1]), encoding="utf-8") as f:
            self.assertEqual(f.read(), '{"books": {"book": [')
        self.assertEqual(len(bookmarks.load(self.path, "book")), 1)

    def test_second_damaged_file_does_not_replace_the_first(self):
        for n in range(2):
            self.write("not json {}".format(n))
            os.utime(self.path, (1000, 1000))
            bookmarks.add(self.path, "book", mark(), 1)
        aside = sorted(name for name in os.listdir(self.tmp) if "damaged" in name)
        self.assertEqual(len(aside), 2)

    def test_wrong_structure_counts_as_damaged(self):
        for content in ('[]', '{"books": []}', '{"books": {"book": {}}}'):
            self.write(content)
            bookmarks.add(self.path, "book", mark(), 1)
        self.assertEqual(len([n for n in os.listdir(self.tmp) if "damaged" in n]), 3)

    def test_entries_not_understood_stay(self):
        odd = {"id": 7, "kind": "from a later version"}
        self.write(json.dumps({"books": {"book": [odd, dict(mark(), id=3, created=1, changed=1)]}}))
        self.assertEqual([m["id"] for m in bookmarks.load(self.path, "book")], [3])
        added = bookmarks.add(self.path, "book", mark(), 2)
        # Past the id of the entry not understood, too.
        self.assertEqual(added["id"], 8)
        bookmarks.set_note(self.path, "book", 3, "n", 3)
        bookmarks.delete(self.path, "book", 8)
        with open(self.path, encoding="utf-8") as f:
            self.assertIn(odd, json.load(f)["books"]["book"])

    def test_later_versions_keep_their_fields(self):
        later = dict(mark(), id=2, created=1, changed=1, color="blue")
        self.write(json.dumps({"books": {"book": [later]}, "settings": {"sort": "time"}}))
        bookmarks.set_note(self.path, "book", 2, "n", 5)
        bookmarks.add(self.path, "book", mark(), 6)
        with open(self.path, encoding="utf-8") as f:
            stored = json.load(f)
        self.assertEqual(stored["settings"], {"sort": "time"})
        self.assertEqual(stored["books"]["book"][0]["color"], "blue")
        self.assertEqual(stored["books"]["book"][0]["note"], "n")

    def test_ids_of_entries_not_understood_are_not_used_again(self):
        self.write(json.dumps({"books": {"book": [{"id": 2, "kind": "later"}]}}))
        self.assertEqual(bookmarks.add(self.path, "book", mark(), 1)["id"], 3)

    @unittest.skipIf(not hasattr(os, "geteuid") or os.geteuid() == 0, "root may read anything")
    def test_file_that_cannot_be_opened_is_not_put_aside(self):
        bookmarks.add(self.path, "book", mark(), 1)
        os.chmod(self.path, 0)
        try:
            with self.assertRaises(OSError):
                bookmarks.load(self.path, "book")
            with self.assertRaises(OSError):
                bookmarks.add(self.path, "book", mark(), 2)
            self.assertEqual(os.listdir(self.tmp), ["bookmarks.json"])
        finally:
            os.chmod(self.path, 0o600)

    def test_bridge(self):
        added = bridge.add_bookmark(self.path, "book", mark())
        self.assertEqual(added["id"], 1)
        self.assertEqual(bridge.add_bookmark(self.path, "book", dict(mark(), raw=""))["error"], "invalid")
        self.assertEqual(bridge.set_bookmark_note(self.path, "book", 1.0, "n")["note"], "n")
        self.assertEqual(bridge.set_bookmark_note(self.path, "book", 5, "n")["error"], "missing")
        self.assertEqual(len(bridge.load_bookmarks(self.path, "book")), 1)
        self.assertTrue(bridge.delete_bookmark(self.path, "book", 1))
        self.assertEqual(bridge.load_bookmarks(self.path, "book"), [])
