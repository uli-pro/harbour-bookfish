import unittest

from bookfish.package import read_ncx_pages, read_nav_pages
from bookfish.pages import RUN, PageTarget, page_numbers, parse_name

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
