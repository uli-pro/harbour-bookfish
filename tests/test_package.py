from bookfish.errors import EpubError
from bookfish.package import (BookInfo, SpineItem, TocEntry, read_info, read_nav, read_ncx,
                               read_package, text_length)

from .helpers import MINI_DIR, TempDirTestCase, write_files

CONTAINER = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles>
    <rootfile full-path="OPS/package.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

OPF = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/"
         xmlns:opf="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata>{metadata}</metadata>
  <manifest>{manifest}</manifest>
  <spine>{spine}</spine>
</package>"""

CHAPTER = '<item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/>'


class MiniBookTest(TempDirTestCase):

    def test_metadata(self):
        book = read_package(MINI_DIR)
        self.assertEqual(book.identifier,
                         "urn:uuid:4f1c2a9e-6b0d-4d5e-9a57-3c8e2f7b1d60")
        self.assertEqual(book.title, "The Happy Prince")
        self.assertEqual(book.authors, ["Wilde, Oscar"])
        self.assertEqual(book.language, "en")
        self.assertEqual(book.cover, "OEBPS/cover.svg")
        self.assertEqual(book.duration, 39000)
        self.assertEqual(book.active_class, "-epub-media-overlay-active")

    def test_spine(self):
        self.assertEqual(read_package(MINI_DIR).spine, [
            SpineItem("OEBPS/title.xhtml", "application/xhtml+xml", None, True),
            SpineItem("OEBPS/chapter.xhtml", "application/xhtml+xml",
                      "OEBPS/MediaOverlays/chapter.smil", True),
        ])

    def test_toc(self):
        self.assertEqual(read_package(MINI_DIR).toc, [
            TocEntry("Title Page", "OEBPS/title.xhtml", "", 0),
            TocEntry("The Happy Prince.", "OEBPS/chapter.xhtml", "chap01", 0),
        ])


class PackageTest(TempDirTestCase):

    def book(self, metadata="", manifest=CHAPTER, spine='<itemref idref="c1"/>',
             files=None):
        content = {
            "META-INF/container.xml": CONTAINER,
            "OPS/package.opf": OPF.format(metadata=metadata, manifest=manifest,
                                          spine=spine),
        }
        content.update(files or {})
        write_files(self.tmp, content)
        return read_package(self.tmp)

    def assertFails(self, code, **kwargs):
        with self.assertRaises(EpubError) as cm:
            self.book(**kwargs)
        self.assertEqual(cm.exception.code, code)

    def test_minimal(self):
        book = self.book()
        self.assertEqual(book.title, "")
        self.assertEqual(book.authors, [])
        self.assertIsNone(book.cover)
        self.assertIsNone(book.duration)
        self.assertEqual(book.active_class, "-epub-media-overlay-active")
        self.assertEqual(book.toc, [])
        self.assertEqual(book.spine, [
            SpineItem("OPS/c1.xhtml", "application/xhtml+xml", None, True)])

    def test_missing_container(self):
        with self.assertRaises(EpubError) as cm:
            read_package(self.tmp)
        self.assertEqual(cm.exception.code, "not_epub")

    def test_container_without_rootfile(self):
        write_files(self.tmp, {"META-INF/container.xml": "<container/>"})
        with self.assertRaises(EpubError) as cm:
            read_package(self.tmp)
        self.assertEqual(cm.exception.code, "not_epub")

    def test_missing_package(self):
        write_files(self.tmp, {"META-INF/container.xml": CONTAINER})
        with self.assertRaises(EpubError) as cm:
            read_package(self.tmp)
        self.assertEqual(cm.exception.code, "bad_package")

    def test_href_leaving_book(self):
        self.assertFails("unsafe_path", manifest=(
            '<item id="c1" href="../../etc/passwd" media-type="text/plain"/>'))

    def test_percent_encoding(self):
        book = self.book(manifest=(
            '<item id="c1" href="Text/chapter%201.xhtml" '
            'media-type="application/xhtml+xml"/>'))
        self.assertEqual(book.spine[0].path, "OPS/Text/chapter 1.xhtml")

    def test_external_item_ignored(self):
        book = self.book(
            manifest=CHAPTER + '<item id="web" href="https://example.com/x.xhtml" '
                               'media-type="application/xhtml+xml"/>',
            spine='<itemref idref="web"/><itemref idref="c1"/>')
        self.assertEqual([item.path for item in book.spine], ["OPS/c1.xhtml"])

    def test_malformed_url_ignored(self):
        book = self.book(
            manifest=CHAPTER + '<item id="bad" href="//[x" media-type="text/css"/>')
        self.assertEqual(len(book.spine), 1)

    def test_unknown_idref_skipped(self):
        book = self.book(spine='<itemref idref="nope"/><itemref idref="c1"/>')
        self.assertEqual(len(book.spine), 1)

    def test_empty_spine(self):
        self.assertFails("bad_package", spine="")

    def test_linear_and_overlay(self):
        book = self.book(
            manifest=(
                '<item id="c1" href="c1.xhtml" media-type="application/xhtml+xml" '
                'media-overlay="s1"/>'
                '<item id="c2" href="c2.xhtml" media-type="application/xhtml+xml" '
                'media-overlay="css"/>'
                '<item id="s1" href="mo/c1.smil" media-type="application/smil+xml"/>'
                '<item id="css" href="style.css" media-type="text/css"/>'),
            spine='<itemref idref="c1"/><itemref idref="c2" linear="no"/>')
        self.assertEqual(book.spine[0].overlay, "OPS/mo/c1.smil")
        self.assertTrue(book.spine[0].linear)
        self.assertIsNone(book.spine[1].overlay)
        self.assertFalse(book.spine[1].linear)

    def test_identifier(self):
        book = self.book(metadata=(
            '<dc:identifier>first</dc:identifier>'
            '<dc:identifier id="uid">unique</dc:identifier>'))
        self.assertEqual(book.identifier, "unique")

    def test_epub2_metadata(self):
        book = self.book(
            metadata=(
                '<dc:creator opf:role="aut">Ann Author</dc:creator>'
                '<dc:creator opf:role="nrt">Ned Narrator</dc:creator>'
                '<dc:creator>Una Unknown</dc:creator>'
                '<meta name="cover" content="img"/>'),
            manifest=CHAPTER + '<item id="img" href="cover.jpg" media-type="image/jpeg"/>')
        self.assertEqual(book.authors, ["Ann Author", "Una Unknown"])
        self.assertEqual(book.cover, "OPS/cover.jpg")

    def test_cover_must_be_image(self):
        book = self.book(
            metadata='<meta name="cover" content="page"/>',
            manifest=CHAPTER + '<item id="page" href="cover.xhtml" media-type="application/xhtml+xml"/>')
        self.assertIsNone(book.cover)

    def test_bad_duration_ignored(self):
        book = self.book(metadata='<meta property="media:duration">soon</meta>')
        self.assertIsNone(book.duration)

    def test_broken_nav_gives_empty_toc(self):
        book = self.book(
            manifest=CHAPTER + '<item id="nav" href="nav.xhtml" '
                               'media-type="application/xhtml+xml" properties="nav"/>',
            files={"OPS/nav.xhtml": "<html><nav>"})
        self.assertEqual(book.toc, [])


NAV = """<?xml version="1.0"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<body>
  <nav epub:type="landmarks"><ol><li><a href="x.xhtml">Landmark</a></li></ol></nav>
  <nav epub:type="toc">
    <ol>
      <li><span>Part   One</span>
        <ol>
          <li><a href="Text/c1.xhtml#start">Chapter <b>1</b></a></li>
          <li><a href="Text/c2.xhtml">Chapter 2</a>
            <ol><li><a href="#note">Note</a></li></ol>
          </li>
        </ol>
      </li>
      <li><a href="Text/end.xhtml">The End</a></li>
    </ol>
  </nav>
