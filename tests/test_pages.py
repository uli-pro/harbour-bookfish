import unittest

from bookfish.package import read_ncx_pages, read_nav_pages
from bookfish.pages import RUN, PageFinder, PageTarget, chars_per_page, page_numbers, parse_name

from .helpers import TempDirTestCase, write_files
from .test_package import CHAPTER, PackageTest

NAV_PAGES = """<?xml version="1.0"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<body>
  <nav epub:type="toc"><ol><li><a href="c1.xhtml">Chapter 1</a></li></ol></nav>
  <nav epub:type="page-list" hidden="">
    <ol>
      <li><a href="c1.xhtml#pg-iii">iii</a></li>
      <li><a href="c1.xhtml#pg1"> <span>1</span> </a></li>
      <li><a href="c1.xhtml#pg2">2</a></li>
      <li><a>no link</a></li>
      <li><a href="../../outside.xhtml#pg3">3</a></li>
      <li><a href="http://example.com/#pg4">4</a></li>
    </ol>
  </nav>
</body>
</html>"""

NCX_PAGES = """<?xml version="1.0"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <navMap>
    <navPoint id="p1"><navLabel><text>Chapter 1</text></navLabel><content src="c1.xhtml"/></navPoint>
  </navMap>
  <pageList>
    <pageTarget type="normal" value="1"><navLabel><text>1</text></navLabel><content src="c1.xhtml"/></pageTarget>
    <pageTarget type="normal" value="2"><navLabel><text>p2</text></navLabel><content src="c1.xhtml#page_2"/></pageTarget>
    <pageTarget><navLabel><text>3</text></navLabel></pageTarget>
  </pageList>
</ncx>"""


def targets(*entries):
    """PageTarget for each (path, fragment, name)."""
    return [PageTarget(*entry) for entry in entries]


def numbered(path, first, last):
    return [PageTarget(path, "pg%d" % n, str(n)) for n in range(first, last + 1)]


class ParseNameTest(unittest.TestCase):

    def test_numbers(self):
        self.assertEqual(parse_name("143"), ("143", 143))
        self.assertEqual(parse_name(" 7 "), ("7", 7))
        self.assertEqual(parse_name("007"), ("7", 7))

    def test_number_with_letters(self):
        self.assertEqual(parse_name("p78"), ("78", 78))
        self.assertEqual(parse_name("Page 12"), ("12", 12))

    def test_volume_and_page(self):
        self.assertEqual(parse_name("v2-5"), ("5", 5))

    def test_roman(self):
        self.assertEqual(parse_name("vii"), ("vii", None))
        self.assertEqual(parse_name("XIV"), ("XIV", None))

    def test_no_page(self):
        self.assertIsNone(parse_name("Cover"))
        self.assertIsNone(parse_name(""))
        self.assertIsNone(parse_name("1234567"))


