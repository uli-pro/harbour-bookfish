import unittest

from bookfish import notes
from bookfish.notes import follow_link, is_short

from .helpers import TempDirTestCase, write_files


def xhtml(body):
    return ('<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
            '<head><title>Head</title></head><body>' + body + '</body></html>')


class ShortTest(unittest.TestCase):

    def test_marks(self):
        for text in ("1", "12", "123", "[3]", "(4)", "12a", "*", "**", "†", "a", "iv", " 7 ", "4,", "12.", "[3];", "[XXIV]", "[iv]", "(xviii)"):
            self.assertTrue(is_short(text), text)

    def test_words(self):
        for text in ("1234", "Chapter 1", "see", "Contents", "", "12 13", "civil", "xxviii", "4,,", ",4", "[civilian]", "[XXIV"):
            self.assertFalse(is_short(text), text)


class FollowTest(TempDirTestCase):

    def book(self, notes_body):
        write_files(self.tmp, {"notes.xhtml": xhtml(notes_body)})
        self.spine = ["text.xhtml", "notes.xhtml"]
        self.toc = set()

    def follow(self, href):
        # A mark in running text, as in most books.
        if href.startswith("notes.xhtml"):
            write_files(self.tmp, {"text.xhtml": xhtml(
                '<h1>One</h1><p>Words before.</p><p>It was so<sup><a href="%s">1</a></sup>.</p>' % href)})
        return follow_link(self.tmp, self.spine, self.toc, "text.xhtml", href, 0)

    def test_paragraph_per_note_with_neighbours(self):
        self.book('<h1>Notes</h1><p id="n1">1 First <i>note</i>.</p><p id="n2">2 Second.</p>'
                  '<p>Goes on.</p><p id="n3">3 Third.</p>')
        result = self.follow("notes.xhtml#n2")
        self.assertEqual(result["paragraphs"],
                         ["1 First <i>note</i>.", "2 Second.", "Goes on.", "3 Third."])
        self.assertEqual((result["first"], result["last"]), (1, 2))

    def test_empty_anchor_at_paragraph_start(self):
        self.book('<p>Notes</p><p><a id="n1"/>1. One.</p><p><a id="n2"/>2. Two.</p>')
        result = self.follow("notes.xhtml#n1")
        self.assertEqual(result["paragraphs"][result["first"]:result["last"] + 1], ["1. One."])

    def test_term_and_explanation(self):
        # Karl May: the number as a term, the note as its explanation, which
        # carries an id of its own (a page break).
        self.book('<p>Notes</p><dl><dt id="n1"><a href="text.xhtml#b1">[1]</a></dt>'
                  '<dd id="pb_1"><p>See the picture.</p></dd></dl>'
                  '<dl><dt id="n2"><a href="text.xhtml#b2">[2]</a></dt><dd><p>Other.</p></dd></dl>')
        result = self.follow("notes.xhtml#n1")
        self.assertEqual(result["paragraphs"][result["first"]:result["last"] + 1],
                         ["[1]", "See the picture."])

    def test_notes_in_a_table(self):
        # Duhigg: all notes of a chapter in one table, the first one's id on it.
        self.book('<p>Notes</p><table id="n1"><tr><td><a href="text.xhtml#b1">1</a></td><td>First.</td></tr>'
                  '<tr id="n2"><td><a href="text.xhtml#b2">2</a></td><td>Second.</td></tr></table>')
        result = self.follow("notes.xhtml#n1")
        self.assertEqual(result["paragraphs"][result["first"]:result["last"] + 1], ["1 First."])

    def test_div_paragraphs(self):
        self.book('<div>Notes</div><div id="n1">1 First,</div><div>still first.</div><div id="n2">2 Second.</div>')
        result = self.follow("notes.xhtml#n1")
        self.assertEqual(result["paragraphs"][result["first"]:result["last"] + 1],
                         ["1 First,", "still first."])

    def test_link_back_inside_the_note(self):
        # Virkler: the verse, then the letter leading back, then the note.
        self.book('<p>Notes</p><p id="n1">2:3 <a href="text.xhtml#b1"><sup>a</sup></a> literally, a Greek</p>'
                  '<p id="n2">2:3 <a href="text.xhtml#b2"><sup>b</sup></a> a mark</p>')
        result = self.follow("notes.xhtml#n1")
        self.assertEqual(result["paragraphs"][result["first"]:result["last"] + 1],
                         ["2:3 a literally, a Greek"])

    def test_page_anchor_inside_the_note(self):
        # Keller: an empty anchor for a printed page inside the note.
        self.book('<p>Notes</p><p class="footnote"><a id="n1" href="text.xhtml#b1">1</a>'
                  'Max Scheler, <a id="page_383"/>p. 68.</p><p class="footnote"><a id="n2" href="text.xhtml#b2">2</a>Ebd.</p>')
        result = self.follow("notes.xhtml#n1")
        self.assertEqual(result["paragraphs"][result["first"]:result["last"] + 1], ["1Max Scheler, p. 68."])

    def test_neighbours_stop_at_headings_and_limit(self):
        many = "".join('<p id="m%d">%d Note.</p>' % (i, i) for i in range(300))
        self.book('<h2>Chapter 1</h2><p id="x">0 Other.</p><h2>Chapter 2</h2>' + many + '<h2>Chapter 3</h2><p>Later.</p>')
        result = self.follow("notes.xhtml#m150")
        paragraphs = result["paragraphs"]
        self.assertEqual(paragraphs[result["first"]], "150 Note.")
        self.assertEqual(result["first"], notes.NEIGHBOURS)
        self.assertEqual(len(paragraphs) - 1 - result["last"], notes.NEIGHBOURS)
        result = self.follow("notes.xhtml#m0")
        self.assertEqual((result["first"], result["paragraphs"][0]), (0, "0 Note."))
        result = self.follow("notes.xhtml#m299")
        self.assertEqual(result["paragraphs"][-1], "299 Note.")

    def test_same_file_without_neighbours(self):
        text = ('<h1>One</h1><p>Text<a href="#f1">*</a> here.</p><p>More text.</p>'
                '<p id="f1">* The note.</p><p id="f2">** Another.</p>')
        write_files(self.tmp, {"text.xhtml": xhtml(text)})
        self.spine, self.toc = ["text.xhtml"], set()
        result = self.follow("#f1")
        self.assertEqual(result, {"paragraphs": ["* The note."], "first": 0, "last": 0, "mark": "*"})

    def test_long_note_alone_is_cut(self):
        long = "".join("<p>%s</p>" % ("x" * 3000) for _ in range(5))
        text = '<h1>One</h1><p>Text<a href="#f1">1</a>.</p><div id="f1">' + long + '</div>'
        write_files(self.tmp, {"text.xhtml": xhtml(text)})
        self.spine, self.toc = ["text.xhtml"], set()
        result = self.follow("#f1")
        self.assertEqual(len(result["paragraphs"]), 4)
        self.assertEqual(result["paragraphs"][-1], "…")

    def test_place_inside_a_paragraph(self):
        # A mark leading into running text: that paragraph alone.
        self.book('<p>Notes</p><p>Before and <span id="b1"/>after.</p><p>Next.</p>')
        self.assertEqual(self.follow("notes.xhtml#b1"),
                         {"paragraphs": ["Before and after."], "first": 0, "last": 0, "mark": "1"})

    def test_anchors_between_paragraphs(self):
        # Nyman: an empty anchor before each note's paragraph; Murphy: page
        # anchors between paragraphs of the text.
        self.book('<p>Notes</p><a id="n1"/><p><a href="text.xhtml#b1">1</a> One.</p><br/>'
                  '<a id="n2"/><p><a href="text.xhtml#b2">2</a> Two.</p>'
                  + "".join("<p>Text %d.</p>" % i for i in range(50)) + '<a id="n3"/><p>Three.</p>')
        result = self.follow("notes.xhtml#n1")
        self.assertEqual(result["paragraphs"][result["first"]:result["last"] + 1], ["1 One."])
        result = self.follow("notes.xhtml#n2")
        self.assertEqual(result["last"] - result["first"], 50)

    def test_note_without_text(self):
        self.book('<p>Notes</p><p id="n1">1 One.</p><p id="n2"><img src="x.png"/></p><p id="n3">3 Three.</p>')
        self.assertEqual(self.follow("notes.xhtml#n2"), {})

    def test_long_paragraph_is_cut(self):
        self.book('<p>Notes</p><p>Before <span id="n1"/>' + "<i>x</i>" * 20000 + '</p>')
        result = self.follow("notes.xhtml#n1")
        paragraph = result["paragraphs"][0]
        self.assertEqual(paragraph.count("x"), notes.MAX_CHARS - len("Before "))
        self.assertTrue(paragraph.endswith("\u2026</i>") or paragraph.endswith("</i>\u2026"), paragraph[-20:])
        self.assertEqual(paragraph.count("<i>"), paragraph.count("</i>"))

    def test_no_break_space_stays(self):
        self.book('<p>Notes</p><p id="n1">1 See p.\u00a012.</p><p id="n2">2</p>')
        result = self.follow("notes.xhtml#n1")
        self.assertEqual(result["paragraphs"][result["first"]], "1 See p.\u00a012.")

    def test_bold_and_italic_by_class(self):
        # Duhigg: the words of the text in bold, titles in italic, both by class.
        write_files(self.tmp, {"style/book.css": "/* .x { font-weight: bold } */ .k { font-weight: 800 }\n"
                                                 "span.t, .u { font-style: italic; } p .no { font-style: italic }\n"
                                                 "@media screen { .m { font: italic bold 1em serif } }"})
        notes_file = ('<html xmlns="http://www.w3.org/1999/xhtml"><head><link rel="stylesheet" href="style/book.css"/>'
                      '<style>.s { font-weight: bold }</style></head><body><p>Notes</p>'
                      '<p id="n1"><span class="k">began diets</span> Wadden, <span class="t">Obesity</span> '
                      '<span class="no">x</span> <span class="x">y</span> <span class="m">m</span> <span class="s">s</span>.</p>'
                      '<p id="n2">2</p></body></html>')
        write_files(self.tmp, {"notes.xhtml": notes_file})
        self.spine, self.toc = ["text.xhtml", "notes.xhtml"], set()
        result = self.follow("notes.xhtml#n1")
        self.assertEqual(result["paragraphs"][result["first"]],
                         "<b>began diets</b> Wadden, <i>Obesity</i> x y <i><b>m</b></i> <b>s</b>.")

    def test_markup_is_escaped(self):
        self.book('<p>Notes</p><p id="n1">1 a &lt;b&gt; &amp; <b>bold</b><br/>line <img src="x.png"/>'
                  '<span>&lt;img src=x&gt;</span></p><p id="n2">2</p>')
        result = self.follow("notes.xhtml#n1")
        self.assertEqual(result["paragraphs"][result["first"]],
                         "1 a &lt;b&gt; &amp; <b>bold</b><br>line &lt;img src=x&gt;")


