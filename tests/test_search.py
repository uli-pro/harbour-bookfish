import unittest
from xml.etree import ElementTree

from bookfish.search import BookIndex, chapter_of, fold, read_chapter

from .helpers import MINI_DIR, TempDirTestCase, write_files

CONTAINER = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles>
    <rootfile full-path="OPS/package.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

OPF = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/"
         version="3.0" unique-identifier="uid">
  <metadata><dc:identifier id="uid">x</dc:identifier><dc:title>T</dc:title></metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    {items}
  </manifest>
  <spine>{refs}</spine>
</package>"""

NAV = """<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<body><nav epub:type="toc"><ol>{entries}</ol></nav>{pages}</body></html>"""


def xhtml(body):
    return ('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Head</title></head>'
            '<body>' + body + '</body></html>')


def chapter(body):
    return chapter_of(ElementTree.fromstring(xhtml(body)).find("{http://www.w3.org/1999/xhtml}body"))


def texts(ch):
    return [ch.text[a:b] for a, b in ch.paragraphs]


class FoldTest(unittest.TestCase):

    def test_accents_case_and_ligatures(self):
        self.assertEqual(fold("Über ÉCOLE Straße ﬁne"), "uber ecole strasse fine")

    def test_punctuation_becomes_space(self):
        self.assertEqual(fold("„Don’t“—go!"), " don t  go ")
        self.assertEqual(fold("don't").split(), fold("don’t").split())

    def test_invisible_characters_go(self):
        # Soft hyphen, zero width space and joiner.
        self.assertEqual(fold("Schwal­be Wort​teil a‍b"), "schwalbe wortteil ab")

    def test_line_breaks_are_spaces(self):
        self.assertEqual(fold("a\nb\tc d"), "a b c d")


class ChapterTest(TempDirTestCase):

    def test_text_like_text_content(self):
        ch = chapter('<p>One <b>two</b> three</p>\n<p>Four</p>')
        self.assertEqual(ch.text, "One two three\nFour")

    def test_paragraphs_at_block_boundaries(self):
        ch = chapter('<div>Loose<p>First <i>para</i></p>tail<div><div>Deep</div></div></div>'
                     '<h2>Head</h2>line<br/>break')
        self.assertEqual(texts(ch), ["Loose", "First para", "tail", "Deep", "Head", "line" + "break"])

    def test_blank_paragraphs_skipped(self):
        ch = chapter('<p>a</p>\n  <p> </p>\n<p>b</p>')
        self.assertEqual([t.strip() for t in texts(ch)], ["a", "b"])

    def test_ids_mark_their_start(self):
        ch = chapter('<p id="p1">ab<span id="s1">cd</span></p><p id="p2">ef</p>')
        self.assertEqual(ch.ids, {"p1": 0, "s1": 2, "p2": 4})

    def test_ids_mark_their_end(self):
        ch = chapter('<p id="p1">ab<span id="s1">cd</span>x</p>tail<p id="p2">ef</p><br id="e"/>')
        self.assertEqual(ch.ends, {"p1": 5, "s1": 4, "p2": 11, "e": 11})

    def test_repeated_id_ends_with_the_first_element(self):
        ch = chapter('<p id="a">ab<span id="a">cd</span>e</p><p id="a">fg</p>')
        self.assertEqual((ch.ids["a"], ch.ends["a"]), (0, 5))

    def test_other_namespaces_hold_text_but_no_blocks(self):
        ch = chapter('<p>a</p><svg xmlns="http://www.w3.org/2000/svg"><text>pic</text></svg>'
                     '<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math>')
        self.assertEqual(ch.text, "apicx")
        self.assertEqual(texts(ch), ["a", "picx"])

    def test_deep_nesting(self):
        ch = chapter("<div>" * 5000 + "deep" + "</div>" * 5000)
        self.assertEqual(texts(ch), ["deep"])

    def test_file_without_namespace(self):
        write_files(self.tmp, {"c.html": "<html><head><title>Not body</title></head>"
                                         "<body><p>a</p><p>b</p></body></html>"})
        ch = read_chapter(self.tmp, "c.html")
        self.assertEqual(texts(ch), ["a", "b"])

    def test_html_entities(self):
        write_files(self.tmp, {"c.xhtml": xhtml("<p>a&nbsp;b&mdash;c</p>")})
        self.assertEqual(read_chapter(self.tmp, "c.xhtml").text, "a b—c")

    def test_unreadable_chapter_is_empty(self):
        write_files(self.tmp, {"bad.xhtml": "<html"})
        self.assertEqual(read_chapter(self.tmp, "bad.xhtml").text, "")
        self.assertEqual(read_chapter(self.tmp, "missing.xhtml").paragraphs, [])

    def test_utf16_counts_like_javascript(self):
        ch = chapter("<p>\U0001F600 x</p>")
        self.assertEqual(ch.utf16(0), 0)
        self.assertEqual(ch.utf16(1), 2)
        self.assertEqual(ch.utf16(3), 4)
        ch = chapter("<p>a\U0001F600b\U0001F601c</p>")
        self.assertEqual([ch.utf16(i) for i in range(6)], [0, 1, 3, 4, 6, 7])
        self.assertEqual(chapter("<p>äx</p>").utf16(1), 1)

    def test_index_from_utf16(self):
        ch = chapter("<p>a\U0001F600b\U0001F601c</p>")
        # Inside a character beyond the BMP: its start.
        self.assertEqual([ch.index(u) for u in range(8)], [0, 1, 1, 2, 3, 3, 4, 5])
        for i in range(6):
            self.assertEqual(ch.index(ch.utf16(i)), i)
        self.assertEqual(chapter("<p>abc</p>").index(2), 2)


class BookIndexTest(TempDirTestCase):

    def book(self, chapters, toc=(), pages=()):
        """chapters: list of XHTML bodies; toc and pages (the page list):
        (title, href) pairs."""
        files = {"META-INF/container.xml": CONTAINER}
        items = []
        refs = []
        for i, body in enumerate(chapters):
            items.append('<item id="c{0}" href="c{0}.xhtml" media-type="application/xhtml+xml"/>'.format(i))
            refs.append('<itemref idref="c{}"/>'.format(i))
            files["OPS/c{}.xhtml".format(i)] = xhtml(body)
        files["OPS/package.opf"] = OPF.format(items="".join(items), refs="".join(refs))
        page_list = "".join('<li><a href="{}">{}</a></li>'.format(href, name) for name, href in pages)
        files["OPS/nav.xhtml"] = NAV.format(entries="".join(
            '<li><a href="{}">{}</a></li>'.format(href, title) for title, href in toc),
            pages='<nav epub:type="page-list"><ol>{}</ol></nav>'.format(page_list) if pages else "")
        write_files(self.tmp, files)
        return BookIndex(self.tmp)

    def test_all_words_in_one_paragraph_in_any_order(self):
        index = self.book(['<p>The swallow flew.</p><p>The prince wept.</p>',
                           '<p>Prince and Swallow parted.</p>'])
        result = index.search("swallow prince")
        self.assertEqual(result["total"], 1)
        hit = result["hits"][0]
        self.assertEqual(hit["spine"], 1)
        self.assertEqual(hit["text"], "Prince")

    def test_parts_of_words_case_and_accents(self):
        index = self.book(['<p>Die Schwalben flogen über die Stadt.</p>'])
        self.assertEqual(index.search("SCHWALB uber")["total"], 1)
        self.assertEqual(index.search("schwalbe")["hits"][0]["text"], "Schwalbe")

    def test_place_of_hit_matches_text(self):
        index = self.book(['<p>x</p><p>Ein „Straße“ und <b>stras</b>se</p>',
                           '<p>\U0001F600 Emoji then word</p>'])
        hit = index.search("strasse")["hits"][0]
        text = index.chapters[0].text
        self.assertEqual(hit["text"], "Straße")
        self.assertEqual(text[hit["offset"]:hit["offset"] + hit["length"]], "Straße")
        hit = index.search("word")["hits"][0]
        # UTF-16: the emoji counts twice.
        self.assertEqual(hit["offset"], len("\U0001F600 Emoji then ") + 1)
        self.assertEqual(hit["length"], 4)

    def test_match_keeps_accent_of_decomposed_text(self):
        index = self.book(['<p>un café noir</p>'])
        hit = index.search("cafe")["hits"][0]
        self.assertEqual(hit["text"], "café")
        self.assertEqual(hit["length"], 5)

    def test_match_across_elements_and_soft_hyphen(self):
        index = self.book(['<p>a Schwal­be <i>b</i></p>'])
        hit = index.search("schwalbe")["hits"][0]
        self.assertEqual(hit["text"], "Schwal­be")

    def test_no_words_no_hits(self):
        index = self.book(['<p>text</p>'])
        self.assertEqual(index.search(" ,; "), {"hits": [], "total": 0, "before": -1, "pagesEstimated": True})

    def test_limit_and_total(self):
        index = self.book(['<p>word</p>' * 5])
        result = index.search("word", limit=3)
        self.assertEqual((len(result["hits"]), result["total"]), (3, 5))

    def test_before_the_place_read(self):
        index = self.book(['<p>word</p><p id="here">word</p><p>word</p>', '<p>word</p>'])
        here = {"spine": 0, "id": "here", "fraction": 0.0}
        self.assertEqual(index.search("word", here)["before"], 1)
        # Without the id, the fraction of the chapter counts.
        self.assertEqual(index.search("word", {"spine": 0, "id": "", "fraction": 1.0})["before"], 3)
        self.assertEqual(index.search("word", {"spine": 1, "id": "", "fraction": 0.0})["before"], 3)
        # The page read, by its first character, before the fraction.
        self.assertEqual(index.search("word", {"spine": 0, "id": "", "offset": 4, "fraction": 1.0})["before"], 1)
        self.assertEqual(index.search("word", {"spine": 0, "id": "", "offset": -1, "fraction": 1.0})["before"], 3)
        # No place: no line among the hits.
        self.assertEqual(index.search("word", None)["before"], -1)
        self.assertEqual(index.search("word", {"spine": 7})["before"], -1)
        # QML may hand a whole number over as a float.
        self.assertEqual(index.search("word", {"spine": 0.0, "id": "here"})["before"], 1)

    def test_before_within_the_paragraph(self):
        # Folded text is longer (ß → ss, … → spaces) or shorter (soft
        # hyphen) than the text; the place inside the paragraph still counts.
        index = self.book(['<p>' + "ß" * 30 + ' word <span id="a">x</span> …' + "­" * 30 + ' late</p>'])
        self.assertEqual(index.search("word", {"spine": 0, "id": "a"})["before"], 1)
        self.assertEqual(index.search("late", {"spine": 0, "id": "a"})["before"], 0)

    def test_chapter_titles_from_toc(self):
        index = self.book(['<p>front word</p>',
                           '<h1 id="a">A</h1><p>word one</p><h1 id="b">B</h1><p>word two</p>',
                           '<p>word three</p>'],
                          toc=[("Part A", "c1.xhtml#a"), ("Part B", "c1.xhtml#b"), ("Last", "c2.xhtml")])
        self.assertEqual([h["chapter"] for h in index.search("word")["hits"]],
                         ["", "Part A", "Part B", "Last"])

    def test_snippet(self):
        long = " ".join("w{}".format(i) for i in range(100))
        index = self.book(['<p>' + long + ' swallow ' + long + '</p>'])
        snippet = index.search("swallow")["hits"][0]["snippet"]
        self.assertEqual(snippet[0], {"text": "…", "match": False})
        self.assertEqual(snippet[-1], {"text": "…", "match": False})
        self.assertIn({"text": "swallow", "match": True}, snippet)
        shown = "".join(part["text"] for part in snippet[1:-1])
        # Whole words only, and some context before the match.
        self.assertTrue(shown.startswith("w"))
        self.assertTrue(shown.split()[-1].startswith("w"))
        self.assertGreater(shown.index("swallow"), 30)

    def test_snippet_marks_every_word_and_folds_spaces(self):
        index = self.book(['<p>The   little\nSwallow and the little Prince.</p>'])
        snippet = index.search("little prince")["hits"][0]["snippet"]
        self.assertEqual(snippet, [
            {"text": "The ", "match": False}, {"text": "little", "match": True},
            {"text": " Swallow and the ", "match": False}, {"text": "little", "match": True},
            {"text": " ", "match": False}, {"text": "Prince", "match": True},
            {"text": ".", "match": False}])

    def test_sentence_as_a_place_to_go_to(self):
        index = self.book(['<p>x</p>',
                           '<h1 id="h">Two</h1><p><span id="s1">\U0001F600 First  one.</span>'
                           '<span id="s2">Second.</span></p>'],
                          toc=[("Part two", "c1.xhtml#h")])
        place = index.sentence(1, "s1")
        self.assertEqual(place, {"spine": 1, "chapter": "Part two", "offset": 3, "length": 14,
                                 "text": "\U0001F600 First  one.", "line": "\U0001F600 First one."})
        self.assertEqual(index.sentence(1, "s2")["offset"], 17)

    def test_sentence_line_is_cut_after_a_word(self):
        words = " ".join("word{}".format(i) for i in range(40))
        index = self.book(['<p id="s">' + words + '</p>'])
        line = index.sentence(0, "s")["line"]
        self.assertTrue(line.endswith("…"))
        self.assertLessEqual(len(line), 101)
        self.assertTrue(words.startswith(line[:-1]))
        self.assertEqual(words[len(line) - 1], " ")

    def test_sentence_gone(self):
        index = self.book(['<p id="s">a</p><p id="empty"></p>'])
        for spine, ident in ((0, "missing"), (0, "empty"), (5, "s"), (-1, "s")):
            place = index.sentence(spine, ident)
            self.assertEqual((place["offset"], place["text"]), (-1, ""), (spine, ident))

    def test_text_at_a_page(self):
        long = "First words of a rather long paragraph that goes on and on."
        index = self.book(['<p>x</p>',
                           '<h1 id="h">Two</h1><p>\U0001F600 ' + long + '</p><p>Next.</p>'],
                          toc=[("Part two", "c1.xhtml#h")])
        place = index.text_at(1, 3)
        self.assertEqual((place["spine"], place["chapter"], place["offset"]), (1, "Part two", 3))
        text = place["text"]
        self.assertTrue(text.startswith("\U0001F600 First words"))
        self.assertLessEqual(len(text), 40)
        # Ends after a word, and its length counts like JavaScript.
        self.assertEqual(("\U0001F600 " + long)[len(text)], " ")
        self.assertEqual(place["length"], len(text) + 1)
        self.assertTrue(place["line"].startswith("\U0001F600 First words"))
        self.assertEqual(index.text_at(1, 0)["chapter"], "Part two")

    def test_text_at_skips_spaces_and_stops_at_the_paragraph(self):
        index = self.book(['<p>Short.</p><p>   Other words.</p>'])
        self.assertEqual(index.text_at(0, 0)["text"], "Short.")
        place = index.text_at(0, 6)
        self.assertEqual((place["offset"], place["text"]), (9, "Other words."))

    def test_text_at_paragraphs_without_space_between(self):
        index = self.book(['<p>Short words.</p><p>Other</p>'])
        self.assertEqual(index.text_at(0, 0)["text"], "Short words.")
        long = " ".join(["word"] * 20)
        index = self.book(['<p>' + long + '</p>'])
        text = index.text_at(0, 0)["text"]
        self.assertLessEqual(len(text), 40)
        self.assertTrue(text.endswith("word"))

    def test_text_at_gone(self):
        index = self.book(['<p>abc</p><p>   </p>'])
        for spine, offset in ((0, 3), (0, 4), (0, 99), (0, -1), (5, 0), (-1, 0)):
            place = index.text_at(spine, offset)
            self.assertEqual((place["offset"], place["text"]), (-1, ""), (spine, offset))

    def test_mini_readaloud(self):
        index = BookIndex(MINI_DIR)
        result = index.search("happy prince")
        self.assertGreater(result["total"], 0)
        self.assertEqual(result["hits"][0]["chapter"], "Title Page")


class PagesTest(TempDirTestCase):

    book = BookIndexTest.book

    def paged(self):
        return self.book(['<h1 id="h">Title</h1><p>One <span id="p1"/>first page.</p>',
                          '<p id="a">Still <span id="p2"/>second 😀 <span id="p3"/>third.</p>'],
                         toc=[("Title", "c0.xhtml#h"), ("Part", "c1.xhtml#a")],
                         pages=[("1", "c0.xhtml#p1"), ("2", "c1.xhtml#p2"), ("3", "c1.xhtml#p3")])

    def test_hits_have_their_page(self):
        result = self.paged().search("third")
        self.assertEqual([hit["page"] for hit in result["hits"]], ["3"])
        self.assertFalse(result["pagesEstimated"])

    def test_labels_of_places_and_elements(self):
        index = self.paged()
        text = index.chapters[1].text
        # After the emoji: UTF-16 counts it twice.
        third = text.index("third") + 1
        result = index.page_labels([{"spine": 0, "fragment": "h"}, {"spine": 1, "fragment": "a"},
                                    {"spine": 1.0, "offset": third}, {"spine": 1, "offset": 0},
                                    {"spine": 9, "offset": 0}, {"spine": 0}, None,
                                    {"spine": 0, "fragment": ""}])
        self.assertEqual(result, {"estimated": False, "labels": ["", "1", "3", "1", "", "", "", ""]})

    def test_flip_stops(self):
        result = self.paged().flip_stops()
        self.assertFalse(result["estimated"])
        self.assertEqual([(s["label"], s["spine"], s["mark"], s["title"]) for s in result["stops"]],
                         [("", 0, -1, "Title"), ("1", 0, 0, "Title"), ("2", 1, 0, "Part"), ("3", 1, 1, "Part")])

    def test_estimated_without_page_list(self):
        index = self.book(['<p>' + "word " * 1000 + '</p>'])
        self.assertTrue(index.search("word")["pagesEstimated"])
        self.assertEqual(index.search("word")["hits"][0]["page"], "1")
        result = index.flip_stops()
        self.assertTrue(result["estimated"])
        self.assertEqual([s["label"] for s in result["stops"]], ["1", "2", "3"])