class PageNumbersTest(unittest.TestCase):

    def test_marks_by_chapter(self):
        pages = page_numbers(["a.xhtml", "b.xhtml"], targets(
            ("a.xhtml", "pg-i", "i"), ("a.xhtml", "pg1", "1"), ("b.xhtml", "", "2"),
            ("b.xhtml", "pg3", "3")))
        self.assertEqual(pages, {
            "total": 3,
            "marks": [[["pg-i", "i", False], ["pg1", "1", True]],
                      [["", "2", True], ["pg3", "3", True]]],
            "start": [None, ["1", True]],
        })

    def test_start_carries_over_chapters_without_marks(self):
        pages = page_numbers(["a", "b", "c", "d"], targets(("b", "x", "vii"), ("b", "y", "viii")))
        self.assertEqual(pages["start"], [None, None, ["viii", False], ["viii", False]])
        self.assertEqual(pages["total"], 0)

    def test_names_without_number_are_no_page(self):
        pages = page_numbers(["a"], targets(("a", "c", "Cover"), ("a", "p1", "1")))
        self.assertEqual(pages["marks"], [[["p1", "1", True]]])

    def test_entries_outside_the_spine_are_left_out(self):
        pages = page_numbers(["a"], targets(("a", "p1", "1"), ("notes", "p9", "9")))
        self.assertEqual(pages["marks"], [[["p1", "1", True]]])
        self.assertEqual(pages["total"], 1)

    def test_chapter_twice_in_spine_gets_marks_once(self):
        pages = page_numbers(["a", "a"], targets(("a", "p1", "1")))
        self.assertEqual(pages["marks"], [[["p1", "1", True]], []])

    def test_list_without_ids_is_estimated(self):
        # Made by calibre: every page of a chapter at its start.
        self.assertIsNone(page_numbers(["a", "b"], targets(
            ("a", "", "1"), ("a", "", "2"), ("b", "p3", "3"), ("b", "", "4"))))
        self.assertIsNotNone(page_numbers(["a", "b"], targets(
            ("a", "", "1"), ("a", "p2", "2"), ("b", "p3", "3"))))

    def test_nothing_usable_is_estimated(self):
        self.assertIsNone(page_numbers(["a"], []))
        self.assertIsNone(page_numbers(["a"], targets(("a", "c", "Cover"), ("a", "d", "Contents"))))
        self.assertIsNone(page_numbers(["a"], targets(("other", "p1", "1"), ("other", "p2", "2"))))

    def test_total_is_the_highest_number(self):
        pages = page_numbers(["a"], numbered("a", 1, 5) + targets(("a", "x", "xii")))
        self.assertEqual(pages["total"], 5)

    def test_numbering_anew_has_no_total(self):
        volumes = numbered("a", 1, RUN) + numbered("b", 1, RUN)
        self.assertEqual(page_numbers(["a", "b"], volumes)["total"], 0)

    def test_page_moved_to_the_front_is_left_out(self):
        # A copyright page printed at the back, moved to the front: the
        # front matter must not show the last page.
        pages = page_numbers(["a", "b"], targets(("a", "c", "338")) + numbered("b", 1, 337))
        self.assertEqual(pages["marks"][0], [])
        self.assertEqual(pages["start"][1], None)
        self.assertEqual(pages["total"], 337)

    def test_long_first_run_is_kept(self):
        pages = page_numbers(["a", "b"], numbered("a", 1, RUN) + numbered("b", 1, 3))
        self.assertEqual(len(pages["marks"][0]), RUN)
        self.assertEqual(pages["total"], RUN)

    def test_roman_pages_before_a_moved_page_stay(self):
        pages = page_numbers(["a", "b"], targets(("a", "x", "xi"), ("a", "c", "5")) + numbered("b", 1, 20))
        self.assertEqual(pages["marks"][0], [["x", "xi", False]])

    def test_page_out_of_order_later_keeps_the_total(self):
        pages = page_numbers(["a"], numbered("a", 1, 3) + numbered("a", 5, 338) + numbered("a", 4, 4))
        self.assertEqual(pages["total"], 338)
        self.assertEqual(pages["marks"][0][-1], ["pg4", "4", True])

    def test_short_appendix_counted_anew_keeps_the_total(self):
        pages = page_numbers(["a", "b"], numbered("a", 1, 29) + numbered("b", 1, 4))
        self.assertEqual(pages["total"], 29)