class JumpTest(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.spine = ["toc.xhtml", "text.xhtml", "notes.xhtml"]

    def follow(self, href, chapter, ordinal=0, toc=()):
        return follow_link(self.tmp, self.spine, set(toc), chapter, href, ordinal)

    def test_long_link(self):
        write_files(self.tmp, {"text.xhtml": xhtml('<h1>A</h1><p>See <a href="notes.xhtml#n1">the notes</a>.</p>'),
                               "notes.xhtml": xhtml('<p>N</p><p id="n1">1 Note.</p>')})
        self.assertEqual(self.follow("notes.xhtml#n1", "text.xhtml"), {"jump": 2, "id": "n1"})

    def test_number_leading_back(self):
        write_files(self.tmp, {"notes.xhtml": xhtml('<p>N</p><p id="n1"><a href="text.xhtml#b1">1</a> Note.</p>'),
                               "text.xhtml": xhtml('<h1>A</h1><p>Text<a id="b1" href="notes.xhtml#n1">1</a>.</p>')})
        self.assertEqual(self.follow("text.xhtml#b1", "notes.xhtml"), {"jump": 1, "id": "b1"})

    def test_list_page(self):
        links = "".join('<p>Ch <a href="text.xhtml#c%d">%d</a> <a href="text.xhtml#c%d">The chapter called %d</a></p>'
                        % (i, i, i, i) for i in range(6))
        body = "<h1>A</h1>" + "".join('<p>Words.</p><p id="c%d">Text.</p>' % (i,) for i in range(6))
        write_files(self.tmp, {"toc.xhtml": xhtml('<h1>Contents</h1>' + links), "text.xhtml": xhtml(body)})
        self.assertEqual(self.follow("text.xhtml#c3", "toc.xhtml", 0), {"jump": 1, "id": "c3"})

    def test_place_in_the_contents(self):
        write_files(self.tmp, {"text.xhtml": xhtml('<h1>A</h1><p>Text<a href="#c2">2</a>.</p><p id="c2">Two.</p>')})
        self.assertEqual(self.follow("#c2", "text.xhtml", toc=[("text.xhtml", "c2")]),
                         {"jump": 1, "id": "c2"})

    def test_start_of_a_chapter(self):
        write_files(self.tmp, {"text.xhtml": xhtml('<h1>A</h1><p>Text<a href="notes.xhtml">1</a> '
                                                   'and<a href="notes.xhtml#top">2</a> and<a href="notes.xhtml#h">3</a>.</p>'),
                               "notes.xhtml": xhtml('<div id="top"><h2 id="h">Notes</h2><p>1 Note.</p></div>')})
        self.assertEqual(self.follow("notes.xhtml", "text.xhtml"), {"jump": 2, "id": ""})
        self.assertEqual(self.follow("notes.xhtml#top", "text.xhtml"), {"jump": 2, "id": "top"})
        self.assertEqual(self.follow("notes.xhtml#h", "text.xhtml"), {"jump": 2, "id": "h"})

    def test_nowhere(self):
        write_files(self.tmp, {"text.xhtml": xhtml('<h1>A</h1><p>Text<a href="http://x.org/#a">1</a> '
                                                   'and<a href="../../etc/passwd#a">2</a> and<a href="#missing">3</a> '
                                                   'and<a href="other.xhtml#a">4</a>.</p>')})
        self.assertEqual(self.follow("http://x.org/#a", "text.xhtml"), {})
        self.assertEqual(self.follow("../../etc/passwd#a", "text.xhtml"), {})
        self.assertEqual(self.follow("#missing", "text.xhtml"), {})
        self.assertEqual(self.follow("other.xhtml#a", "text.xhtml"), {})

    def test_links_that_do_nothing(self):
        write_files(self.tmp, {"text.xhtml": xhtml('<h1>A</h1><p>Text<a href="#">1</a> and<a href="">2</a>.</p>')})
        self.assertEqual(self.follow("#", "text.xhtml"), {})
        self.assertEqual(self.follow("", "text.xhtml"), {})

    def test_which_of_several_links(self):
        write_files(self.tmp, {"text.xhtml": xhtml('<h1>A</h1><p><a href="notes.xhtml#n1">1</a> leads.</p>'
                                                   '<p>Text<a href="notes.xhtml#n1">1</a>.</p>'),
                               "notes.xhtml": xhtml('<p>N</p><p id="n1">1 Note.</p>')})
        self.assertEqual(self.follow("notes.xhtml#n1", "text.xhtml", 0), {"jump": 2, "id": "n1"})
        self.assertIn("paragraphs", self.follow("notes.xhtml#n1", "text.xhtml", 1))


if __name__ == "__main__":
    unittest.main()
