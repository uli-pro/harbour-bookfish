"""The package document (OPF): reading order, metadata, table of contents."""

import collections
import math

from .errors import EpubError
from .overlay import parse_clock
from .pages import PageTarget
from .paths import local_path, resolve
from .xmlutil import parse_xml

_CONTAINER = "{urn:oasis:names:tc:opendocument:xmlns:container}"
_OPF = "{http://www.idpf.org/2007/opf}"
_DC = "{http://purl.org/dc/elements/1.1/}"
_XHTML = "{http://www.w3.org/1999/xhtml}"
_EPUB = "{http://www.idpf.org/2007/ops}"
_NCX = "{http://www.daisy.org/z3986/2005/ncx/}"
_ENC = "{http://www.w3.org/2001/04/xmlenc#}"

# Embedded fonts may be obfuscated; anything else encrypted is DRM.
_FONT_OBFUSCATION = {"http://www.idpf.org/2008/embedding",
                     "http://ns.adobe.com/pdf/enc#RC"}

DEFAULT_ACTIVE_CLASS = "-epub-media-overlay-active"

# Far above real metadata, which goes to every library view and its cache:
# one title of 3 million characters made the cache too large to read.
MAX_META_LENGTH = 500
MAX_AUTHORS = 20

Book = collections.namedtuple(
    "Book", "identifier title authors language cover duration active_class "
            "spine toc pages")
# overlay is the path of the chapter's SMIL file, or None.
SpineItem = collections.namedtuple(
    "SpineItem", "path media_type overlay linear")
# path is None for headings without a link; level 0 is the top level.
TocEntry = collections.namedtuple("TocEntry", "title path fragment level")
# What the library shows. sort is the first author's sort name ("Wilde,
# Oscar"); series_index is a float or None; cover a path in the book or None;
# audio is true if a chapter has narration, by the same rule as read_package.
BookInfo = collections.namedtuple(
    "BookInfo", "identifier title authors sort series series_index cover audio")

_Item = collections.namedtuple("_Item", "path media_type properties overlay_id")


def package_path(container):
    """The path of the package document named in container.xml."""
    opf_path = None
    for rootfile in container.iter(_CONTAINER + "rootfile"):
        if rootfile.get("media-type") == "application/oebps-package+xml":
            opf_path = rootfile.get("full-path")
            break
    if not opf_path:
        raise EpubError("not_epub", "no package document")
    target = resolve("", opf_path)
    if not target:
        raise EpubError("bad_package", opf_path)
    return target[0]


def read_package(root):
    """Read the book unpacked at root."""
    try:
        container = parse_xml(local_path(root, "META-INF/container.xml"))
    except OSError:
        raise EpubError("not_epub", "no META-INF/container.xml")
    opf_path = package_path(container)
    _check_encryption(root)
    try:
        opf = parse_xml(local_path(root, opf_path))
    except OSError:
        raise EpubError("bad_package", "missing " + opf_path)

    manifest = _read_manifest(opf, opf_path)
    spine = _read_spine(opf, manifest)
    metadata = opf.find(_OPF + "metadata")
    if metadata is None:
        metadata = opf.makeelement(_OPF + "metadata", {})

    toc = []
    nav = next((i for i in manifest.values() if "nav" in i.properties), None)
    if nav is not None:
        try:
            toc = read_nav(root, nav.path)
        except (EpubError, OSError):
            pass
    if not toc:
        ncx = _ncx_item(opf, manifest)
        if ncx is not None:
            try:
                toc = read_ncx(root, ncx.path)
            except (EpubError, OSError):
                pass

    pages = []
    if nav is not None:
        try:
            pages = read_nav_pages(root, nav.path)
        except (EpubError, OSError):
            pass
    if not pages:
        ncx = _ncx_item(opf, manifest)
        if ncx is not None:
            try:
                pages = read_ncx_pages(root, ncx.path)
            except (EpubError, OSError):
                pass

    return Book(
        identifier=_short(_identifier(opf, metadata)),
        title=_short(_first_text(metadata, _DC + "title")),
        authors=[_short(name) for name in _authors(metadata)[:MAX_AUTHORS]],
        language=_short(_first_text(metadata, _DC + "language")),
        cover=_cover(metadata, manifest),
        duration=_duration(metadata),
        active_class=(_meta(metadata, "media:active-class")
                      or DEFAULT_ACTIVE_CLASS),
        spine=spine,
        toc=toc,
        pages=pages)


def read_info(opf, opf_path):
    """The library's view of the parsed package document opf."""
    metadata = opf.find(_OPF + "metadata")
    if metadata is None:
        metadata = opf.makeelement(_OPF + "metadata", {})
    creators = _creators(metadata)
    series, index = _series(metadata)
    manifest = _read_manifest(opf, opf_path)
    return BookInfo(
        identifier=_short(_identifier(opf, metadata)),
        title=_short(_first_text(metadata, _DC + "title")),
        authors=[_short(name) for name, _ in creators[:MAX_AUTHORS]],
        sort=_short(_sort_name(metadata, creators[0], len(creators))) if creators else "",
        series=_short(series),
        series_index=index,
        cover=_cover(metadata, manifest),
        audio=any(item.overlay for item in _read_spine(opf, manifest)))