</body>
</html>"""


NCX = """<?xml version="1.0"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <navMap>
    <navPoint id="p1" playOrder="1">
      <navLabel><text>Part One</text></navLabel>
      <content src="Text/part1.xhtml"/>
      <navPoint id="p2" playOrder="2">
        <navLabel><text> Chapter
          1 </text></navLabel>
        <content src="Text/c1.xhtml#start"/>
      </navPoint>
    </navPoint>
    <navPoint id="p3" playOrder="3">
      <navLabel><text>No link</text></navLabel>
    </navPoint>
  </navMap>
</ncx>"""

ENCRYPTION = """<?xml version="1.0"?>
<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container"
            xmlns:enc="http://www.w3.org/2001/04/xmlenc#">
  <enc:EncryptedData>
    <enc:EncryptionMethod Algorithm="{}"/>
    <enc:CipherData><enc:CipherReference URI="OPS/{}"/></enc:CipherData>
  </enc:EncryptedData>
</encryption>"""


class NcxTest(TempDirTestCase):

    book = PackageTest.book
    assertFails = PackageTest.assertFails

    def test_nested(self):
        write_files(self.tmp, {"OPS/toc.ncx": NCX})
        self.assertEqual(read_ncx(self.tmp, "OPS/toc.ncx"), [
            TocEntry("Part One", "OPS/Text/part1.xhtml", "", 0),
            TocEntry("Chapter 1", "OPS/Text/c1.xhtml", "start", 1),
            TocEntry("No link", None, "", 0),
        ])

    def test_deep_nesting(self):
        depth = 5000
        points = ("<navPoint><navLabel><text>x</text></navLabel><content src='a.xhtml'/>" * depth
                  + "</navPoint>" * depth)
        write_files(self.tmp, {"toc.ncx": (
            '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap>' + points
            + "</navMap></ncx>")})
        entries = read_ncx(self.tmp, "toc.ncx")
        self.assertEqual(len(entries), depth)
        self.assertEqual(entries[-1].level, depth - 1)

    def test_package_uses_spine_toc(self):
        book = self.book(
            manifest=CHAPTER + '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
            spine='<itemref idref="c1"/>', files={"OPS/toc.ncx": NCX})
        self.assertEqual(len(book.toc), 3)

    def test_package_finds_ncx_by_media_type(self):
        book = self.book(
            manifest=CHAPTER + '<item id="n" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
            files={"OPS/toc.ncx": NCX})
        self.assertEqual(book.toc[0], TocEntry("Part One", "OPS/Text/part1.xhtml", "", 0))

    def test_package_finds_ncx_by_extension(self):
        book = self.book(
            manifest=CHAPTER + '<item id="n" href="toc.ncx" media-type="text/xml"/>',
            files={"OPS/toc.ncx": NCX})
        self.assertEqual(len(book.toc), 3)

    def test_nav_wins_over_ncx(self):
        book = self.book(
            manifest=CHAPTER + '<item id="nav" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/>'
                     '<item id="n" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
            files={"OPS/toc.ncx": NCX, "OPS/nav.xhtml": NAV})
        self.assertEqual(book.toc[0].title, "Part One")
        self.assertIsNone(book.toc[0].path)  # from the nav, where Part One has no link

    def test_broken_ncx_gives_no_toc(self):
        outside = NCX.replace("Text/part1.xhtml", "../../outside.xhtml")
        for ncx in ("<ncx", outside):
            book = self.book(
                manifest=CHAPTER + '<item id="n" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
                files={"OPS/toc.ncx": ncx})
            self.assertEqual(book.toc, [])


class EncryptionTest(TempDirTestCase):

    book = PackageTest.book
    assertFails = PackageTest.assertFails

    def test_obfuscated_fonts_are_fine(self):
        for algorithm in ("http://www.idpf.org/2008/embedding", "http://ns.adobe.com/pdf/enc#RC"):
            book = self.book(files={"META-INF/encryption.xml": ENCRYPTION.format(algorithm, "font.otf")})
            self.assertEqual(len(book.spine), 1)

    def test_encrypted_content_is_drm(self):
        self.assertFails("drm", files={"META-INF/encryption.xml": ENCRYPTION.format(
            "http://www.w3.org/2001/04/xmlenc#aes128-cbc", "c1.xhtml")})

    def test_unreadable_encryption_is_drm(self):
        self.assertFails("drm", files={"META-INF/encryption.xml": "<encryption"})


class NavTest(TempDirTestCase):

    def test_nested(self):
        write_files(self.tmp, {"OPS/nav.xhtml": NAV})
        self.assertEqual(read_nav(self.tmp, "OPS/nav.xhtml"), [
            TocEntry("Part One", None, "", 0),
            TocEntry("Chapter 1", "OPS/Text/c1.xhtml", "start", 1),
            TocEntry("Chapter 2", "OPS/Text/c2.xhtml", "", 1),
            TocEntry("Note", "OPS/nav.xhtml", "note", 2),
            TocEntry("The End", "OPS/Text/end.xhtml", "", 0),
        ])

    def test_deep_nesting(self):
        depth = 5000
        body = "<ol><li><a href='a.xhtml'>x</a>" * depth + "</li></ol>" * depth
        write_files(self.tmp, {"nav.xhtml": (
            '<html xmlns="http://www.w3.org/1999/xhtml"><body><nav>'
            + body + "</nav></body></html>")})
        entries = read_nav(self.tmp, "nav.xhtml")
        self.assertEqual(len(entries), depth)
        self.assertEqual(entries[-1].level, depth - 1)


class TextLengthTest(TempDirTestCase):

    def test_counts_body_text_with_collapsed_whitespace(self):
        write_files(self.tmp, {"c.xhtml": (
            '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Not counted</title></head>'
            '<body><p>Two  words</p>\n<p><span>and</span> more</p></body></html>')})
        self.assertEqual(text_length(self.tmp, "c.xhtml"), len("Two words and more"))

    def test_unreadable_files_count_zero(self):
        write_files(self.tmp, {"bad.xhtml": "<html"})
        self.assertEqual(text_length(self.tmp, "bad.xhtml"), 0)
        self.assertEqual(text_length(self.tmp, "missing.xhtml"), 0)

    def test_without_xhtml_body_counts_whole_document(self):
        write_files(self.tmp, {"c.svg": '<svg xmlns="http://www.w3.org/2000/svg"><text>Hi there</text></svg>'})
        self.assertEqual(text_length(self.tmp, "c.svg"), len("Hi there"))

    def test_forbidden_or_oversized_count_zero(self):
        write_files(self.tmp, {
            "dtd.xhtml": '<!DOCTYPE html [<!ENTITY a "x">]><html xmlns="http://www.w3.org/1999/xhtml"><body>&a;</body></html>',
            "big.xhtml": '<html xmlns="http://www.w3.org/1999/xhtml"><body>' + "x" * (10 * 1024 * 1024) + '</body></html>'})
        self.assertEqual(text_length(self.tmp, "dtd.xhtml"), 0)
        self.assertEqual(text_length(self.tmp, "big.xhtml"), 0)

    def test_named_html_characters(self):
        write_files(self.tmp, {"c.xhtml": (
            '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">'
            '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>a&nbsp;b &uuml; &amp;</p></body></html>')})
        self.assertEqual(text_length(self.tmp, "c.xhtml"), len("a\u00a0b \u00fc &"))

    def test_unknown_named_character_counts_zero(self):
        write_files(self.tmp, {"c.xhtml": '<html xmlns="http://www.w3.org/1999/xhtml"><body>&bogus;</body></html>'})
        self.assertEqual(text_length(self.tmp, "c.xhtml"), 0)

    def test_mini_chapter(self):
        self.assertGreater(text_length(MINI_DIR, "OEBPS/chapter.xhtml"), 100)


class InfoTest(TempDirTestCase):

    def info(self, metadata="", manifest=CHAPTER):
        from xml.etree import ElementTree
        opf = ElementTree.fromstring(OPF.format(metadata=metadata, manifest=manifest,
                                                spine='<itemref idref="c1"/>'))
        return read_info(opf, "OPS/package.opf")

    def test_epub2(self):
        info = self.info(
            '<dc:identifier id="uid">urn:uuid:1</dc:identifier><dc:title>Shogun</dc:title>'
            '<dc:creator opf:role="nrt">Ned Narrator</dc:creator>'
            '<dc:creator opf:role="aut" opf:file-as="Clavell, James">James Clavell</dc:creator>'
            '<meta name="calibre:series" content="The Asian Saga"/>'
            '<meta name="calibre:series_index" content="1.0"/>'
            '<meta name="cover" content="img"/>',
            CHAPTER + '<item id="img" href="cover.jpg" media-type="image/jpeg"/>')
        self.assertEqual(info, BookInfo("urn:uuid:1", "Shogun", ["James Clavell"], "Clavell, James",
                                        "The Asian Saga", 1.0, "OPS/cover.jpg", False))

    def test_epub3(self):
        info = self.info(
            '<dc:creator id="a">Oscar Wilde</dc:creator>'
            '<meta refines="#a" property="file-as">Wilde, Oscar</meta>'
            '<meta property="belongs-to-collection" id="c">Fairy Tales</meta>'
            '<meta refines="#c" property="collection-type">series</meta>'
            '<meta refines="#c" property="group-position">2</meta>')
        self.assertEqual((info.sort, info.series, info.series_index), ("Wilde, Oscar", "Fairy Tales", 2.0))

    def test_sort_name_of_several_authors(self):
        info = self.info(
            '<dc:creator opf:file-as="Child, Lee &amp; Child, Andrew">Lee Child</dc:creator>'
            '<dc:creator opf:file-as="Child, Andrew">Andrew Child</dc:creator>')
        self.assertEqual(info.sort, "Child, Lee")
        info = self.info('<dc:creator opf:file-as="Höcker, Anna &amp; Rist, Fred">Anna Höcker &amp; Fred Rist</dc:creator>')
        self.assertEqual(info.sort, "Höcker, Anna & Rist, Fred")
        # A duo as one author, and a translator: not split.
        info = self.info('<dc:creator opf:file-as="Preston &amp; Child">Preston &amp; Child</dc:creator>'
                         '<dc:creator opf:role="trl">T. Ranslator</dc:creator>')
        self.assertEqual((info.sort, info.authors), ("Preston & Child", ["Preston & Child"]))

    def test_only_authors(self):
        info = self.info('<dc:creator opf:role="aut">Arthur Conan Doyle</dc:creator>'
                         '<dc:creator opf:role="trl">Eve Fritsche</dc:creator>'
                         '<dc:creator opf:role="ill">Sidney Paget</dc:creator>'
                         '<dc:creator opf:role="pbl">Verlag</dc:creator>'
                         '<dc:creator opf:role="nrt">Ned Narrator</dc:creator>')
        self.assertEqual(info.authors, ["Arthur Conan Doyle"])
        self.assertEqual(self.info('<dc:creator opf:role="edt">Ed Itor</dc:creator>').authors, ["Ed Itor"])

    def test_placeholder_sort_name(self):
        info = self.info('<dc:creator opf:file-as="Unbekannt">Jussi Adler-Olsen</dc:creator>')
        self.assertEqual(info.sort, "Jussi Adler-Olsen")

    def test_sort_falls_back_to_name(self):
        self.assertEqual(self.info('<dc:creator>Ann Author</dc:creator>').sort, "Ann Author")
        self.assertEqual(self.info().sort, "")

    def test_series_without_or_with_bad_index(self):
        info = self.info('<meta name="calibre:series" content="S"/><meta name="calibre:series_index" content="x"/>')
        self.assertEqual((info.series, info.series_index), ("S", None))
        info = self.info('<meta name="calibre:series" content="S"/><meta name="calibre:series_index" content="nan"/>')
        self.assertIsNone(info.series_index)

    def test_collection_that_is_no_series(self):
        info = self.info(
            '<meta property="belongs-to-collection" id="c">Classics</meta>'
            '<meta refines="#c" property="collection-type">set</meta>')
        self.assertEqual(info.series, "")
