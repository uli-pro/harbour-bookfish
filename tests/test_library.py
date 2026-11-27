import json
import os
import struct
import unittest
from unittest import mock

from bookfish import archive, library
from bookfish.errors import EpubError
from bookfish.library import (BookFile, book_info, broken_info, card_folders, extract_cover,
                               list_books, load_cached, normal_identifier,
                               prune_covers, scan, without_replaced)

from . import audiodata as ad
from .helpers import TempDirTestCase, make_epub, mini_entries, write_files


class ListBooksTest(TempDirTestCase):

    def path(self, name):
        return os.path.join(self.tmp, *name.split("/"))

    def test_finds_epubs_in_subfolders_sorted_by_name(self):
        write_files(self.tmp, {
            "b/zebra.epub": "", "apple.EPUB": "", "a/Mango.epub": "",
            "notes.txt": "", "book.epub.part": ""})
        self.assertEqual(list_books([self.tmp]), [
            BookFile(self.path("apple.EPUB"), "apple"),
            BookFile(self.path("a/Mango.epub"), "Mango"),
            BookFile(self.path("b/zebra.epub"), "zebra")])

    def test_hidden_files_and_folders_left_out(self):
        write_files(self.tmp, {".hidden.epub": "", ".trash/old.epub": "",
                               "book.epub": ""})
        self.assertEqual([b.name for b in list_books([self.tmp])], ["book"])

    def test_links_to_folders_not_followed(self):
        write_files(self.tmp, {"books/book.epub": ""})
        os.symlink(self.tmp, self.path("books/loop"))
        self.assertEqual([b.path for b in list_books([self.path("books")])],
                         [self.path("books/book.epub")])

    def test_deep_folders_left_out(self):
        write_files(self.tmp, {"/".join(["d"] * 32) + "/deep.epub": "",
                               "/".join(["d"] * 33) + "/deeper.epub": ""})
        self.assertEqual([b.name for b in list_books([self.tmp])], ["deep"])
        # os.walk recursed into all of them before Python 3.12.
        # makedirs and rmtree recurse as well.
        folders = [self.path("e")]
        for _ in range(1199):
            folders.append(os.path.join(folders[-1], "e"))
        for folder in folders:
            os.mkdir(folder)
        self.addCleanup(lambda: [os.rmdir(folder) for folder in reversed(folders)])
        self.assertEqual([b.name for b in list_books([self.tmp])], ["deep"])

    def test_several_folders(self):
        write_files(self.tmp, {"one/b.epub": "", "two/a.epub": ""})
        self.assertEqual(
            [b.name for b in list_books([self.path("one"), self.path("two")])],
            ["a", "b"])

    def test_missing_folder(self):
        self.assertEqual(list_books([self.path("missing")]), [])

    def test_link_to_a_listed_book_lists_it_once(self):
        write_files(self.tmp, {"a.epub": ""})
        os.symlink(self.path("a.epub"), self.path("b.epub"))
        self.assertEqual(len(list_books([self.tmp])), 1)

    def test_names_not_valid_utf8_left_out(self):
        write_files(self.tmp, {"good.epub": ""})
        open(os.path.join(self.tmp.encode(), b"bad\xff.epub"), "w").close()
        self.assertEqual([b.name for b in list_books([self.tmp])], ["good"])

    def test_same_folder_twice_lists_books_once(self):
        write_files(self.tmp, {"a.epub": ""})
        self.assertEqual(len(list_books([self.tmp, self.tmp])), 1)


class CardFoldersTest(TempDirTestCase):

    def test_folders_only_sorted(self):
        write_files(self.tmp, {"b-card/x": "", "a-card/x": "", "file": ""})
        self.assertEqual(card_folders(self.tmp), [os.path.join(self.tmp, "a-card"),
                                                  os.path.join(self.tmp, "b-card")])

    def test_missing(self):
        self.assertEqual(card_folders(os.path.join(self.tmp, "missing")), [])


CONTAINER = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="OPS/p.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""


def opf(identifier="id-1", title="A Book", creator="<dc:creator>Ann Author</dc:creator>",
        extra="", overlay=False):
    return """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/"
         version="3.0" unique-identifier="uid">
  <metadata><dc:identifier id="uid">{}</dc:identifier><dc:title>{}</dc:title>{}{}</metadata>
  <manifest><item id="c" href="c.xhtml" media-type="application/xhtml+xml"{}/>
    <item id="s" href="c.smil" media-type="application/smil+xml"/>
    <item id="img" href="cover.png" media-type="image/png" properties="cover-image"/></manifest>
  <spine><itemref idref="c"/></spine>
</package>""".format(identifier, title, creator, extra,
                     ' media-overlay="s"' if overlay else "")