def read_nav(root, nav_path):
    """Read the table of contents from the navigation document nav_path."""
    doc = parse_xml(local_path(root, nav_path))
    navs = list(doc.iter(_XHTML + "nav"))
    toc_navs = [n for n in navs if "toc" in n.get(_EPUB + "type", "").split()]
    navs = toc_navs or navs
    if not navs:
        return []
    top = navs[0].find(_XHTML + "ol")
    if top is None:
        return []
    entries = []
    # Iterative walk, so a hostile file cannot exhaust the recursion limit.
    stack = [(iter(top.findall(_XHTML + "li")), 0)]
    while stack:
        items, level = stack[-1]
        li = next(items, None)
        if li is None:
            stack.pop()
            continue
        label = li.find(_XHTML + "a")
        if label is None:
            label = li.find(_XHTML + "span")
        if label is not None:
            path, fragment = None, ""
            href = label.get("href")
            if href:
                target = resolve(nav_path, href)
                if target:
                    path, fragment = target
            entries.append(TocEntry(_text(label), path, fragment, level))
        sub = li.find(_XHTML + "ol")
        if sub is not None:
            stack.append((iter(sub.findall(_XHTML + "li")), level + 1))
    return entries


def read_ncx(root, ncx_path):
    """Read the table of contents from the EPUB 2 NCX file ncx_path."""
    doc = parse_xml(local_path(root, ncx_path))
    nav_map = doc.find(_NCX + "navMap")
    if nav_map is None:
        return []
    entries = []
    stack = [(iter(nav_map.findall(_NCX + "navPoint")), 0)]
    while stack:
        points, level = stack[-1]
        point = next(points, None)
        if point is None:
            stack.pop()
            continue
        label = point.find(_NCX + "navLabel/" + _NCX + "text")
        content = point.find(_NCX + "content")
        path, fragment = None, ""
        src = content.get("src") if content is not None else None
        if src:
            target = resolve(ncx_path, src)
            if target:
                path, fragment = target
        entries.append(TocEntry(_text(label) if label is not None else "",
                                path, fragment, level))
        stack.append((iter(point.findall(_NCX + "navPoint")), level + 1))
    return entries


def read_nav_pages(root, nav_path):
    """The page list (PageTarget) of the navigation document nav_path."""
    doc = parse_xml(local_path(root, nav_path))
    nav = next((n for n in doc.iter(_XHTML + "nav")
                if "page-list" in n.get(_EPUB + "type", "").split()), None)
    if nav is None:
        return []
    return _page_targets(nav_path, ((_text(a), a.get("href"))
                                    for a in nav.iter(_XHTML + "a")))


def read_ncx_pages(root, ncx_path):
    """The page list (PageTarget) of the EPUB 2 NCX file ncx_path."""
    doc = parse_xml(local_path(root, ncx_path))
    page_list = doc.find(_NCX + "pageList")
    if page_list is None:
        return []

    def entries():
        for target in page_list.iter(_NCX + "pageTarget"):
            label = target.find(_NCX + "navLabel/" + _NCX + "text")
            content = target.find(_NCX + "content")
            yield (_text(label) if label is not None else "",
                   content.get("src") if content is not None else None)
    return _page_targets(ncx_path, entries())


def _page_targets(referrer, entries):
    targets = []
    for name, href in entries:
        try:
            target = resolve(referrer, href) if href else None
        except EpubError:
            target = None
        if target:
            targets.append(PageTarget(target[0], target[1], name))
    return targets


def text_length(root, path):
    """Number of characters of text in the XHTML file path.

    Only used to estimate page numbers across the book, so an unreadable
    file counts as 0 instead of raising.
    """
    try:
        doc = parse_xml(local_path(root, path), html_entities=True)
    except (EpubError, OSError):
        return 0
    body = doc.find(_XHTML + "body")
    return len(_text(body if body is not None else doc))


def _check_encryption(root):
    try:
        doc = parse_xml(local_path(root, "META-INF/encryption.xml"))
    except OSError:
        return
    except EpubError:
        raise EpubError("drm", "unreadable encryption.xml")
    check_encryption(doc)


def check_encryption(doc):
    """Raise EpubError "drm" if the parsed META-INF/encryption.xml encrypts
    more than embedded fonts."""
    for data in doc.iter(_ENC + "EncryptedData"):
        method = data.find(_ENC + "EncryptionMethod")
        algorithm = method.get("Algorithm", "") if method is not None else ""
        if algorithm not in _FONT_OBFUSCATION:
            raise EpubError("drm", algorithm)


def _ncx_item(opf, manifest):
    spine = opf.find(_OPF + "spine")
    toc_id = spine.get("toc") if spine is not None else None
    if toc_id and toc_id in manifest:
        return manifest[toc_id]
    # Some books declare it as text/xml; the extension still tells.
    return next((i for i in manifest.values()
                 if i.media_type == "application/x-dtbncx+xml"
                 or i.path.lower().endswith(".ncx")), None)