class ReadPagesTest(TempDirTestCase):

    book = PackageTest.book

    def test_nav(self):
        write_files(self.tmp, {"OPS/nav.xhtml": NAV_PAGES})
        self.assertEqual(read_nav_pages(self.tmp, "OPS/nav.xhtml"), [
            PageTarget("OPS/c1.xhtml", "pg-iii", "iii"),
            PageTarget("OPS/c1.xhtml", "pg1", "1"),
            PageTarget("OPS/c1.xhtml", "pg2", "2"),
        ])

    def test_nav_without_page_list(self):
        write_files(self.tmp, {"OPS/nav.xhtml": NAV_PAGES.replace("page-list", "landmarks")})
        self.assertEqual(read_nav_pages(self.tmp, "OPS/nav.xhtml"), [])

    def test_ncx(self):
        write_files(self.tmp, {"OPS/toc.ncx": NCX_PAGES})
        self.assertEqual(read_ncx_pages(self.tmp, "OPS/toc.ncx"), [
            PageTarget("OPS/c1.xhtml", "", "1"),
            PageTarget("OPS/c1.xhtml", "page_2", "p2"),
        ])

    def test_ncx_without_page_list(self):
        write_files(self.tmp, {"OPS/toc.ncx": NCX_PAGES.split("<pageList>")[0] + "</ncx>"})
        self.assertEqual(read_ncx_pages(self.tmp, "OPS/toc.ncx"), [])

    def test_package_without_page_list(self):
        self.assertEqual(self.book().pages, [])

    def test_package_reads_nav(self):
        book = self.book(
            manifest=CHAPTER + '<item id="nav" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/>',
            files={"OPS/nav.xhtml": NAV_PAGES})
        self.assertEqual([t.name for t in book.pages], ["iii", "1", "2"])

    def test_package_reads_ncx_if_nav_has_none(self):
        book = self.book(
            manifest=CHAPTER + '<item id="nav" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/>'
                     '<item id="n" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
            files={"OPS/nav.xhtml": NAV_PAGES.replace("page-list", "landmarks"),
                   "OPS/toc.ncx": NCX_PAGES})
        self.assertEqual([t.name for t in book.pages], ["1", "p2"])

    def test_nav_wins_over_ncx(self):
        book = self.book(
            manifest=CHAPTER + '<item id="nav" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/>'
                     '<item id="n" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
            files={"OPS/nav.xhtml": NAV_PAGES, "OPS/toc.ncx": NCX_PAGES})
        self.assertEqual([t.name for t in book.pages], ["iii", "1", "2"])

    def test_broken_page_list_gives_no_pages(self):
        book = self.book(
            manifest=CHAPTER + '<item id="n" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
            files={"OPS/toc.ncx": "<ncx"})
        self.assertEqual(book.pages, [])


def chapters(*specs):
    """search.Chapter for each (text, {id: index})."""
    from bookfish.search import Chapter
    return [Chapter(text, ids=ids) for text, ids in specs]


def info(marks, total=0):
    """page_numbers' result for marks per chapter ([fragment, label, counted])."""
    start = []
    current = None
    for chapter_marks in marks:
        start.append(current)
        if chapter_marks:
            current = chapter_marks[-1][1:]
    return {"total": total, "marks": marks, "start": start}


def title_at(spine, index):
    return "%d:%d" % (spine, index)


class PageFinderListTest(unittest.TestCase):

    def setUp(self):
        self.finder = PageFinder(
            info([[["pg1", "1", True]], [["pg2", "2", True], ["pg3", "3", True]], []], 3),
            chapters(("Title. One page", {"pg1": 7}),
                     ("Two pages here", {"pg2": 0, "pg3": 9}),
                     ("Notes", {})),
            [True, True, False], "en")

    def test_last_mark_at_or_before_the_place(self):
        self.assertEqual(self.finder.label(0, 7), "1")
        self.assertEqual(self.finder.label(1, 8), "2")
        self.assertEqual(self.finder.label(1, 9), "3")

    def test_none_before_the_first_page(self):
        self.assertEqual(self.finder.label(0, 6), "")

    def test_chapter_without_marks_has_the_page_before(self):
        self.assertEqual(self.finder.label(2, 3), "3")

    def test_place_outside_the_book_has_none(self):
        self.assertEqual(self.finder.label(5, 0), "")
        self.assertEqual(self.finder.label(-1, 0), "")

    def test_marks_at_one_place_the_last_counts(self):
        # Pictures printed as pages of their own share the next text's place.
        finder = PageFinder(info([[["pg5", "5", True], ["pg6", "6", True], ["pg7", "7", True]]]),
                            chapters(("Text", {"pg5": 0, "pg6": 0, "pg7": 0})), [True], "en")
        self.assertEqual(finder.label(0, 2), "7")

    def test_mark_not_in_the_text_is_passed_over(self):
        finder = PageFinder(info([[["pg1", "1", True], ["gone", "2", True]]]),
                            chapters(("Some text", {"pg1": 0})), [True], "en")
        self.assertEqual(finder.label(0, 5), "1")

    def test_stops_in_reading_order_with_the_start_of_the_book(self):
        stops = self.finder.stops(title_at)
        self.assertEqual([(s["label"], s["spine"], s["mark"]) for s in stops],
                         [("", 0, -1), ("1", 0, 0), ("2", 1, 0), ("3", 1, 1)])
        self.assertEqual([s["title"] for s in stops], ["0:0", "0:7", "1:0", "1:9"])
        self.assertFalse(stops[0]["counted"])
        self.assertTrue(stops[1]["counted"])

    def test_no_start_stop_if_the_first_page_begins_the_book(self):
        finder = PageFinder(info([[["", "1", True], ["pg2", "2", True]]]),
                            chapters(("One. Two", {"pg2": 5})), [True], "en")
        self.assertEqual([s["mark"] for s in finder.stops(title_at)], [0, 1])

    def test_chapters_outside_the_reading_order_have_no_stops(self):
        finder = PageFinder(info([[["n1", "1", True]], [["pg2", "2", True]]]),
                            chapters(("Note", {"n1": 0}), ("Text", {"pg2": 0})), [False, True], "en")
        self.assertEqual([(s["spine"], s["mark"]) for s in finder.stops(title_at)], [(1, 0)])

    def test_stop_for_a_mark_python_does_not_find(self):
        finder = PageFinder(info([[["", "1", True], ["gone", "2", True]]]),
                            chapters(("Text", {})), [True], "en")
        stops = finder.stops(title_at)
        self.assertEqual([(s["label"], s["mark"], s["title"]) for s in stops],
                         [("1", 0, "0:0"), ("2", 1, "0:0")])

    def test_roman_pages_are_not_counted(self):
        finder = PageFinder(info([[["", "vii", False], ["pg1", "1", True]]]),
                            chapters(("Preface. Text", {"pg1": 9})), [True], "en")
        self.assertEqual([s["counted"] for s in finder.stops(title_at)], [False, True])


