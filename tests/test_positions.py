import json
import os

from bookfish import positions

from .helpers import TempDirTestCase

POSITION = {"spine": 3, "id": "item19-s5", "fraction": 0.25, "heard": False, "offset": 1200}


class PositionsTest(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.path = os.path.join(self.tmp, "positions.json")

    def write(self, content):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(content)

    def test_save_and_load(self):
        positions.save(self.path, "book", POSITION)
        self.assertEqual(positions.load(self.path, "book"), POSITION)

    def test_two_books(self):
        other = {"spine": 0, "id": "", "fraction": 1}
        positions.save(self.path, "a", POSITION)
        positions.save(self.path, "b", other)
        self.assertEqual(positions.load(self.path, "a"), POSITION)
        self.assertEqual(positions.load(self.path, "b"),
                         {"spine": 0, "id": "", "fraction": 1.0, "heard": False, "offset": -1})

    def test_overwrite(self):
        positions.save(self.path, "book", POSITION)
        positions.save(self.path, "book", dict(POSITION, spine=4))
        self.assertEqual(positions.load(self.path, "book")["spine"], 4)

    def test_no_temporary_file_left(self):
        positions.save(self.path, "book", POSITION)
        self.assertEqual(os.listdir(self.tmp), ["positions.json"])

    def test_extra_fields_dropped(self):
        positions.save(self.path, "book", dict(POSITION, extra="x"))
        self.assertEqual(positions.load(self.path, "book"), POSITION)

    def test_heard(self):
        positions.save(self.path, "book", dict(POSITION, heard=True))
        self.assertIs(positions.load(self.path, "book")["heard"], True)
        # Only true itself counts.
        positions.save(self.path, "book", dict(POSITION, heard="yes"))
        self.assertIs(positions.load(self.path, "book")["heard"], False)

    def test_offset(self):
        # Not known (listening, a page without text), or from an older file.
        for given in [-1, -5, 2.5, True, "7", None]:
            positions.save(self.path, "book", dict(POSITION, offset=given))
            self.assertEqual(positions.load(self.path, "book")["offset"], -1, given)
        no_offset = dict(POSITION)
        del no_offset["offset"]
        positions.save(self.path, "book", no_offset)
        self.assertEqual(positions.load(self.path, "book")["offset"], -1)
        # A number from QML may come as a float.
        positions.save(self.path, "book", dict(POSITION, offset=7.0))
        self.assertEqual(positions.load(self.path, "book")["offset"], 7)

    def test_unknown_book_or_missing_file(self):
        self.assertIsNone(positions.load(self.path, "book"))
        positions.save(self.path, "book", POSITION)
        self.assertIsNone(positions.load(self.path, "other"))

    def test_damaged_files(self):
        for content in ["{", "[1, 2]", '"text"', '{"books": []}', "[" * 100000, "\udcff"]:
            with self.subTest(content=content[:10]):
                with open(self.path, "w", encoding="utf-8",
                          errors="surrogateescape") as f:
                    f.write(content)
                self.assertIsNone(positions.load(self.path, "book"))

    def test_damaged_file_is_replaced(self):
        self.write("{")
        positions.save(self.path, "book", POSITION)
        self.assertEqual(positions.load(self.path, "book"), POSITION)

    def test_too_large(self):
        self.write(json.dumps({"books": {"book": POSITION}, "pad": "x" * positions.MAX_SIZE}))
        self.assertIsNone(positions.load(self.path, "book"))

    def test_invalid_positions(self):
        for bad in [None, [], {}, dict(POSITION, spine=-1), dict(POSITION, spine=True),
                    dict(POSITION, spine=1.5), dict(POSITION, id=5),
                    dict(POSITION, id="x" * 1001), dict(POSITION, fraction=1.5),
                    dict(POSITION, fraction=float("nan")), dict(POSITION, fraction="0")]:
            with self.subTest(position=bad):
                self.write(json.dumps({"books": {"book": bad}}))
                self.assertIsNone(positions.load(self.path, "book"))
                with self.assertRaises(ValueError):
                    positions.save(self.path, "book", bad)


class LastBookTest(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.path = os.path.join(self.tmp, "positions.json")
        self.epub = os.path.join(self.tmp, "book.epub")
        open(self.epub, "w").close()

    def test_none_at_first(self):
        self.assertIsNone(positions.load_last(self.path))

    def test_save_and_load(self):
        positions.save_last(self.path, self.epub)
        self.assertEqual(positions.load_last(self.path), self.epub)

    def test_kept_next_to_positions(self):
        positions.save(self.path, "book", POSITION)
        positions.save_last(self.path, self.epub)
        positions.save(self.path, "other", POSITION)
        self.assertEqual(positions.load_last(self.path), self.epub)
        self.assertEqual(positions.load(self.path, "book"), POSITION)

    def test_file_gone(self):
        positions.save_last(self.path, self.epub)
        os.remove(self.epub)
        self.assertIsNone(positions.load_last(self.path))

    def test_name_not_valid_utf8(self):
        positions.save(self.path, "b\udcfcch.epub", POSITION)
        self.assertEqual(positions.load(self.path, "b\udcfcch.epub"), POSITION)

    def test_not_a_string(self):
        with open(self.path, "w") as f:
            json.dump({"books": {}, "last": 5}, f)
        self.assertIsNone(positions.load_last(self.path))


class RecentTest(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.path = os.path.join(self.tmp, "positions.json")
        self.epubs = []
        for name in "abcd":
            epub = os.path.join(self.tmp, name + ".epub")
            open(epub, "w").close()
            self.epubs.append(epub)

    def test_newest_first_three_at_most(self):
        a, b, c, d = self.epubs
        for epub in (a, b, c, a, d):
            positions.save_last(self.path, epub)
        self.assertEqual(positions.load_recent(self.path), [d, a, c])
        self.assertEqual(positions.load_last(self.path), d)

    def test_files_gone_left_out(self):
        a, b = self.epubs[:2]
        positions.save_last(self.path, a)
        positions.save_last(self.path, b)
        os.remove(b)
        self.assertEqual(positions.load_recent(self.path), [a])

    def test_old_file_and_damage(self):
        self.assertEqual(positions.load_recent(self.path), [])
        with open(self.path, "w") as f:
            json.dump({"books": {}, "last": self.epubs[0], "recent": [5, self.epubs[1]]}, f)
        self.assertEqual(positions.load_recent(self.path), [self.epubs[1]])


class AudioPositionTest(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.path = os.path.join(self.tmp, "positions.json")

    def test_save_and_load(self):
        positions.save(self.path, "audio:book", {"file": "book-002.mp3", "ms": 61000.0,
                                                 "spine": 7})
        self.assertEqual(positions.load(self.path, "audio:book"),
                         {"file": "book-002.mp3", "ms": 61000})

    def test_invalid(self):
        for position in ({"file": "", "ms": 0}, {"file": "a.mp3", "ms": -1},
                         {"file": "a.mp3", "ms": True}, {"file": "a.mp3", "ms": float("nan")},
                         {"file": "a.mp3", "ms": "5"}, {"file": 3, "ms": 0},
                         {"file": "x" * 1001, "ms": 0}, {"file": "a.mp3"}):
            with self.assertRaises(ValueError, msg=position):
                positions.save(self.path, "audio:book", position)

    def test_folder_as_last_and_recent_book(self):
        folder = os.path.join(self.tmp, "Book")
        os.mkdir(folder)
        positions.save_last(self.path, folder)
        self.assertEqual(positions.load_last(self.path), folder)
        self.assertEqual(positions.load_recent(self.path), [folder])
        os.rmdir(folder)
        self.assertIsNone(positions.load_last(self.path))
        self.assertEqual(positions.load_recent(self.path), [])


class ProgressTest(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.path = os.path.join(self.tmp, "positions.json")

    def test_progress_and_time_kept(self):
        self.write_position(dict(POSITION, progress=0.43, time=1700000000.0))
        self.assertEqual(positions.load(self.path, "book"),
                         dict(POSITION, progress=0.43, time=1700000000))
        for stamp in (-1, 2.5, True, "1", float("inf")):
            self.write_position(dict(POSITION, time=stamp))
            self.assertEqual(positions.load(self.path, "book"), POSITION, stamp)
        positions.save(self.path, "audio:b", {"file": "b.mp3", "ms": 5, "progress": 1})
        self.assertEqual(positions.load(self.path, "audio:b"),
                         {"file": "b.mp3", "ms": 5, "progress": 1.0})

    def test_bad_values_dropped_not_the_place(self):
        for progress, stamp in [(-0.1, -1), (1.5, 2.5), (float("nan"), True), ("0.5", "1"),
                                (True, None), (None, float("inf"))]:
            with self.subTest(progress=progress, time=stamp):
                positions.save(self.path, "book", dict(POSITION, progress=progress, time=stamp))
                self.assertEqual(positions.load(self.path, "book"), POSITION)

    def test_time_only_when_moved(self):
        positions.save(self.path, "book", POSITION, now=100)
        self.assertEqual(positions.load(self.path, "book")["time"], 100)
        # Opened and closed again, laid out anew: the place may differ a
        # little, the book was not used.
        positions.save(self.path, "book", dict(POSITION, offset=1100, fraction=0.2))
        self.assertEqual(positions.load(self.path, "book")["time"], 100)
        # A time from QML does not count.
        positions.save(self.path, "book", dict(POSITION, time=999))
        self.assertEqual(positions.load(self.path, "book")["time"], 100)
        positions.save(self.path, "book", dict(POSITION, time=999), now=400)
        self.assertEqual(positions.load(self.path, "book")["time"], 400)

    def test_never_moved_has_no_time(self):
        positions.save(self.path, "book", POSITION)
        self.assertNotIn("time", positions.load(self.path, "book"))
        positions.save(self.path, "audio:b", {"file": "b.mp3", "ms": 5})
        self.assertNotIn("time", positions.load(self.path, "audio:b"))

    def test_progress_stays_until_moved(self):
        # Saved before the reader knows the lengths of the chapters.
        positions.save(self.path, "book", dict(POSITION, progress=0.4), now=100)
        positions.save(self.path, "book", POSITION)
        self.assertEqual(positions.load(self.path, "book")["progress"], 0.4)
        positions.save(self.path, "book", dict(POSITION, progress=0.5))
        self.assertEqual(positions.load(self.path, "book")["progress"], 0.5)
        positions.save(self.path, "book", dict(POSITION, spine=4), now=300)
        self.assertNotIn("progress", positions.load(self.path, "book"))

    def test_place_from_an_older_file_has_no_time(self):
        self.write_position(POSITION)
        positions.save(self.path, "book", POSITION)
        self.assertNotIn("time", positions.load(self.path, "book"))
        positions.save(self.path, "book", dict(POSITION, spine=4), now=200)
        self.assertEqual(positions.load(self.path, "book")["time"], 200)

    def write_position(self, position):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"books": {"book": position}}, f)