def _read_manifest(opf, opf_path):
    manifest = {}
    for item in opf.iterfind(_OPF + "manifest/" + _OPF + "item"):
        item_id = item.get("id")
        href = item.get("href")
        if not item_id or not href:
            continue
        target = resolve(opf_path, href)
        if target is None:
            continue
        manifest[item_id] = _Item(
            target[0], item.get("media-type", ""),
            item.get("properties", "").split(), item.get("media-overlay"))
    return manifest


def _read_spine(opf, manifest):
    spine = []
    for ref in opf.iterfind(_OPF + "spine/" + _OPF + "itemref"):
        item = manifest.get(ref.get("idref"))
        if item is None:
            continue
        overlay = manifest.get(item.overlay_id) if item.overlay_id else None
        if overlay is not None and overlay.media_type != "application/smil+xml":
            overlay = None
        spine.append(SpineItem(item.path, item.media_type,
                               overlay.path if overlay else None,
                               ref.get("linear") != "no"))
    if not spine:
        raise EpubError("bad_package", "empty spine")
    return spine


def _identifier(opf, metadata):
    uid = opf.get("unique-identifier")
    identifiers = metadata.findall(_DC + "identifier")
    for identifier in identifiers:
        if uid and identifier.get("id") == uid:
            return _text(identifier)
    return _text(identifiers[0]) if identifiers else ""


def _authors(metadata):
    return [name for name, _ in _creators(metadata)]


def _creators(metadata):
    """(name, element) of the authors: creators without a role or with
    "aut"; translators, illustrators, publishers and narrators are not. A
    book naming none that way gets all but its narrators."""
    # EPUB 3 states roles in <meta refines="#id" property="role">,
    # EPUB 2 in an opf:role attribute.
    roles = _refinements(metadata, "role")
    authors, others = [], []
    for creator in metadata.iterfind(_DC + "creator"):
        role = roles.get(creator.get("id"), creator.get(_OPF + "role")) or "aut"
        name = _text(creator)
        if name and role == "aut":
            authors.append((name, creator))
        elif name and role != "nrt":
            others.append((name, creator))
    return authors or others


def _sort_name(metadata, creator, count):
    name, element = creator
    sort = (_refinements(metadata, "file-as").get(element.get("id"))
            or element.get(_OPF + "file-as") or "")
    # Calibre puts the sort names of all authors into the first one's:
    # "Child, Lee & Child, Andrew"; one part for each author.
    parts = sort.split(" & ")
    if count > 1 and len(parts) == count:
        sort = parts[0]
    sort = " ".join(sort.split())
    # Some books carry a placeholder although the author is known.
    if sort.casefold() in ("unbekannt", "unknown"):
        sort = ""
    return sort or name


def _series(metadata):
    """(name, index) of the series, from calibre's or EPUB 3's metadata."""
    name, index = "", None
    for meta in metadata.iterfind(_OPF + "meta"):
        if meta.get("name") == "calibre:series":
            name = " ".join(meta.get("content", "").split())
        elif meta.get("name") == "calibre:series_index":
            index = _number(meta.get("content"))
    if name:
        return name, index
    for meta in metadata.iterfind(_OPF + "meta"):
        if meta.get("property") == "belongs-to-collection" and not meta.get("refines"):
            details = {}
            if meta.get("id"):
                for prop in ("collection-type", "group-position"):
                    details[prop] = _refinements(metadata, prop).get(meta.get("id"), "")
            if details.get("collection-type", "") in ("", "series"):
                return _text(meta), _number(details.get("group-position"))
    return "", None


def _refinements(metadata, prop):
    """{id: text} of the <meta property=prop refines="#id"> elements."""
    found = {}
    for meta in metadata.iterfind(_OPF + "meta"):
        refines = meta.get("refines", "")
        if meta.get("property") == prop and refines.startswith("#"):
            found.setdefault(refines[1:], _text(meta))
    return found


def _number(text):
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _cover(metadata, manifest):
    # Only images: the EPUB 2 entry may name the cover page instead.
    for item in manifest.values():
        if "cover-image" in item.properties and _is_image(item):
            return item.path
    for meta in metadata.iterfind(_OPF + "meta"):
        if meta.get("name") == "cover":
            item = manifest.get(meta.get("content"))
            if item is not None and _is_image(item):
                return item.path
    return None


def _is_image(item):
    return item.media_type.startswith("image/")


def _duration(metadata):
    value = _meta(metadata, "media:duration")
    if not value:
        return None
    try:
        return parse_clock(value)
    except ValueError:
        return None


def _meta(metadata, prop):
    """Text of the first <meta property=prop> that refines nothing."""
    for meta in metadata.iterfind(_OPF + "meta"):
        if meta.get("property") == prop and not meta.get("refines"):
            return _text(meta)
    return ""


def _first_text(parent, tag):
    element = parent.find(tag)
    return _text(element) if element is not None else ""


def _short(text):
    return text[:MAX_META_LENGTH]


def _text(element):
    return " ".join("".join(element.itertext()).split())