def write_book(path, package=None, audio=False, cover=b"PNG"):
    entries = [("mimetype", b"application/epub+zip"), ("META-INF/container.xml", CONTAINER),
               ("OPS/p.opf", package or opf()), ("OPS/c.xhtml", "<html/>")]
    if cover is not None:
        entries.append(("OPS/cover.png", cover))
    if audio:
        entries.append(("OPS/c.smil", "<smil/>"))
    make_epub(path, entries)


class BookInfoTest(TempDirTestCase):

    def test_read_from_the_zip(self):
        path = os.path.join(self.tmp, "b.epub")
        write_book(path, opf(extra='<meta name="calibre:series" content="S"/>'
                                   '<meta name="calibre:series_index" content="3"/>', overlay=True),
                   audio=True)
        self.assertEqual(book_info(path), {
            "identifier": "id-1", "title": "A Book", "authors": ["Ann Author"], "sort": "Ann Author",
            "series": "S", "index": 3.0, "cover": "OPS/cover.png", "audio": True, "broken": False,
            "kind": "epub"})

    def test_unusable_books_raise(self):
        cases = {
            "notzip.epub": b"no zip",
            "nocontainer.epub": [("mimetype", b"application/epub+zip")],
            "dtd.epub": [("META-INF/container.xml", CONTAINER),
                         ("OPS/p.opf", '<!DOCTYPE p [<!ENTITY a "x">]><p/>')],
        }
        for name, content in cases.items():
            path = os.path.join(self.tmp, name)
            if isinstance(content, bytes):
                write_files(self.tmp, {name: content})
            else:
                make_epub(path, content)
            with self.assertRaises(Exception, msg=name):
                book_info(path)

    def test_drm_listed_as_broken(self):
        path = os.path.join(self.tmp, "drm.epub")
        make_epub(path, [("META-INF/container.xml", CONTAINER), ("OPS/p.opf", opf()),
                         ("META-INF/encryption.xml",
                          '<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
                          'xmlns:enc="http://www.w3.org/2001/04/xmlenc#"><enc:EncryptedData>'
                          '<enc:EncryptionMethod Algorithm="aes"/></enc:EncryptedData></encryption>')])
        info = book_info(path)
        self.assertEqual((info["title"], info["broken"]), ("A Book", True))

    def test_smil_without_overlay_is_no_readaloud(self):
        path = os.path.join(self.tmp, "b.epub")
        write_book(path, audio=True)
        self.assertFalse(book_info(path)["audio"])

    def test_oversized_package_document(self):
        path = os.path.join(self.tmp, "big.epub")
        write_book(path, opf(extra="<!--" + "x" * (10 * 1024 * 1024) + "-->"))
        with self.assertRaises(EpubError) as cm:
            book_info(path)
        self.assertEqual(cm.exception.code, "too_large")


    def test_huge_central_directory_refused_before_reading(self):
        # zipfile would build an object per entry first (1 million: 550 MB).
        path = os.path.join(self.tmp, "b.epub")
        write_book(path)
        with mock.patch.object(archive, "MAX_DIRECTORY", 100), \
                mock.patch("zipfile.ZipFile", side_effect=AssertionError("read")):
            with self.assertRaises(EpubError) as cm:
                book_info(path)
        self.assertEqual(cm.exception.code, "too_many_files")


