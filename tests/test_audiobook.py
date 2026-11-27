import json
import os
from unittest import mock

from bookfish import audiobook, bridge, library
from bookfish.audioutil import AudioError

from . import audiodata as ad
from .helpers import TempDirTestCase, write_files

FRAMES_MS = 100 * ad.FRAME_MS


class AudiobookTest(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.cache = os.path.join(self.tmp, "cache")

    def test_file_with_chapter_marks(self):
        write_files(self.tmp, {"b.mp3": ad.mp3([ad.chap("c2", 1000, 2000, "Two"),
                                                ad.chap("c1", 0, 1000, "One")],
                                               audio_frames=100)})
        book = audiobook.open_audiobook(os.path.join(self.tmp, "b.mp3"), self.cache)
        duration = book["duration"]
        self.assertAlmostEqual(duration, FRAMES_MS, delta=30)
        self.assertEqual(book["root"], self.tmp)
        self.assertTrue(book["complete"])
        self.assertEqual(book["chapters"], [
            {"title": "One", "file": "b.mp3", "begin": 0, "end": 1000, "length": 1000, "start": 0},
            {"title": "Two", "file": "b.mp3", "begin": 1000, "end": None,
             "length": duration - 1000, "start": 1000}])
        json.dumps(book)

    def test_file_without_marks_is_one_chapter(self):
        write_files(self.tmp, {"b.mp3": ad.mp3([ad.text("TIT2", "Tag title")], audio_frames=100)})
        chapters = audiobook.open_audiobook(os.path.join(self.tmp, "b.mp3"), self.cache)["chapters"]
        self.assertEqual(len(chapters), 1)
        # The page shows the book's title for it.
        self.assertEqual((chapters[0]["title"], chapters[0]["begin"], chapters[0]["end"]),
                         ("", 0, None))

    def test_m4b(self):
        write_files(self.tmp, {"b.m4b": ad.m4b(60000, [(0, "Intro"), (20000, "Main")])})
        book = audiobook.open_audiobook(os.path.join(self.tmp, "b.m4b"), self.cache)
        self.assertEqual([(c["title"], c["begin"], c["end"], c["length"], c["start"])
                          for c in book["chapters"]],
                         [("Intro", 0, 20000, 20000, 0), ("Main", 20000, None, 40000, 20000)])
        self.assertEqual(book["duration"], 60000)

    def test_not_audio(self):
        write_files(self.tmp, {"b.mp3": b"nothing", "empty/x.txt": ""})
        with self.assertRaises(AudioError):
            audiobook.open_audiobook(os.path.join(self.tmp, "b.mp3"), self.cache)
        with self.assertRaises(AudioError):
            audiobook.open_audiobook(os.path.join(self.tmp, "empty"), self.cache)
        with self.assertRaises(OSError):
            audiobook.open_audiobook(os.path.join(self.tmp, "gone.mp3"), self.cache)

    def folder(self):
        folder = os.path.join(self.tmp, "Book")
        write_files(folder, {
            "part-10.mp3": ad.mp3([ad.text("TIT2", "Ten")], audio_frames=200),
            "part-2.mp3": ad.mp3([ad.text("TIT2", "Two")], audio_frames=100),
            # Marks in folder files belong to the whole book: not read.
            "part-3.mp3": ad.mp3([ad.chap("c1", 0, 500, "Mark")], audio_frames=100),
            "cover.jpg": ad.JPEG})
        return folder

    def test_folder_opens_with_estimates(self):
        folder = self.folder()
        book = audiobook.open_audiobook(folder, self.cache)
        self.assertFalse(book["complete"])
        self.assertEqual(book["root"], folder)
        self.assertEqual([(c["title"], c["file"], c["begin"], c["end"]) for c in book["chapters"]],
                         [("part-2", "part-2.mp3", 0, None), ("part-3", "part-3.mp3", 0, None),
                          ("part-10", "part-10.mp3", 0, None)])
        # Same bitrate as the first: close to the real lengths.
        lengths = [c["length"] for c in book["chapters"]]
        for length, real in zip(lengths, (FRAMES_MS, FRAMES_MS, 2 * FRAMES_MS)):
            self.assertAlmostEqual(length, real, delta=real * 0.05)
        self.assertEqual([c["start"] for c in book["chapters"]],
                         [0, lengths[0], lengths[0] + lengths[1]])

    def test_folder_read_and_cached(self):
        folder = self.folder()
        book = audiobook.read_folder(folder, self.cache)
        self.assertTrue(book["complete"])
        self.assertEqual([c["title"] for c in book["chapters"]], ["Two", "part-3", "Ten"])
        self.assertAlmostEqual(book["chapters"][2]["length"], 2 * FRAMES_MS, delta=30)
        self.assertEqual(audiobook.open_audiobook(folder, self.cache), book)

    def test_cache_dropped_when_a_file_changes(self):
        folder = self.folder()
        audiobook.read_folder(folder, self.cache)
        write_files(folder, {"part-2.mp3": ad.mp3([ad.text("TIT2", "New")], audio_frames=50)})
        self.assertFalse(audiobook.open_audiobook(folder, self.cache)["complete"])
        audiobook.read_folder(folder, self.cache)
        os.rename(os.path.join(folder, "part-3.mp3"), os.path.join(folder, "part-4.mp3"))
        self.assertFalse(audiobook.open_audiobook(folder, self.cache)["complete"])

    def test_damaged_cache_ignored(self):
        folder = self.folder()
        audiobook.read_folder(folder, self.cache)
        cache_file = os.path.join(self.cache, os.listdir(self.cache)[0])
        with open(cache_file) as f:
            stored = json.load(f)
        for files in ([], [{"title": 3, "duration": 1}] * 3, [{"title": "", "duration": -1}] * 3,
                      [{"title": "", "duration": True}] * 3, ["x"] * 3,
                      [{"title": "x" * 1001, "duration": 1}] * 3):
            with open(cache_file, "w") as f:
                json.dump(dict(stored, files=files), f)
            self.assertFalse(audiobook.open_audiobook(folder, self.cache)["complete"], files)
        with open(cache_file, "w") as f:
            f.write("{")
        self.assertFalse(audiobook.open_audiobook(folder, self.cache)["complete"])

    def test_unreadable_files_in_folder(self):
        folder = os.path.join(self.tmp, "Book")
        write_files(folder, {"1.mp3": b"junk", "2.mp3": ad.mp3([ad.text("TIT2", "T")])})
        book = audiobook.open_audiobook(folder, self.cache)
        # The first unreadable: a usual bitrate is assumed.
        self.assertEqual(book["chapters"][0]["length"], 4 // 16)
        book = audiobook.read_folder(folder, self.cache)
        self.assertEqual([(c["title"], c["length"]) for c in book["chapters"]][0], ("1", 0))

    def test_cache_not_writable(self):
        folder = self.folder()
        write_files(self.tmp, {"file": ""})
        book = audiobook.read_folder(folder, os.path.join(self.tmp, "file"))
        self.assertTrue(book["complete"])


class BridgeAudiobookTest(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.library = os.path.join(self.tmp, "library")
        self.paths = {"library": os.path.join(self.tmp, "library.json"),
                      "covers": os.path.join(self.tmp, "covers"),
                      "audio": os.path.join(self.tmp, "audiobooks")}

    def open(self, path):
        with mock.patch.object(bridge, "_audiobooks") as worker:
            book = bridge.open_audiobook(path, self.paths["library"], [self.library],
                                         self.paths["covers"], self.paths["audio"])
        return book, worker

    def test_file_as_the_library_shows_it(self):
        write_files(self.library, {"talk.mp3": ad.mp3([ad.text("TALB", "Talk"),
                                                         ad.text("TPE1", "Tag Author"),
                                                         ad.apic(ad.JPEG)])})
        library.scan([self.library], self.paths["library"])
        path = os.path.join(self.library, "talk.mp3")
        book, worker = self.open(path)
        json.dumps(book)
        self.assertEqual((book["kind"], book["path"], book["key"], book["title"], book["authors"]),
                         ("audiobook", path, "audio:talk.mp3", "Talk", ["Tag Author"]))
        self.assertTrue(book["cover"].startswith(self.paths["covers"]))
        self.assertTrue(os.path.isfile(book["cover"]))
        self.assertEqual(len(book["chapters"]), 1)
        worker.submit.assert_not_called()

    def test_folder_read_in_a_thread(self):
        folder = os.path.join(self.library, "Book")
        write_files(folder, {"1.mp3": ad.mp3([ad.text("TALB", "Album"), ad.text("TIT2", "One")])})
        book, worker = self.open(folder)
        # Not in the library cache yet: the tags tell.
        self.assertEqual((book["title"], book["authors"], book["cover"], book["complete"]),
                         ("Album", [], "", False))
        worker.submit.assert_called_once_with(folder, self.paths["audio"], None)
        with mock.patch.object(bridge, "_send") as send:
            bridge._read_audiobook(folder, self.paths["audio"])
        event, path, result = send.call_args[0]
        self.assertEqual((event, path, result["complete"], result["chapters"][0]["title"]),
                         ("audiobook", folder, True, "One"))
        self.assertTrue(self.open(folder)[0]["complete"])

    def test_album_of_a_folder(self):
        folder = os.path.join(self.library, "Books")
        write_files(folder, {
            "a1.mp3": ad.mp3([ad.text("TALB", "Hobbit"), ad.text("TIT2", "One"), ad.apic(ad.JPEG)]),
            "a2.mp3": ad.mp3([ad.text("TALB", "hobbit"), ad.text("TIT2", "Two")]),
            "a3.mp3": ad.mp3([ad.text("TALB", "Hobbit"), ad.text("TIT2", "Three")]),
            "b.mp3": ad.mp3([ad.text("TALB", "Emil")])})
        path = library.album_path(folder, "hobbit")
        for scanned in (False, True):
            if scanned:
                library.scan([self.library], self.paths["library"])
            book, worker = self.open(path)
            json.dumps(book)
            self.assertEqual((book["path"], book["key"], book["title"], book["root"]),
                             (path, "audio:Books//hobbit", "Hobbit", folder))
            self.assertEqual([c["file"] for c in book["chapters"]], ["a1.mp3", "a2.mp3", "a3.mp3"])
            files = [os.path.join(folder, name) for name in ("a1.mp3", "a2.mp3", "a3.mp3")]
            worker.submit.assert_called_once_with(path, self.paths["audio"], files)
        self.assertTrue(os.path.isfile(book["cover"]))
        with mock.patch.object(bridge, "_send") as send:
            bridge._read_audiobook(path, self.paths["audio"], files)
        result = send.call_args[0][2]
        self.assertEqual([c["title"] for c in result["chapters"]], ["One", "Two", "Three"])
        self.assertTrue(self.open(path)[0]["complete"])
        self.assertTrue(bridge.is_audiobook(path))
        self.assertTrue(bridge.is_audiobook(library.album_path(folder, "x.epub")))
        # Opened last: still in the list of books read last.
        positions_file = os.path.join(self.tmp, "positions.json")
        bridge.save_last_book(positions_file, path)
        self.assertEqual(bridge.recent_books(positions_file), [path])

    def test_errors(self):
        write_files(self.library, {"x.mp3": b"junk"})
        self.assertEqual(self.open(os.path.join(self.library, "x.mp3"))[0]["error"], "not_audio")
        self.assertEqual(self.open(os.path.join(self.library, "gone.mp3"))[0]["error"], "io")
        os.makedirs(os.path.join(self.library, "Gone"))
        with mock.patch.object(bridge, "_send") as send:
            bridge._read_audiobook(os.path.join(self.library, "Gone"), self.paths["audio"])
        self.assertEqual(send.call_args[0][2]["error"], "not_audio")

    def test_audio_history(self):
        path = os.path.join(self.tmp, "history.json")
        self.assertEqual(bridge.audio_history(path, "audio:b"), {"sessions": []})
        with mock.patch("time.time", side_effect=[100, 200]):
            bridge.add_history(path, "audio:b", "start", {"spine": 2, "ms": 5000})
            bridge.add_history(path, "audio:b", "timer", {"spine": 3, "ms": 0})
        sessions = bridge.audio_history(path, "audio:b")["sessions"]
        self.assertEqual(sessions, [{"mode": "listening", "start": 100, "end": 200, "entries": [
            {"time": 200, "kind": "timer", "spine": 3, "ms": 0},
            {"time": 100, "kind": "start", "spine": 2, "ms": 5000}]}])


class EstimateTest(TempDirTestCase):

    def test_pictures_in_the_tags_left_out(self):
        # A short first file with a large picture: its size would make every
        # other file seem far shorter.
        picture = ad.JPEG + bytes(200000)
        folder = os.path.join(self.tmp, "Book")
        write_files(folder, {"1.mp3": ad.mp3([ad.apic(picture)], audio_frames=50),
                             "2.mp3": ad.mp3([ad.apic(picture)], audio_frames=1000)})
        chapters = audiobook.open_audiobook(folder, os.path.join(self.tmp, "c"))["chapters"]
        self.assertAlmostEqual(chapters[1]["length"], 1000 * ad.FRAME_MS, delta=1000 * ad.FRAME_MS * 0.03)

    def test_names_not_utf8_left_out(self):
        folder = os.path.join(self.tmp, "Book")
        write_files(folder, {"1.mp3": ad.mp3([ad.text("TIT2", "T")])})
        try:
            with open(os.path.join(os.fsencode(folder), b"2\xff.mp3"), "wb") as f:
                f.write(ad.mp3([ad.text("TIT2", "T")]))
        except OSError:
            self.skipTest("file system refuses the name")
        book = audiobook.open_audiobook(folder, os.path.join(self.tmp, "c"))
        self.assertEqual([c["file"] for c in book["chapters"]], ["1.mp3"])

    def test_unexpected_error_in_one_file(self):
        folder = os.path.join(self.tmp, "Book")
        write_files(folder, {"1.mp3": ad.mp3([ad.text("TIT2", "One")]),
                             "2.mp3": ad.mp3([ad.text("TIT2", "Two")])})
        real = audiobook._read

        def read(file, chapters):
            if file.endswith("2.mp3"):
                raise RuntimeError("parser bug")
            return real(file, chapters)

        with mock.patch.object(audiobook, "_read", read):
            book = audiobook.read_folder(folder, os.path.join(self.tmp, "c"))
        self.assertEqual([c["title"] for c in book["chapters"]], ["One", "2"])

    def test_unexpected_error_on_opening_answers(self):
        with mock.patch.object(audiobook, "open_audiobook", side_effect=RuntimeError("bug")), \
                mock.patch("traceback.print_exc"):
            result = bridge.open_audiobook(self.tmp, "", [], "", "")
        self.assertEqual(result["error"], "internal")