class PageFinderEstimateTest(unittest.TestCase):

    def test_chars_per_page_by_language(self):
        self.assertEqual(chars_per_page("de-DE"), 1600)
        self.assertEqual(chars_per_page("DE"), 1600)
        self.assertEqual(chars_per_page("en"), 1700)
        self.assertEqual(chars_per_page(None), 1700)

    def finder(self, *lengths, linear=None, language="de"):
        texts = [("x" * n, {}) for n in lengths]
        return PageFinder(None, chapters(*texts), linear or [True] * len(lengths), language)

    def test_total_rounds_up(self):
        self.assertEqual(self.finder(1600, 1601).total, 3)
        self.assertEqual(self.finder(0).total, 1)

    def test_label_counts_the_chapters_before(self):
        finder = self.finder(2000, 3000)
        self.assertEqual(finder.label(0, 0), "1")
        self.assertEqual(finder.label(0, 1600), "2")
        self.assertEqual(finder.label(1, 1200), "3")
        self.assertEqual(finder.label(1, 3000), "4")

    def test_spaces_are_folded_as_the_reading_page_counts(self):
        finder = PageFinder(None, chapters(("a  \n  b" * 800, {})), [True], "de")
        self.assertEqual(finder.lengths, [len("a b" * 800)])

    def test_chapters_outside_the_reading_order_count_nothing(self):
        finder = self.finder(1000, 5000, 1000, linear=[True, False, True])
        self.assertEqual(finder.total, 2)
        self.assertEqual(finder.label(1, 4000), "1")
        self.assertEqual(finder.label(2, 900), "2")

    def test_stops_where_pages_begin(self):
        finder = self.finder(2400, 0, 2400)
        stops = finder.stops(title_at)
        self.assertEqual([(s["label"], s["spine"], s["share"]) for s in stops],
                         [("1", 0, 0.0), ("2", 0, 1600 / 2400), ("3", 2, 800 / 2400)])
        self.assertEqual(stops[1]["title"], "0:1600")

    def test_stops_leave_out_chapters_outside_the_reading_order(self):
        finder = self.finder(500, 1000, linear=[False, True])
        self.assertEqual([s["spine"] for s in finder.stops(title_at)], [1])

    def test_no_stops_without_reading_order(self):
        self.assertEqual(self.finder(500, linear=[False]).stops(title_at), [])