class ScanTest(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.books = os.path.join(self.tmp, "books")
        self.cache = os.path.join(self.tmp, "cache", "library.json")
        os.makedirs(self.books)

    def book(self, name, **kwargs):
        path = os.path.join(self.books, name)
        write_book(path, **kwargs)
        return path

    def test_reads_only_new_and_changed_books(self):
        a = self.book("a.epub")
        b = self.book("b.epub", package=opf(title="B"))
        entries, changed = scan([self.books], self.cache)
        self.assertEqual([e["info"]["title"] for e in entries], ["A Book", "B"])
        self.assertTrue(changed)
        self.assertEqual(scan([self.books], self.cache), (entries, False))
        write_book(b, package=opf(title="B2"))
        os.utime(b, ns=(1, 1))
        os.remove(a)
        with mock.patch("bookfish.library.book_info", wraps=library.book_info) as read:
            entries, changed = scan([self.books], self.cache)
        self.assertEqual([e["info"]["title"] for e in entries], ["B2"])
        self.assertTrue(changed)
        self.assertEqual(read.call_count, 1)
        self.assertEqual(load_cached(self.cache), entries)

    def test_other_and_missing_folders_stay_cached(self):
        other = os.path.join(self.tmp, "card")
        os.makedirs(other)
        write_book(os.path.join(other, "c.epub"))
        self.book("a.epub")
        scan([self.books, other], self.cache)
        scan([self.books], self.cache)  # one folder chosen
        os.rename(other, other + "-out")  # card taken out
        entries, changed = scan([self.books, other], self.cache)
        self.assertEqual(len(entries), 1)
        self.assertFalse(changed)
        self.assertEqual(len(load_cached(self.cache)), 2)

    def test_read_again_after_a_passing_error(self):
        path = self.book("a.epub")
        with mock.patch("bookfish.library.book_info", side_effect=OSError("card gone")):
            entry = scan([self.books], self.cache)[0][0]
        self.assertTrue(entry["info"]["broken"])
        entry = scan([self.books], self.cache)[0][0]
        self.assertFalse(entry["info"]["broken"])
        with mock.patch("bookfish.library.book_info", side_effect=EpubError("bad_xml")):
            os.utime(path, ns=(2, 2))
            scan([self.books], self.cache)
        self.assertTrue(scan([self.books], self.cache)[0][0]["info"]["broken"])

    def test_fifo_and_folder_are_not_opened(self):
        os.mkfifo(os.path.join(self.books, "pipe.epub"))  # would hang if opened
        os.mkdir(os.path.join(self.books, "folder.epub"))
        self.assertEqual(scan([self.books], self.cache)[0], [])
        with self.assertRaises(EpubError):
            book_info(os.path.join(self.books, "pipe.epub"))

    def test_broken_book_listed_by_file_name(self):
        write_files(self.books, {"Broken Book.epub": b"no zip"})
        info = scan([self.books], self.cache)[0][0]["info"]
        self.assertEqual((info["title"], info["broken"]), ("Broken Book", True))

    def test_damaged_cache_is_ignored(self):
        self.book("a.epub")
        for content in ("{", "[]", '{"version": 4, "books": [{"path": 5}]}',
                        '{"version": 99, "books": []}', "[" * 100000 + "]" * 100000):
            write_files(os.path.dirname(self.cache), {"library.json": content})
            self.assertEqual(load_cached(self.cache), [])
            self.assertEqual(len(scan([self.books], self.cache)[0]), 1)

    def test_entry_with_wrong_types_is_dropped(self):
        self.book("a.epub")
        entry = scan([self.books], self.cache)[0][0]
        for field, value in (("authors", [1]), ("index", float("nan")), ("index", True)):
            bad = dict(entry, info=dict(entry["info"], **{field: value}))
            write_files(os.path.dirname(self.cache), {"library.json": json.dumps(
                {"version": 4, "books": [bad]})})
            self.assertEqual(load_cached(self.cache), [], field)


class ReplacedTest(unittest.TestCase):

    def entry(self, identifier, title, audio):
        info = dict(broken_info("x"), identifier=identifier, title=title, audio=audio, broken=False)
        return {"path": title + str(audio), "stamp": [0, 0], "info": info}

    def test_readaloud_replaces_its_epub(self):
        epub = self.entry("urn:uuid:ABC", "Patriot Games", False)
        readaloud = self.entry("uuid:abc", "Patriot Games", True)
        other_title = self.entry("urn:uuid:abc", "Red Rabbit", False)
        other_id = self.entry("urn:uuid:xyz", "Patriot Games", False)
        no_id = self.entry("", "Patriot Games", False)
        self.assertEqual(without_replaced([epub, readaloud, other_title, other_id, no_id]),
                         [readaloud, other_title, other_id, no_id])

    def test_normal_identifier(self):
        for identifier in ("urn:uuid:abc", "uuid:ABC", " abc ", "url:abc"):
            self.assertEqual(normal_identifier(identifier), "abc")
        self.assertEqual(normal_identifier("urn:asin:B006"), "b006")
        for identifier in ("ISBN:978", "urn:isbn:978", "978"):
            self.assertEqual(normal_identifier(identifier), "978")


class CoverTest(TempDirTestCase):

    def test_extract_and_prune(self):
        path = os.path.join(self.tmp, "b.epub")
        write_book(path)
        covers = os.path.join(self.tmp, "covers")
        os.makedirs(covers)
        target = os.path.join(covers, "0123456789abcdef.png")
        self.assertTrue(extract_cover(path, "OPS/cover.png", target))
        with open(target, "rb") as f:
            self.assertEqual(f.read(), b"PNG")
        self.assertFalse(extract_cover(path, "OPS/missing.png", target + "x"))
        write_files(covers, {"fedcba9876543210.jpg": "", "other.txt": ""})
        prune_covers(covers, {"0123456789abcdef"})
        self.assertEqual(sorted(os.listdir(covers)), ["0123456789abcdef.png", "other.txt"])

    def test_huge_png_refused(self):
        path = os.path.join(self.tmp, "b.epub")
        header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        write_book(path, cover=header + struct.pack(">II", 20000, 100) + b"rest")
        self.assertFalse(extract_cover(path, "OPS/cover.png", os.path.join(self.tmp, "c.png")))
        write_book(path, cover=header + struct.pack(">II", 1000, 1500) + b"rest")
        self.assertTrue(extract_cover(path, "OPS/cover.png", os.path.join(self.tmp, "c.png")))

    def test_oversized_cover(self):
        path = os.path.join(self.tmp, "b.epub")
        write_book(path, cover=b"x" * (5 * 1024 * 1024 + 1))
        self.assertFalse(extract_cover(path, "OPS/cover.png", os.path.join(self.tmp, "c.png")))


class AudiobookTest(TempDirTestCase):
    """Audiobooks in the library: which files make a book, and their entries."""

    def path(self, name):
        return os.path.join(self.tmp, *name.split("/"))

    def write(self, files):
        write_files(self.tmp, files)

    def test_folder_without_epub_is_one_book_in_natural_order(self):
        tune = ad.mp3([ad.text("TIT2", "x")])
        self.write({"Kling/Book/Book-10.mp3": tune, "Kling/Book/Book-2.mp3": tune,
                    "Kling/Book/cover.jpg": ad.JPEG, "Kling/Book/.hidden.mp3": tune})
        self.assertEqual(list_books([self.tmp]), [
            BookFile(self.path("Kling/Book"), "Book", "audiobook",
                     (self.path("Kling/Book/Book-2.mp3"), self.path("Kling/Book/Book-10.mp3")))])

    def test_mp3s_beside_epubs_are_books_of_their_own(self):
        tune = ad.mp3([ad.text("TIT2", "x")])
        self.write({"Follett/a.mp3": tune, "Follett/b.mp3": tune, "Follett/a.epub": "",
                    "Follett/c.M4B": ad.m4b()})
        self.assertEqual(list_books([self.tmp]), [
            BookFile(self.path("Follett/a.epub"), "a"),
            BookFile(self.path("Follett/a.mp3"), "a", "audiobook", (self.path("Follett/a.mp3"),)),
            BookFile(self.path("Follett/b.mp3"), "b", "audiobook", (self.path("Follett/b.mp3"),)),
            BookFile(self.path("Follett/c.M4B"), "c", "audiobook", (self.path("Follett/c.M4B"),))])

    def test_mp3s_in_the_library_folder_itself_are_books(self):
        tune = ad.mp3([ad.text("TIT2", "x")])
        self.write({"one.mp3": tune, "two.mp3": tune})
        self.assertEqual([(b.path, b.kind) for b in list_books([self.tmp])],
                         [(self.path("one.mp3"), "audiobook"), (self.path("two.mp3"), "audiobook")])
        # Found again from the cache: nothing changed, nothing added.
        cache = os.path.join(self.tmp, "library.json")
        scan([self.tmp], cache)
        self.assertEqual(scan([self.tmp], cache)[1], False)
        self.assertEqual(len(load_cached(cache)), 2)

    def test_m4b_files_are_books_also_without_epubs(self):
        self.write({"x/one.m4b": ad.m4b(), "x/two.m4b": ad.m4b()})
        self.assertEqual([b.name for b in list_books([self.tmp])], ["one", "two"])

    def test_info_of_a_single_file(self):
        self.write({"a.mp3": ad.mp3([ad.text("TIT2", "Jackdaws"), ad.text("TALB", "Jackdaws (Unabridged)"),
                                     ad.text("TPE1", "Ken Follett"), ad.apic(ad.JPEG)]),
                    "b.epub": ""})
        book = [b for b in list_books([self.tmp]) if b.kind == "audiobook"][0]
        self.assertEqual(library.audio_info(book), {
            "identifier": "", "title": "Jackdaws", "authors": ["Ken Follett"], "sort": "",
            "series": "", "index": None, "cover": "embedded.jpg", "audio": False,
            "broken": False, "kind": "audiobook"})

    def test_series_of_an_audiobook(self):
        tags = [ad.txxx("SERIES", "Die Känguru-Werke"), ad.txxx("SERIES-PART", "4")]
        for album, title in (("Die Känguru-Werke 4 – Die Känguru-Apokryphen", "Die Känguru-Apokryphen"),
                             ("die känguru-werke 04: Apokryphen", "Apokryphen"),
                             ("Die Känguru-Werke 4 - X", "X"),
                             ("Die Känguru-Werke 40 – X", "Die Känguru-Werke 40 – X"),
                             ("Die Känguru-Werke 3 – X", "Die Känguru-Werke 3 – X"),
                             ("Das Känguru 4 – X", "Das Känguru 4 – X"),
                             ("Die Känguru-Werke 4 – ", "Die Känguru-Werke 4 –"),
                             ("Apokryphen", "Apokryphen")):
            self.write({"f/01.mp3": ad.mp3([ad.text("TALB", album)] + tags), "f/02.mp3": ad.mp3([])})
            info = library.audio_info(list_books([self.tmp])[0])
            self.assertEqual((info["title"], info["series"], info["index"]),
                             (title, "Die Känguru-Werke", 4.0), album)
        self.write({"f/01.mp3": ad.mp3([ad.text("TALB", "S 1.5 – X"), ad.txxx("SERIES", "S"),
                                        ad.txxx("SERIES-PART", "1.5")])})
        self.assertEqual(library.audio_info(list_books([self.tmp])[0])["title"], "X")
        for part, album, title in (("123456.5", "S 123456 – X", "S 123456 – X"),
                                   ("1234.567", "S 1234,567 — X", "X"),
                                   ("4", "S 4.0 – X", "S 4.0 – X")):
            self.write({"f/01.mp3": ad.mp3([ad.text("TALB", album), ad.txxx("SERIES", "S"),
                                            ad.txxx("SERIES-PART", part)])})
            self.assertEqual(library.audio_info(list_books([self.tmp])[0])["title"], title, part)
        self.write({"f/01.mp3": ad.mp3([ad.text("TALB", "S.* 2: X"), ad.txxx("SERIES", "S.*"),
                                        ad.txxx("SERIES-PART", "2")])})
        self.assertEqual(library.audio_info(list_books([self.tmp])[0])["title"], "X")
        self.write({"f/01.mp3": ad.mp3([ad.text("TALB", "Sx 2: X"), ad.txxx("SERIES", "S.")])})
        self.assertEqual(library.audio_info(list_books([self.tmp])[0])["title"], "Sx 2: X")
        self.write({"f/01.mp3": ad.mp3([ad.text("TALB", "S 1 – X"), ad.txxx("SERIES", "S")])})
        info = library.audio_info(list_books([self.tmp])[0])
        self.assertEqual((info["title"], info["series"], info["index"]), ("S 1 – X", "S", None))

    def test_info_of_a_folder(self):
        first = ad.mp3([ad.text("TIT2", "Chapter 1"), ad.text("TALB", "The Book"),
                        ad.text("TPE1", "Reader"), ad.text("TPE2", "Writer, Wanda"), ad.apic(ad.PNG)])
        self.write({"f/01.mp3": first, "f/02.mp3": ad.mp3([]), "f/Cover.PNG": ad.PNG})
        info = library.audio_info(list_books([self.tmp])[0])
        self.assertEqual((info["title"], info["authors"], info["cover"]),
                         ("The Book", ["Writer, Wanda"], "Cover.PNG"))
        os.remove(self.path("f/Cover.PNG"))
        self.write({"f/01.mp3": ad.mp3([ad.text("TPE1", "Reader")])})
        info = library.audio_info(list_books([self.tmp])[0])
        self.assertEqual((info["title"], info["authors"], info["cover"]), ("f", ["Reader"], None))

    def test_scan_reads_folders_again_when_a_file_changes(self):
        books = self.path("books")
        self.write({"books/f/1.mp3": ad.mp3([ad.text("TALB", "Old")]), "books/f/2.mp3": ad.mp3([])})
        cache = self.path("library.json")
        entries, changed = scan([books], cache)
        self.assertEqual((entries[0]["info"]["title"], changed), ("Old", True))
        self.assertEqual(scan([books], cache)[1], False)
        self.write({"books/f/1.mp3": ad.mp3([ad.text("TALB", "New title")])})
        entries, changed = scan([books], cache)
        self.assertEqual((entries[0]["info"]["title"], changed), ("New title", True))
        # A file renamed, added, removed, at once after the last scan.
        for change in (lambda: os.rename(self.path("books/f/2.mp3"), self.path("books/f/3.mp3")),
                       lambda: self.write({"books/f/4.mp3": b""}),
                       lambda: os.remove(self.path("books/f/4.mp3"))):
            scan([books], cache)
            change()
            self.assertEqual(scan([books], cache)[1], True)

    def test_broken_audiobook_listed_by_name(self):
        self.write({"books/Dr.-Devil/1.mp3": b"no audio here", "books/x.m4b": b"nothing"})
        entries, _ = scan([self.path("books")], self.path("library.json"))
        self.assertEqual([(e["info"]["title"], e["info"]["broken"], e["info"]["kind"]) for e in entries],
                         [("Dr.-Devil", True, "audiobook"), ("x", True, "audiobook")])

    def test_audio_cover_from_tags_or_folder(self):
        self.write({"a.mp3": ad.mp3([ad.apic(ad.JPEG)]), "f/1.mp3": ad.mp3([ad.apic(ad.PNG)]),
                    "f/cover.png": ad.PNG, "g/1.mp3": ad.mp3([]), "g/cover.jpg": ad.PNG,
                    "m.m4b": ad.m4b(items=[ad.item(b"covr", ad.JPEG, 13)])})
        target = self.path("cover.out")
        for path, cover, expected in (("a.mp3", "embedded.jpg", ad.JPEG),
                                      ("f", "embedded.png", ad.PNG), ("f", "cover.png", ad.PNG),
                                      ("m.m4b", "embedded.jpg", ad.JPEG)):
            self.assertTrue(library.extract_audio_cover(self.path(path), cover, target), path)
            with open(target, "rb") as f:
                self.assertEqual(f.read(), expected)
        # A PNG named .jpg, a name that is no cover, a path out of the folder.
        for path, cover in (("g", "cover.jpg"), ("a.mp3", "embedded.png"), ("f", "1.mp3"),
                            ("f", "../a.mp3"), ("g", "embedded.jpg")):
            self.assertFalse(library.extract_audio_cover(self.path(path), cover, target), cover)


def audio_entry(path, title="T", authors=(), kind="audiobook", **info):
    entry = {"path": path, "stamp": [1, 2], "info": {
        "identifier": "", "title": title, "authors": list(authors), "sort": "", "series": "",
        "index": None, "cover": None, "audio": False, "broken": False, "kind": kind}}
    entry["info"].update(info)
    return entry


class AlbumsTest(TempDirTestCase):
    """A folder of MP3 files without EPUBs holding several albums."""

    def path(self, name):
        return os.path.join(self.tmp, *name.split("/"))

    def write(self, albums, folder="Lib/Books"):
        """albums: {file name: album or None}."""
        write_files(self.tmp, {folder + "/" + name: ad.mp3(
            [ad.text("TIT2", name)] + ([ad.text("TALB", album)] if album is not None else []))
            for name, album in albums.items()})

    def books(self):
        cache = os.path.join(self.tmp, "library.json")
        return list_books([self.path("Lib")], library._Albums(library._load_store(cache)["albums"]))

    def test_one_album_and_files_without_one_are_one_book(self):
        self.write({"01.mp3": "Kopf schlägt Kapital", "02.mp3": " kopf  Schlägt kapital",
                    "03.mp3": None, "04.mp3": ""})
        self.assertEqual(self.books(), [BookFile(self.path("Lib/Books"), "Books", "audiobook", tuple(
            self.path("Lib/Books/0%d.mp3" % n) for n in (1, 2, 3, 4)))])

    def test_each_album_a_book(self):
        self.write({"a1.mp3": "Hobbit", "a2.mp3": "hobbit", "a3.mp3": "Hobbit", "b.mp3": "Emil",
                    "c1.mp3": "AC/DC Live", "c2.mp3": "AC DC  Live", "d.mp3": None,
                    "cover.jpg": None})
        folder = self.path("Lib/Books")
        self.assertEqual(self.books(), [
            BookFile(library.album_path(folder, "ac dc live"), "AC/DC Live", "audiobook",
                     (self.path("Lib/Books/c1.mp3"), self.path("Lib/Books/c2.mp3")), "AC/DC Live"),
            BookFile(self.path("Lib/Books/b.mp3"), "b", "audiobook", (self.path("Lib/Books/b.mp3"),),
                     "Emil"),
            BookFile(self.path("Lib/Books/d.mp3"), "d", "audiobook", (self.path("Lib/Books/d.mp3"),)),
            BookFile(library.album_path(folder, "hobbit"), "Hobbit", "audiobook",
                     tuple(self.path("Lib/Books/a%d.mp3" % n) for n in (1, 2, 3)), "Hobbit")])

    def test_entries_of_albums(self):
        write_files(self.tmp, {
            "Lib/Books/a1.mp3": ad.mp3([ad.text("TALB", "Hobbit"), ad.text("TIT2", "Chapter 1"),
                                        ad.text("TPE1", "Tolkien"), ad.apic(ad.JPEG)]),
            "Lib/Books/a2.mp3": ad.mp3([ad.text("TALB", "Hobbit")]),
            "Lib/Books/b.mp3": ad.mp3([ad.text("TALB", "Emil"), ad.text("TIT2", "Kapitel 1")]),
            "Lib/Books/cover.jpg": ad.JPEG})
        cache = os.path.join(self.tmp, "library.json")
        entries, _ = scan([self.path("Lib")], cache)
        infos = {e["path"]: e["info"] for e in entries}
        hobbit = infos[library.album_path(self.path("Lib/Books"), "hobbit")]
        # The picture beside the files belongs to no album.
        self.assertEqual((hobbit["title"], hobbit["authors"], hobbit["cover"]),
                         ("Hobbit", ["Tolkien"], "embedded.jpg"))
        self.assertEqual(infos[self.path("Lib/Books/b.mp3")]["title"], "Emil")
        target = os.path.join(self.tmp, "cover.jpg")
        self.assertTrue(library.extract_audio_cover(
            library.album_path(self.path("Lib/Books"), "hobbit"), "embedded.jpg", target))

    def test_album_tags_read_once(self):
        self.write({"a.mp3": "A", "b.mp3": "B"})
        cache = os.path.join(self.tmp, "library.json")
        first, _ = scan([self.path("Lib")], cache)
        with mock.patch.object(library.mp3, "album", side_effect=AssertionError("read again")):
            entries, changed = scan([self.path("Lib")], cache)
        self.assertEqual((sorted(e["path"] for e in entries), changed),
                         (sorted(e["path"] for e in first), False))
        # A file changed: read again, and the folder is one book now.
        self.write({"b.mp3": "a"})
        entries, changed = scan([self.path("Lib")], cache)
        self.assertEqual(([e["path"] for e in entries], changed), ([self.path("Lib/Books")], True))
        # Of a folder of one album only that is kept.
        self.assertEqual(library._load_store(cache)["albums"][self.path("Lib/Books")][2], [])

    def test_title_follows_an_epub_put_beside(self):
        write_files(self.tmp, {"Lib/Books/a.mp3": ad.mp3([ad.text("TALB", "Alpha Album"),
                                                          ad.text("TIT2", "A")]),
                               "Lib/Books/b.mp3": ad.mp3([ad.text("TALB", "Beta")])})
        cache = os.path.join(self.tmp, "library.json")
        titles = lambda: {os.path.basename(e["path"]): e["info"]["title"]
                          for e in scan([self.path("Lib")], cache)[0]}
        self.assertEqual(titles()["a.mp3"], "Alpha Album")
        make_epub(self.path("Lib/Books/x.epub"), mini_entries())
        self.assertEqual(titles()["a.mp3"], "A")

    def test_library_folder_with_slashes_and_unicode_forms(self):
        import unicodedata
        self.write({"a.mp3": unicodedata.normalize("NFD", "Höhle"), "b.mp3": "Höhle"})
        self.assertEqual([b.path for b in list_books([self.path("Lib") + "//"], library._Albums({}))],
                         [self.path("Lib/Books")])

    def test_unreadable_tags_leave_the_folder_whole(self):
        self.write({"a.mp3": "A", "b.mp3": "B"})
        with mock.patch.object(library.mp3, "album", side_effect=OSError("hangs")):
            self.assertEqual([b.path for b in self.books()], [self.path("Lib/Books")])
        # A broken file is a book of its own; it tells what is wrong.
        with open(self.path("Lib/Books/c.mp3"), "wb") as f:
            f.write(b"junk")
        self.assertEqual([b.path for b in self.books()], [self.path("Lib/Books/" + name)
                                                          for name in ("a.mp3", "b.mp3", "c.mp3")])

    def test_library_folder_itself_and_folders_beside_epubs_not_split(self):
        self.write({"a.mp3": "A", "b.mp3": "B"}, folder="Lib")
        self.write({"c.mp3": "C", "d.mp3": "D", "e.epub": None}, folder="Lib/Author")
        self.assertEqual([b.album for b in self.books()], ["", "", "", "", ""])

    def test_album_files_and_paths(self):
        self.write({"a1.mp3": "Hobbit", "a2.mp3": "HOBBIT", "b.mp3": "Emil"})
        folder = self.path("Lib/Books")
        path = library.album_path(folder, "hobbit")
        self.assertEqual(library.split_album(path), (folder, "hobbit"))
        self.assertEqual(library.split_album(folder), (folder, None))
        self.assertEqual(library.split_album("/a//b/c.mp3"), ("/a//b/c.mp3", None))
        self.assertEqual(library.album_files(path), [self.path("Lib/Books/a1.mp3"),
                                                     self.path("Lib/Books/a2.mp3")])
        self.assertTrue(library.exists(path))
        self.assertFalse(library.exists(library.album_path(self.path("Lib/Gone"), "hobbit")))

    def test_arranged_without_partner_or_neighbours(self):
        self.write({"Books.mp3": None, "x.epub": None}, folder="Lib")
        self.write({"a.mp3": "A", "b.mp3": "B", "b2.mp3": "B"})
        entries, _ = scan([self.path("Lib")], os.path.join(self.tmp, "library.json"))
        album = library.album_path(self.path("Lib/Books"), "b")
        shown = {e["path"]: partner for e, _, partner in library.arranged(entries)}
        self.assertIsNone(shown[album])


class ArrangedTest(unittest.TestCase):

    def test_paired_audiobook_shows_its_epub(self):
        epub = audio_entry("/l/A/x.epub", "Real Title", ["Ann, A"], kind="epub",
                           identifier="id", series="S", index=2.0, sort="Ann, A")
        audio = audio_entry("/l/A/x.mp3", "x (Unabridged)", ["A Ann"])
        folder = audio_entry("/l/A/x", "Folder", ["Narrator"])
        result = library.arranged([epub, audio, folder])
        self.assertEqual([(e["path"], i["title"], i["authors"], i["series"], p and p["path"])
                          for e, i, p in result],
                         [("/l/A/x.epub", "Real Title", ["Ann, A"], "S", None),
                          ("/l/A/x.mp3", "Real Title", ["Ann, A"], "S", "/l/A/x.epub"),
                          ("/l/A/x", "Real Title", ["Ann, A"], "S", "/l/A/x.epub")])

    def test_series_of_the_epub_wins(self):
        epub = audio_entry("/l/A/x.epub", kind="epub", identifier="id")
        audio = audio_entry("/l/A/x.mp3", series="Tag", index=4.0)
        other = audio_entry("/l/A/y.mp3", series="Tag", index=5.0)
        self.assertEqual([(i["series"], i["index"]) for _, i, _ in library.arranged([epub, audio, other])],
                         [("", None), ("", None), ("Tag", 5.0)])

    def test_readaloud_hides_epub_and_its_audiobook(self):
        epub = audio_entry("/l/x.epub", "T", kind="epub", identifier="urn:uuid:1")
        readaloud = audio_entry("/l/x-readaloud.epub", "T", kind="epub", identifier="uuid:1",
                                audio=True)
        audio = audio_entry("/l/x.m4b")
        self.assertEqual([e["path"] for e, _, _ in library.arranged([epub, readaloud, audio])],
                         ["/l/x-readaloud.epub"])

    def test_readaloud_with_isbn_prefix_hides_epub_and_its_audiobook(self):
        # Storyteller writes an identifier with opf:scheme="ISBN" with a prefix.
        epub = audio_entry("/l/x.epub", "T", kind="epub", identifier="978")
        readaloud = audio_entry("/l/x-readaloud.epub", "T", kind="epub", identifier="ISBN:978",
                                audio=True)
        for audio in (audio_entry("/l/x.m4b"), audio_entry("/l/x")):
            self.assertEqual([e["path"] for e, _, _ in library.arranged([epub, readaloud, audio])],
                             ["/l/x-readaloud.epub"])

    def test_unpaired_audiobook_takes_the_author_beside_it(self):
        epubs = [audio_entry("/l/Keller/a.epub", kind="epub", authors=["Keller, Timothy"],
                             sort="Keller, Timothy"),
                 audio_entry("/l/Keller/b.epub", kind="epub", authors=["Keller, Timothy", "X"])]
        lone = audio_entry("/l/Keller/talk.mp3", authors=["Timothy J. Keller"])
        folder = audio_entry("/l/Keller/sermons", authors=["Narrator"])
        mixed = [audio_entry("/l/Mixed/a.epub", kind="epub", authors=["One"]),
                 audio_entry("/l/Mixed/b.epub", kind="epub", authors=["Two"]),
                 audio_entry("/l/Mixed/c.mp3", authors=["Tag"])]
        alone = audio_entry("/l/Kids/episode", authors=["Kids"])
        shown = {e["path"]: (i["authors"], i["sort"])
                 for e, i, _ in library.arranged(epubs + [lone, folder, alone] + mixed)}
        self.assertEqual(shown["/l/Keller/talk.mp3"], (["Keller, Timothy"], "Keller, Timothy"))
        self.assertEqual(shown["/l/Keller/sermons"], (["Keller, Timothy"], "Keller, Timothy"))
        self.assertEqual(shown["/l/Mixed/c.mp3"], (["Tag"], ""))
        self.assertEqual(shown["/l/Kids/episode"], (["Kids"], ""))

    def test_no_author_from_beside_in_a_library_folder(self):
        entries = [audio_entry("/docs/prayer.epub", kind="epub", authors=["Keller, Timothy"]),
                   audio_entry("/docs/potter.m4b", authors=["Rowling"]),
                   audio_entry("/docs/sub/talk.mp3", authors=["Tag"]),
                   audio_entry("/docs/sub/a.epub", kind="epub", authors=["Sub"])]
        shown = {e["path"]: i["authors"] for e, i, _ in library.arranged(entries, ["/docs/"])}
        self.assertEqual((shown["/docs/potter.m4b"], shown["/docs/sub/talk.mp3"]),
                         (["Rowling"], ["Sub"]))
