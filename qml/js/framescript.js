// Runs in the browser part of the WebView, not in the page. Page scripts are
// disabled, so this is the only code that touches a book; QML talks to it
// through messages only.

var state = null

// Second line of defence besides the app-wide setting, and for this view
// only: no page scripts, no <meta http-equiv="refresh"> leaving the chapter,
// no embedded frames. Each in its own try, should Gecko drop one of them.
try { docShell.allowJavascript = false } catch (e) { }
try { docShell.allowMetaRedirects = false } catch (e) { }
try { docShell.allowSubframes = false } catch (e) { }

function current() {
    return state && state.doc === content.document ? state : null
}

addEventListener("DOMContentLoaded", function (event) {
    var doc = content.document
    if (event.target !== doc)
        return
    // Without a viewport the page is laid out 980 px wide, like on a desktop;
    // a book's own viewport would break the page width just the same.
    var viewport = doc.querySelector("meta[name=viewport]")
    if (!viewport) {
        viewport = doc.createElement("meta")
        viewport.name = "viewport"
        ;(doc.head || doc.documentElement).appendChild(viewport)
    }
    viewport.content = "width=device-width, initial-scale=1"
    // The WebView gets no touches; this only guards against links leaving
    // the chapter should that ever change.
    doc.addEventListener("click", function (e) { e.preventDefault() }, true)
}, true)

// The view's new size reaches Gecko up to a second after Qt's (turning
// the phone), passing other sizes on the way; QML lays out once it has
// the right one.
addEventListener("resize", function (event) {
    // Only the window sends it.
    if (content)
        sendAsyncMessage("bookfish:resized", { width: content.innerWidth, height: content.innerHeight })
}, true)

// Wait for "load", not DOMContentLoaded: images change the number of pages.
addEventListener("load", function (event) {
    if (event.target === content.document)
        sendAsyncMessage("bookfish:loaded", { url: content.document.URL })
}, true)

addMessageListener("bookfish:layout", function (message) {
    var o = message.data
    var doc = content.document
    var width = content.innerWidth
    var margin = o.margin
    var target = o.target
    var columns = o.columns > 1 ? 2 : 1
    // Laid out again (new text size, controls moved): replace our style and
    // show the page with the character in the middle of the page shown now.
    // Wherever the reader is on the page, the text moves by half a page at
    // most, and laying out again and again does not drift: the first
    // character, or the sentence at the top (led back to where it began),
    // took the place a little further back each time. Without text in the
    // middle (a picture) the first character counts, else that sentence.
    var style = current() ? state.style : null
    if (style && target.keep) {
        var page = currentPage()
        var offset = middleOffset(page, margin)
        if (offset < 0)
            offset = firstOffsetOn(page)
        target = offset >= 0 ? { offset: offset, fraction: target.fraction }
                             : { id: firstSentenceOn(page), fraction: target.fraction }
    }
    if (!style) {
        style = doc.createElement("style")
        ;(doc.head || doc.documentElement).appendChild(style)
    }
    // QML gives the text size and the bar in screen pixels, CSS counts
    // device-independent ones. The bar is 0 while the controls sit above
    // the text.
    var dpr = content.devicePixelRatio || 1
    var fontSize = o.fontSize / dpr
    var marginBottom = o.marginBottom + o.barHeight / dpr
    // Everything is !important: the book's CSS must neither break the pages
    // nor override the basic settings. Pages are CSS columns of one screen width
    // each: a column of width - 2 * margin plus a gap of 2 * margin, so every
    // page starts exactly one screen width further right.
    // Our font rules apply to XHTML elements only (h|*): MathML and SVG keep
    // theirs. The namespace rule must come first and takes no !important.
    style.textContent = "@namespace h url(" + xhtml + ");" +
        "@namespace m url(http://www.w3.org/1998/Math/MathML);" +
        // Formulas keep a math font, if Gecko has one (not important: a
        // book's own math font wins).
        "body m|math { font-family: math; }" + important(
        // On html too: sizes in rem refer to it.
        "html { height: 100%; margin: 0; padding: 0; overflow: hidden; background: " + o.background + ";" +
        "  font-size: " + fontSize + "px; }" +
        "html body { margin: 0; height: 100vh; box-sizing: border-box; overflow: hidden;" +
        "  padding: " + o.marginTop + "px " + margin + "px " + marginBottom + "px;" +
        columnRule(width, margin, columns) +
        "  color: " + o.color + "; background: " + o.background + ";" +
        "  font-size: " + fontSize + "px; line-height: " + o.lineHeight + ";" +
        "  overflow-wrap: break-word; }" +
        // Like the basic settings of FBReader: font size and line spacing
        // come from the app, relative sizes, indents and spacing of the
        // book build on them. A unitless line height scales with each font.
        "body * { line-height: inherit; }" +
        // The app's font, not the book's; code stays monospaced. The book's
        // own fonts follow the app's, for characters it lacks (Greek, Hebrew).
        "body, body h|* { font-family: " + o.fontFamily + bookFonts(doc) + "; }" +
        "body h|pre, body h|pre h|*, body h|code, body h|code h|*, body h|kbd, body h|kbd h|*," +
        "  body h|samp, body h|samp h|*, body h|tt, body h|tt h|* { font-family: monospace; }" +
        "body img, body svg { display: block; margin: 0 auto; max-width: 100%; max-height: 70vh;" +
        "  break-inside: avoid; }" +
        "body a, body a:link, body a:visited { color: inherit; text-decoration: none; }" +
        // Books are made for white pages: their own black text or light
        // backgrounds would be unreadable on a black one. A rule may be drawn
        // with its background.
        (o.background === "black" ? "body h|*:not(h|hr) { color: inherit; background-color: transparent; }" : "") +
        // Links into the book can be followed by a long press: coloured, not
        // underlined. Links out of it lead nowhere (no network) and look
        // like the text around them.
        "body h|a[href], body h|a[href] h|* { color: " +
        (o.background === "black" ? "#8ab4f8" : "#0645ad") + "; }" +
        outLinks.map(function (scheme) {
            var a = "body h|a[href^=\"" + scheme + "\" i]"
            return a + ", " + a + " h|*"
        }).join(", ") + " { color: inherit; }" +
        // Our own mark for the sentence spoken, and for the one heard last
        // where listening goes on: the book's style for its active class is
        // made for white pages.
        "body .bookfish-active, body .bookfish-resume { background-color: " + o.markColor + "; }" +
        // Bookmarks and notes: a dotted line, which changes no line's height.
        "body .bookfish-mark { text-decoration: underline dotted " + o.underlineColor + ";" +
        "  text-decoration-thickness: 0.1em; text-underline-offset: 0.2em; }" +
        // The first cell and the caption of each table in the colour of
        // links: a long press on them opens the table as the book made it.
        "body .bookfish-table-link, body .bookfish-table-link h|* { color: " +
        (o.background === "black" ? "#8ab4f8" : "#0645ad") + "; }" +
        // A table drawn for the picture view (drawTable), outside the body
        // and its columns: the body's rules again.
        ".bookfish-table-render { position: absolute; left: 0; top: 0; z-index: 2147483647; margin: 0;" +
        "  padding: 0.5em; box-sizing: content-box; overflow: visible; display: block; float: none;" +
        "  min-width: 0; max-width: none; min-height: 0; max-height: none; border: 0; transform: none;" +
        "  text-indent: 0; columns: auto; overflow-wrap: normal; word-break: normal; color: " + o.color + "; background: " +
        o.background + "; font-size: " + fontSize + "px; line-height: " + o.lineHeight + "; }" +
        ".bookfish-table-render h|* { line-height: inherit; font-family: " + o.fontFamily + bookFonts(doc) + "; }" +
        ".bookfish-table-render h|pre, .bookfish-table-render h|pre h|*, .bookfish-table-render h|code," +
        "  .bookfish-table-render h|code h|*, .bookfish-table-render h|kbd, .bookfish-table-render h|kbd h|*," +
        "  .bookfish-table-render h|samp, .bookfish-table-render h|samp h|*, .bookfish-table-render h|tt," +
        "  .bookfish-table-render h|tt h|* { font-family: monospace; }" +
        ".bookfish-table-render > h|table { width: auto; min-width: 0; max-width: none; margin: 0; }" +
        ".bookfish-table-render h|a { color: inherit; text-decoration: none; }" +
        (o.background === "black" ? ".bookfish-table-render h|*:not(h|hr) { color: inherit; background-color: transparent; }" : ""))
    // innerWidth is rounded (469 for 468.9): far into a long chapter the
    // small difference would put a box on the wrong page, and with two
    // columns a width too large leaves room for one only.
    var real = doc.body ? doc.body.getBoundingClientRect().width : width
    if (real > 0 && Math.abs(real - width) > 0.001) {
        style.textContent = style.textContent.replace(important(columnRule(width, margin, columns)),
                                                      important(columnRule(real, margin, columns)))
        width = real
    }
    normalize(doc, o)

    var sentences = []
    var isSentence = {}
    for (var i = 0; i < o.ids.length; ++i) {
        // Python does not check that the ids exist in the page.
        var el = doc.getElementById(o.ids[i])
        if (el) {
            sentences.push(el)
            isSentence[o.ids[i]] = true
        }
    }
    // Not kept: the reader's selection ends with a new layout.
    if (current() && state.selection) {
        try {
            content.getSelection().removeAllRanges()
        } catch (e) { }
    }
    var active = current() ? state.active : null
    var resume = current() ? state.resume : null
    var found = current() ? state.found : null
    if (resume)
        resume.classList.remove("bookfish-resume")
    resume = o.resume ? doc.getElementById(o.resume) : null
    if (resume)
        resume.classList.add("bookfish-resume")
    state = {
        serial: o.serial,
        doc: doc,
        style: style,
        // The body scrolls, not the root element: Sailfish's Gecko stops
        // scrolling the root four screen widths before its end.
        scroller: doc.body || doc.documentElement,
        // A screen's width: two columns in landscape if chosen.
        width: width,
        columns: columns,
        margin: margin,
        // The view's size this layout was made for, in CSS pixels.
        viewWidth: content.innerWidth,
        viewHeight: content.innerHeight,
        // The WebView enlarges text by itself (measured: 1.6); the settings
        // page shows its sample at the size the reader sees. A page Gecko
        // could not parse has no body.
        textScale: doc.body ? parseFloat(content.getComputedStyle(doc.body).fontSize) / fontSize : 0,
        sentences: sentences,
        isSentence: isSentence,
        active: active,
        resume: resume,
        // The text found, kept to select it again (see remark): offsets in
        // body.textContent, which stay when bookmarks' spans move text nodes
        // around (a Range would not).
        found: found,
        // See select().
        selection: null,
        // See applyMarks().
        marks: [],
        // See textNodes().
        texts: null,
        // Ids where the printed pages begin, "" for the chapter's start;
        // see pageMarkAt().
        pageMarks: o.pageMarks || [],
        pageMarkOffsets: null
    }
    applyMarks(o.marks || [])
    evenColumns(doc)
    go(target)
    remark()
    if (o.highlight) {
        highlight(o.highlight)
    } else if (state.active) {
        // Playback has stopped.
        state.active.classList.remove("bookfish-active")
        state.active = null
    }
    awaitPaint(o.serial)
})

// The sentence spoken: marked, its page shown. A sentence running onto
// further pages reports them with the share of its text before each, so
// QML can turn the page while the sentence is spoken.
function highlight(id) {
    var el = state.doc.getElementById(id)
    if (state.active && state.active !== el)
        state.active.classList.remove("bookfish-active")
    state.active = el
    var splits = []
    if (el) {
        el.classList.add("bookfish-active")
        var rects = boxes(el)
        var total = 0
        for (var i = 0; i < rects.length; ++i)
            total += rects[i].width
        var first = rects.length ? pageOfBox(rects[0]) : pageOf(el)
        var before = 0
        var page = first
        for (var j = 0; j < rects.length; ++j) {
            var p = pageOfBox(rects[j])
            if (p > page && total > 0) {
                splits.push({ page: p, share: before / total })
                page = p
            }
            before += rects[j].width
        }
        // The page stays while the reader has text selected.
        if (first !== currentPage() && !state.selection)
            showPage(first)
    }
    sendAsyncMessage("bookfish:highlighted", { serial: state.serial, id: id, splits: splits })
}

addMessageListener("bookfish:highlight", function (message) {
    if (current())
        highlight(message.data.id)
})

addMessageListener("bookfish:show", function (message) {
    if (current() && !state.selection && message.data.page !== currentPage())
        showPage(message.data.page)
})

// A tap, given as a share of the view's width and height: the sentence
// there, "" if none.
// Not named like the answer: the WebView hands a frame script's own
// messages back to its listeners, which made the answer ask again.
addMessageListener("bookfish:hitTest", function (message) {
    if (!current())
        return
    var el = state.doc.elementFromPoint(message.data.x * content.innerWidth,
                                        message.data.y * content.innerHeight)
    while (el && !(el.id && state.isSentence[el.id]))
        el = el.parentElement
    sendAsyncMessage("bookfish:hit", { serial: state.serial, id: el ? el.id : "" })
})

// Links into the book have an address without a scheme ("notes.xhtml#n1",
// "#fn:1"), as Python's paths.resolve sees them. CSS cannot test that, so
// the colour rule leaves out the schemes books use.
var outLinks = ["http:", "https:", "mailto:", "ftp:", "tel:", "data:", "javascript:", "file:", "urn:"]

function isBookLink(element) {
    var href = element.getAttribute("href")
    return element.namespaceURI === xhtml && href !== null && !/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(href)
}

// A long press, given like a tap: a big picture there; else a link right
// under the finger; else the word there, selected; else, between words or
// beside the text, the link nearest to the finger: notes' numbers are
// small, the finger often lands beside them. Python decides what a link
// does (notes.py).
addMessageListener("bookfish:pressAt", function (message) {
    if (!current())
        return
    var x = message.data.x * content.innerWidth
    var y = message.data.y * content.innerHeight
    var table = tableLinkAt(x, y)
    if (table >= 0) {
        var answer = { serial: state.serial }
        try {
            answer.tableImage = drawTable(table)
        } catch (e) {
            answer.tableError = String(e)
        }
        sendAsyncMessage("bookfish:pressed", answer)
        return
    }
    var src = pictureAt(x, y)
    var link = null
    var answer = { serial: state.serial, picture: src }
    if (!src) {
        link = linkUnder(x, y)
        var c = link ? -1 : charAtPoint(x, y)
        var texts = textNodes()
        if (c >= 0) {
            var under = linkOf(texts.nodes[nodeIndex(texts, c)])
            if (under && isBookLink(under))
                link = under
            else if (isWordChar(texts.all, c))
                answer.selection = select(wordStart(texts, c), wordEnd(texts, c))
        }
        if (!link && !answer.selection)
            link = linkAt(x, y)
    }
    if (link) {
        var href = link.getAttribute("href")
        var same = state.doc.getElementsByTagNameNS(xhtml, "a")
        var ordinal = 0
        for (var i = 0; i < same.length && same[i] !== link; ++i) {
            if (same[i].getAttribute("href") === href)
                ++ordinal
        }
        answer.href = href
        answer.ordinal = ordinal
    }
    sendAsyncMessage("bookfish:pressed", answer)
})

function linkUnder(x, y) {
    var el = state.doc.elementFromPoint(x, y)
    var link = el && el.closest ? el.closest("a[href]") : null
    return link && isBookLink(link) ? link : null
}

// The link a text node is in, null if none.
function linkOf(node) {
    return node.parentElement ? node.parentElement.closest("a[href]") : null
}

// Text selected by a long press: offsets in body.textContent (see
// findRange), start included, end not; null if none. The reader moves its
// ends by whole words, or by letters back into the word an end lies in, on
// the page shown only.

// Letters, digits and their marks make words; an apostrophe or a hyphen
// between two of them belongs to the word ("don't", "Know-how"), and so
// does a soft hyphen; a point, comma or colon between digits too ("3,6",
// "1.000", "12:30").
var wordLetter = /[\p{L}\p{N}\p{M}]/u
var wordJoiner = /['\u2019\u2010\u2011\u00ad-]/
var digit = /\p{N}/u
var numberJoiner = /[.,:]/

function isWordChar(all, i) {
    if (i < 0 || i >= all.length)
        return false
    if (wordLetter.test(all[i]))
        return true
    if (i === 0 || i + 1 >= all.length)
        return false
    if (wordJoiner.test(all[i]))
        return wordLetter.test(all[i - 1]) && wordLetter.test(all[i + 1])
    return numberJoiner.test(all[i]) && digit.test(all[i - 1]) && digit.test(all[i + 1])
}

// The index of the text node holding offset: the last one starting at or
// before it.
function nodeIndex(texts, offset) {
    var lo = 0
    var hi = texts.starts.length
    while (hi - lo > 1) {
        var mid = (lo + hi) >> 1
        if (texts.starts[mid] <= offset)
            lo = mid
        else
            hi = mid
    }
    return lo
}

// The paragraph or other block a node is in. Floated elements count as
// inline: drop capitals float ("<span>T</span>he").
function blockOf(node) {
    for (var el = node.parentElement; el; el = el.parentElement) {
        var style = content.getComputedStyle(el)
        if (!style)
            continue
        if (!/^inline|^contents$|^ruby/.test(style.display) && style.cssFloat === "none")
            return el
    }
    return null
}

// Whether the characters at i and i + 1 may belong to one word, as far as
// their nodes go: within one node, or in neighbours of the same paragraph
// and the same link. A note's number after a word ("king<a>12</a>") is no
// part of it, nor is the first word of a paragraph that follows a heading
// without a space between them in the book.
function sameWord(texts, i) {
    var a = nodeIndex(texts, i)
    var b = nodeIndex(texts, i + 1)
    if (a === b)
        return true
    // A line break or a picture between them ("blue<br/>Sugar").
    for (var k = a + 1; k <= b; ++k) {
        if (texts.breaks[k])
            return false
    }
    return blockOf(texts.nodes[a]) === blockOf(texts.nodes[b])
           && linkOf(texts.nodes[a]) === linkOf(texts.nodes[b])
}

// Where the word holding the character at c begins and ends.
function wordStart(texts, c) {
    var s = c
    while (s > 0 && isWordChar(texts.all, s - 1) && sameWord(texts, s - 1))
        --s
    return s
}

function wordEnd(texts, c) {
    var e = c + 1
    while (e < texts.all.length && isWordChar(texts.all, e) && sameWord(texts, e - 1))
        ++e
    return e
}

function inWord(texts, o) {
    return isWordChar(texts.all, o - 1) && isWordChar(texts.all, o) && sameWord(texts, o - 1)
}

// An end dragged to the caret at o: the end of the word there, else of the
// last word before it; -1 if there is none.
function snapEnd(texts, o) {
    if (inWord(texts, o))
        return wordEnd(texts, o)
    var i = o - 1
    while (i >= 0 && !isWordChar(texts.all, i))
        --i
    return i < 0 ? -1 : i + 1
}

// A start dragged there: the start of the word there, else of the next one.
function snapStart(texts, o) {
    if (inWord(texts, o))
        return wordStart(texts, o)
    var i = Math.max(0, o)
    while (i < texts.all.length && !isWordChar(texts.all, i))
        ++i
    return i < texts.all.length ? i : -1
}

function lineHeight() {
    return parseFloat(content.getComputedStyle(state.scroller).lineHeight) || 40
}

// The character under x, y as an offset in body.textContent; -1 if the
// point is not on text. The caret may lie on either side of it; a little
// above and below the letters still counts, up to the line's height.
function charAtPoint(x, y) {
    var pos = state.doc.caretPositionFromPoint ? state.doc.caretPositionFromPoint(x, y) : null
    if (!pos || !pos.offsetNode || (pos.offsetNode.nodeType !== 3 && pos.offsetNode.nodeType !== 4))
        return -1
    var texts = textNodes()
    var i = texts ? texts.nodes.indexOf(pos.offsetNode) : -1
    if (i < 0)
        return -1
    var node = texts.nodes[i]
    var line = lineHeight()
    var candidates = [pos.offset, pos.offset - 1]
    for (var n = 0; n < candidates.length; ++n) {
        var k = candidates[n]
        if (k < 0 || k >= node.length)
            continue
        var rects = textBoxes(node, k, k + 1)
        for (var j = 0; j < rects.length; ++j) {
            var r = rects[j]
            var pad = Math.max(0, (line - r.height) / 2)
            if (x >= r.left - 1 && x <= r.right + 1 && y >= r.top - pad && y <= r.bottom + pad)
                return texts.starts[i] + k
        }
    }
    return -1
}

// The caret nearest to x, y as an offset in body.textContent; -1 if none.
function caretOffset(x, y) {
    var pos = state.doc.caretPositionFromPoint ? state.doc.caretPositionFromPoint(x, y) : null
    if (!pos || !pos.offsetNode || (pos.offsetNode.nodeType !== 3 && pos.offsetNode.nodeType !== 4))
        return -1
    var texts = textNodes()
    var i = texts ? texts.nodes.indexOf(pos.offsetNode) : -1
    return i < 0 ? -1 : texts.starts[i] + pos.offset
}

// A range over offsets in body.textContent.
function rangeAt(start, end) {
    var texts = textNodes()
    var range = state.doc.createRange()
    var a = nodeIndex(texts, start)
    var b = nodeIndex(texts, Math.max(start, end - 1))
    range.setStart(texts.nodes[a], start - texts.starts[a])
    range.setEnd(texts.nodes[b], end - texts.starts[b])
    return range
}

function charBox(texts, offset) {
    var i = nodeIndex(texts, offset)
    var at = offset - texts.starts[i]
    return textBoxes(texts.nodes[i], at, Math.min(at + 1, texts.nodes[i].length))[0] || null
}

function select(start, end) {
    state.selection = { start: start, end: end }
    remark()
    return selectionAnswer("")
}

// For QML: where the ends are on the view, as shares of it, the start's
// left edge and the end's right edge with the top and bottom of their
// lines; the text; and which end the finger now moves (see moveEdge).
function selectionAnswer(moving) {
    var texts = textNodes()
    var sel = state.selection
    var a = charBox(texts, sel.start)
    var b = charBox(texts, sel.end - 1)
    if (!a || !b) {
        var whole = rangeAt(sel.start, sel.end).getBoundingClientRect()
        a = a || whole
        b = b || whole
    }
    var w = content.innerWidth
    var h = content.innerHeight
    return {
        serial: state.serial,
        moving: moving,
        start: sel.start,
        end: sel.end,
        mark: markAt(sel),
        text: selectionText(texts, sel),
        startX: a.left / w, startTop: a.top / h, startBottom: a.bottom / h,
        endX: b.right / w, endTop: b.top / h, endBottom: b.bottom / h
    }
}

// Like the marks notes.py takes for notes: "12", "[3]", "*", "a", "iv".
var noteMark = /^(?:[\[\(]?[0-9]{1,3}[a-z]?[\]\)]?|[\[\(]?[*†‡§¶]{1,3}[\]\)]?|[a-zA-Z]|[ivxlcIVXLC]{1,4}|[\[\(][ivxlcdmIVXLCDM]{1,8}[\]\)])[,;.]?$/

function isNoteMark(node) {
    var link = linkOf(node)
    return !!link && isBookLink(link) && noteMark.test(link.textContent.trim())
}

// The text as it reads: spaces of the source folded, a line break between
// paragraphs and at <br/>, without soft hyphens, hidden text and notes'
// numbers; with them if the selection holds nothing else.
function selectionText(texts, sel, keepMarks) {
    var parts = []
    var lastBlock
    for (var i = nodeIndex(texts, sel.start); i < texts.nodes.length && texts.starts[i] < sel.end; ++i) {
        var node = texts.nodes[i]
        var from = Math.max(0, sel.start - texts.starts[i])
        var to = Math.min(node.length, sel.end - texts.starts[i])
        if (to <= from || (!keepMarks && isNoteMark(node)))
            continue
        var piece = node.data.substring(from, to)
        // Not shown: display: none, or not rendered at all (style, script).
        if (/\S/.test(piece) && textBoxes(node, from, to).length === 0)
            continue
        var block = blockOf(node)
        if (lastBlock !== undefined) {
            if (block !== lastBlock || texts.breaks[i] === "line")
                parts.push("\u2029")
            else if (texts.breaks[i] === "gap")
                parts.push(" ")
        }
        lastBlock = block
        parts.push(piece)
    }
    var text = parts.join("").replace(/\u00ad/g, "").split("\u2029").map(function (line) {
        return line.replace(/\s+/g, " ").trim()
    }).filter(function (line) { return line !== "" }).join("\n")
    return text || keepMarks ? text : selectionText(texts, sel, true)
}

// An end of the selection dragged to x, y: it goes to the word there, on
// the page shown only; back into the word it lies in, letter by letter
// ("s'" off "s'intéressèrent"). Dragged past the other end, the ends swap:
// the word at the end left behind stays selected, and the finger moves the
// other end. Returns the end the finger moves now.
function moveEdge(edge, x, y) {
    var texts = textNodes()
    var sel = state.selection
    var o = caretOffset(x, y)
    if (o < 0)
        return edge
    var page = currentPage()
    var s, e
    // Moves come for every bit the finger moves; where the end is already,
    // it stays (snapping would undo a letter taken off).
    if ((edge === "end" && o === sel.end) || (edge === "start" && o === sel.start))
        return edge
    if (edge === "end" && o > sel.start && o < sel.end && isWordChar(texts.all, sel.end - 1)
            && o > wordStart(texts, sel.end - 1)) {
        sel.end = o
        return "end"
    }
    if (edge === "start" && o > sel.start && o < sel.end && isWordChar(texts.all, sel.start)
            && o < wordEnd(texts, sel.start)) {
        sel.start = o
        return "start"
    }
    if (edge === "end") {
        e = snapEnd(texts, o)
        if (e > sel.start) {
            if (pageOfOffset(e - 1) === page)
                sel.end = e
            return "end"
        }
        s = snapStart(texts, o)
        if (s < 0 || pageOfOffset(s) !== page)
            return "end"
        state.selection = { start: s, end: wordEnd(texts, sel.start) }
        return "start"
    }
    s = snapStart(texts, o)
    if (s >= 0 && s < sel.end) {
        if (pageOfOffset(s) === page)
            sel.start = s
        return "start"
    }
    e = snapEnd(texts, o)
    if (e < 0 || pageOfOffset(e - 1) !== page)
        return "start"
    state.selection = { start: wordStart(texts, sel.end - 1), end: e }
    return "end"
}

// Always answered: QML sends the next move only after the answer.
addMessageListener("bookfish:moveEdge", function (message) {
    if (!current() || !state.selection) {
        sendAsyncMessage("bookfish:selected", { serial: -1 })
        return
    }
    var d = message.data
    try {
        var before = state.selection
        var start = before.start
        var end = before.end
        var moving = moveEdge(d.edge, d.x * content.innerWidth, d.y * content.innerHeight)
        // Moved by the reader: a bookmark takes the selection, not the
        // sentence around the word pressed (see takeSelection).
        state.selection.moved = !!before.moved || state.selection.start !== start
                                || state.selection.end !== end
        remark()
        sendAsyncMessage("bookfish:selected", selectionAnswer(moving))
    } catch (e) {
        sendAsyncMessage("bookfish:selected", { serial: -1, error: String(e) })
    }
})

// A sentence ends after one of these, closing quotes or brackets after it,
// before a space, unless a lower-case letter follows ("“Oh!” he said").
var sentenceEnd = /[.!?…]/
var closer = /["'”’“‘»«)\]]/
var lowerCase = /\p{Ll}/u
// Words before a point that does not end the sentence; single letters
// (initials, "z. B.", "e.g.") and numbers of one or two digits ("am 3. Mai")
// count too.
var abbreviations = {
    mr: true, mrs: true, ms: true, dr: true, prof: true, st: true, sr: true, jr: true, vs: true,
    fig: true, cf: true, gen: true, col: true, capt: true, lt: true, rev: true,
    bzw: true, ca: true, vgl: true, usw: true, evtl: true, ggf: true, nr: true, hr: true, fr: true,
    sog: true, bspw: true, inkl: true, zzgl: true, geb: true, gest: true, jh: true, dt: true, ev: true
}

// Where a sentence ending at the character p ends (after closing quotes
// and a note's number), or -1 if it does not end there; limit is the end of
// the paragraph.
function endAfter(texts, p, limit) {
    var all = texts.all
    if (!sentenceEnd.test(all[p]))
        return -1
    var q = p + 1
    while (q < limit && (sentenceEnd.test(all[q]) || closer.test(all[q])))
        ++q
    // "the end.<a>12</a> Next": the number belongs to this sentence.
    while (q < limit && !/\s/.test(all[q])) {
        var i = nodeIndex(texts, q)
        if (!isNoteMark(texts.nodes[i]) || texts.starts[i] !== q)
            break
        q = texts.starts[i] + texts.nodes[i].length
    }
    if (q < limit && !/\s/.test(all[q]))
        return -1
    var r = q
    while (r < limit && /\s/.test(all[r]))
        ++r
    if (r < limit && lowerCase.test(all[r]))
        return -1
    if (all[p] === ".") {
        var w = p
        while (w > 0 && wordLetter.test(all[w - 1]))
            --w
        var word = all.substring(w, p)
        if (word.length === 1 || abbreviations[word.toLowerCase()] || /^\p{N}{1,2}$/u.test(word)
                || (word.toLowerCase() === "no" && r < limit && digit.test(all[r])))
            return -1
    }
    return q
}

// The sentence around a word: in a readaloud the sentence its narration
// marks; else from the end of the sentence before to the end of this one,
// in its paragraph, some thousand characters each way at most.
function sentenceRange(texts, sel) {
    var i = nodeIndex(texts, sel.start)
    var nodes = texts.nodes
    var first = i
    var last = i
    var reach = 3000
    var el
    for (el = nodes[i].parentElement; el; el = el.parentElement) {
        if (el.id && state.isSentence[el.id])
            break
    }
    var inside = el ? function (node) { return el.contains(node) }
                    : function (node) { return blockOf(node) === blockOf(nodes[i]) }
    while (first > 0 && sel.start - texts.starts[first - 1] < reach && inside(nodes[first - 1]))
        --first
    while (last + 1 < nodes.length && texts.starts[last + 1] - sel.end < reach && inside(nodes[last + 1]))
        ++last
    var all = texts.all
    var start = texts.starts[first]
    var end = texts.starts[last] + nodes[last].length
    if (!el) {
        var limit = end
        for (var p = sel.start - 1; p >= start; --p) {
            var q = endAfter(texts, p, limit)
            if (q >= 0 && q <= sel.start) {
                start = q
                break
            }
        }
        for (p = sel.end; p < limit; ++p) {
            q = endAfter(texts, p, limit)
            if (q >= 0) {
                end = q
                break
            }
        }
    }
    while (start < end && /\s/.test(all[start]))
        ++start
    while (end > start && /\s/.test(all[end - 1]))
        --end
    if (end - start > maxMarkLength || start > sel.start || end < sel.end)
        return sel
    return { start: start, end: end }
}

// As bookmarks.MAX_TEXT.
var maxMarkLength = 10000

// For a bookmark: the place selected, or the sentence around the word if
// the reader did not move the ends. raw is the text exactly as it stands,
// to find the place again; quote as it reads (see selectionText).
addMessageListener("bookfish:takeSelection", function (message) {
    if (!current() || !state.selection) {
        sendAsyncMessage("bookfish:selectionTaken", { serial: -1 })
        return
    }
    var texts = textNodes()
    var sel = state.selection.moved ? state.selection : sentenceRange(texts, state.selection)
    var end = Math.min(sel.end, sel.start + maxMarkLength)
    sendAsyncMessage("bookfish:selectionTaken", {
        serial: state.serial,
        action: message.data.action,
        offset: sel.start,
        length: end - sel.start,
        raw: texts.all.substring(sel.start, end),
        quote: selectionText(texts, { start: sel.start, end: end })
    })
})

// Bookmarks of the chapter, underlined: <span>s around their text, which
// leave body.textContent and so every offset as it was. Each comes as
// { id, offset, length, raw } and is found like a search hit; state.marks
// keeps those found as { id, start, end }.
function applyMarks(marks) {
    unwrapMarks()
    var found = []
    for (var i = 0; i < marks.length; ++i) {
        var at = findOffsets({ offset: marks[i].offset, length: marks[i].length, text: marks[i].raw })
        if (at)
            found.push({ id: marks[i].id, start: at.start, end: at.end })
    }
    wrapMarks(found)
    state.marks = found
    remark()
}

function unwrapMarks() {
    var spans = state.doc.querySelectorAll("span.bookfish-mark")
    for (var i = 0; i < spans.length; ++i) {
        var span = spans[i]
        var parent = span.parentNode
        while (span.firstChild)
            parent.insertBefore(span.firstChild, span)
        parent.removeChild(span)
        parent.normalize()
    }
    state.texts = null
}

// Text that is no running text: a span there would change the book.
var unmarkable = { style: true, script: true, textarea: true, title: true, option: true }

// All marks in one pass over the text nodes, each cut once at every mark's
// edge: a long chapter with many bookmarks is not walked once per mark.
// Overlapping marks nest. Only around text with something to see, and in
// XHTML: a span between paragraphs or inside a formula has no business
// there.
function wrapMarks(marks) {
    var texts = textNodes()
    var cuts = new Map()
    marks.forEach(function (mark) {
        for (var i = nodeIndex(texts, mark.start); i < texts.nodes.length && texts.starts[i] < mark.end; ++i) {
            var node = texts.nodes[i]
            var from = Math.max(0, mark.start - texts.starts[i])
            var to = Math.min(node.length, mark.end - texts.starts[i])
            var parent = node.parentNode
            if (to <= from || !/\S/.test(node.data.substring(from, to)) || !parent
                    || parent.namespaceURI !== xhtml || unmarkable[parent.localName])
                continue
            if (!cuts.has(node))
                cuts.set(node, [])
            cuts.get(node).push({ from: from, to: to, id: mark.id })
        }
    })
    cuts.forEach(function (pieces, node) {
        var bounds = [0, node.length]
        pieces.forEach(function (piece) { bounds.push(piece.from, piece.to) })
        bounds = bounds.sort(function (a, b) { return a - b }).filter(function (b, i, all) {
            return i === 0 || b !== all[i - 1]
        })
        var rest = node
        for (var k = 0; k + 1 < bounds.length; ++k) {
            var segment = rest
            if (k + 2 < bounds.length)
                rest = rest.splitText(bounds[k + 1] - bounds[k])
            var from = bounds[k]
            var to = bounds[k + 1]
            if (!/\S/.test(segment.data))
                continue
            pieces.forEach(function (piece) {
                if (piece.from <= from && to <= piece.to) {
                    var span = state.doc.createElementNS(xhtml, "span")
                    span.setAttribute("class", "bookfish-mark")
                    span.setAttribute("data-mark", String(piece.id))
                    segment.parentNode.insertBefore(span, segment)
                    span.appendChild(segment)
                }
            })
        }
    })
    state.texts = null
}

// The bookmark the selection starts in, else one it overlaps; 0 if none.
function markAt(sel) {
    var marks = state.marks || []
    for (var i = 0; i < marks.length; ++i) {
        if (marks[i].start <= sel.start && sel.start < marks[i].end)
            return marks[i].id
    }
    for (i = 0; i < marks.length; ++i) {
        if (marks[i].start < sel.end && sel.start < marks[i].end)
            return marks[i].id
    }
    return 0
}

addMessageListener("bookfish:marks", function (message) {
    if (current())
        applyMarks(message.data.marks || [])
})

// The text found, if any, is marked again.
addMessageListener("bookfish:selectClear", function (message) {
    if (!current())
        return
    state.selection = null
    try {
        content.getSelection().removeAllRanges()
    } catch (e) { }
    remark()
})

// The link into the book nearest to x, y on the page shown, at most a line
// away: a note's mark is small, a finger is not.
function linkAt(x, y) {
    var reach = parseFloat(content.getComputedStyle(state.scroller).lineHeight) || 40
    var best = null
    var bestDistance = reach
    var links = state.doc.getElementsByTagNameNS(xhtml, "a")
    for (var i = 0; i < links.length; ++i) {
        if (!isBookLink(links[i]))
            continue
        var rects = boxes(links[i])
        for (var j = 0; j < rects.length; ++j) {
            var r = rects[j]
            if (r.right < 0 || r.left > content.innerWidth)
                continue
            var dx = Math.max(r.left - x, 0, x - r.right)
            var dy = Math.max(r.top - y, 0, y - r.bottom)
            var distance = Math.sqrt(dx * dx + dy * dy)
            if (distance <= bestDistance) {
                best = links[i]
                bestDistance = distance
            }
        }
    }
    return best
}

// The address of a picture at x, y, "" if none. Small ones count as none:
// ornaments, rules and the wide but low heads of chapters (measured over
// the library: the shorter side of all of them is below a quarter of the
// text's width).
function pictureAt(x, y) {
    var el = state.doc.elementFromPoint(x, y)
    var picture = null
    for (; el; el = el.parentElement) {
        if (el.localName === "img" || el.localName === "svg")
            picture = el
    }
    var src = ""
    if (picture) {
        var rect = picture.getBoundingClientRect()
        var style = content.getComputedStyle(state.scroller)
        var textWidth = columnWidth(parseFloat(style.paddingLeft) + parseFloat(style.paddingRight))
        if (Math.min(rect.width, rect.height) >= textWidth / 4) {
            if (picture.localName === "img") {
                src = picture.currentSrc || picture.src || ""
            } else {
                var image = picture.querySelector("image")
                var href = image ? (image.getAttribute("href")
                                    || image.getAttributeNS("http://www.w3.org/1999/xlink", "href")) : ""
                // A link resolves the address against the chapter's.
                if (href) {
                    var link = state.doc.createElementNS("http://www.w3.org/1999/xhtml", "a")
                    link.setAttribute("href", href)
                    src = link.href || ""
                }
            }
        }
    }
    return src
}

// Where playback starts on this page: the preferred sentence (the one
// paused at) if it is on the page, else the topmost sentence, also one cut
// off at the top, else the first one after the page. "" if there is none.
addMessageListener("bookfish:startSentence", function (message) {
    if (!current())
        return
    var page = currentPage()
    var id = ""
    var prefer = message.data.prefer ? state.doc.getElementById(message.data.prefer) : null
    if (prefer && boxes(prefer).some(function (r) { return pageOfBox(r) === page }))
        id = prefer.id
    for (var i = 0; !id && i < state.sentences.length; ++i) {
        var rects = boxes(state.sentences[i])
        if (rects.length && pageOfBox(rects[rects.length - 1]) >= page)
            id = state.sentences[i].id
    }
    sendAsyncMessage("bookfish:start", { serial: state.serial, id: id })
})

function important(css) {
    return css.replace(/;/g, " !important;")
}

// Elements that may stay smaller than the text around them.
var smallTags = { sub: true, sup: true, small: true, rt: true, rtc: true, rp: true }
var xhtml = "http://www.w3.org/1999/xhtml"

// The families of the book's @font-face rules, quoted, each after a comma.
function bookFonts(doc) {
    var names = []
    try {
        doc.fonts.forEach(function (face) {
            var name = face.family.replace(/^["']|["']$/g, "").replace(/[\x00-\x1f\x7f"\\;]/g, "")
            if (name && names.indexOf(name) < 0)
                names.push(name)
        })
    } catch (e) {
        return ""
    }
    return names.map(function (name) { return ', "' + name + '"' }).join("")
}

// Kept small on purpose: hidden (0), raised like a note mark, or small caps.
function smallOnPurpose(style, size) {
    return size === 0 || /^(super|sub|top|text-top)$/.test(style.verticalAlign)
           || style.fontVariantCaps !== "normal"
           || (style.textTransform === "uppercase" && style.display === "inline")
}

// Block elements: a div holding none of them is a paragraph.
var blocks = "p, div, ul, ol, dl, table, blockquote, pre, section, article, aside, figure, " +
             "header, footer, h1, h2, h3, h4, h5, h6, hr"

// An empty paragraph, typically "<div> </div>" between paragraphs in
// books converted from Kindle files, stands for a blank line, unless it
// draws something: an ornament (::before), a background, a border.
var drawn = "img, svg, hr, video, audio, object, iframe, table, math"

function isBlankLine(element, style) {
    if ((element.localName !== "div" && element.localName !== "p")
            || element.textContent.trim() !== "" || element.querySelector(drawn)
            || style.backgroundImage !== "none" || parseFloat(style.borderTopWidth) > 0
            || parseFloat(style.borderBottomWidth) > 0)
        return false
    var before = content.getComputedStyle(element, "::before").content
    var after = content.getComputedStyle(element, "::after").content
    return (before === "none" || before === "normal") && (after === "none" || after === "normal")
}

// What normalize changed in the book's inline styles, to undo it before the
// next layout: [element, property, old value, old priority].
var overridden = []

function override(element, property, value) {
    // An element of a namespace unknown to Gecko has no style.
    if (!element.style)
        return
    overridden.push([element, property, element.style.getPropertyValue(property),
                     element.style.getPropertyPriority(property)])
    element.style.setProperty(property, value, "important")
}

function restore() {
    // Backwards: an element changed twice gets its first value back.
    for (var i = overridden.length - 1; i >= 0; --i) {
        var o = overridden[i]
        if (o[2])
            o[0].style.setProperty(o[1], o[2], o[3])
        else
            o[0].style.removeProperty(o[1])
    }
    overridden = []
}

// Undo what CSS alone cannot, looking at each element:
// - books shrink their text with relative sizes on paragraphs or wrappers
//   (".calibre { font-size: 0.75em }"), which would scale the text size
//   chosen in the app, while larger headings must stay: an element smaller
//   than its parent gets 1em;
// - paragraphs get the app's spacing, or an indent; many books build them
//   from divs. A large space above one is a scene break and stays. A single
//   blank line between them goes (it would add to the spacing chosen),
//   several in a row stay: a scene break;
// - justified text leaves wide gaps on a narrow screen, but "center" must
//   stay, and a centred paragraph must not be pushed aside by the indent.
// All reads come before all writes: mixing them would recompute the styles
// every time. Only XHTML elements: MathML and SVG size their parts
// themselves.
function normalize(doc, o) {
    // A new layout starts from the book's styles, so that it gives the same
    // result as the first one.
    try {
        if (overridden.length > 0 && overridden[0][0].ownerDocument === doc)
            restore()
    } catch (e) {
        // Elements of a chapter already closed.
    }
    overridden = []
    if (!doc.body)
        return
    // Ours only: a book's own element of that class keeps it.
    tableLinks.forEach(function (link) { link.element.classList.remove("bookfish-table-link") })
    tableLinks = []
    var elements = doc.body.getElementsByTagName("*")
    var justified = []
    var centred = []
    var paragraphs, blanks
    // A wrapper made larger can leave a child of fixed size smaller than
    // it; another look catches that. Paragraph margins are judged on the
    // last look, with the sizes corrected.
    for (var pass = 0; pass < 3; ++pass) {
        var sizes = new Map([[doc.body, parseFloat(content.getComputedStyle(doc.body).fontSize)]])
        var shrunk = []
        paragraphs = []
        blanks = new Map()
        // Document order: a parent comes before its children.
        for (var i = 0; i < elements.length; ++i) {
            var element = elements[i]
            if (element.namespaceURI !== xhtml)
                continue
            var style = content.getComputedStyle(element)
            var size = parseFloat(style.fontSize)
            sizes.set(element, size)
            if (pass === 0) {
                if (style.textAlign === "justify")
                    justified.push(element)
                else if (/center|right|end/.test(style.textAlign))
                    centred.push(element)
            }
            if (isBlankLine(element, style)) {
                // Only the outermost of nested blank lines counts. An empty
                // anchor without a box is no line.
                if (!blanks.has(element.parentElement))
                    blanks.set(element, element.getClientRects().length > 0)
            } else if (element.localName === "p" || (element.localName === "div"
                    && !element.querySelector(blocks))) {
                paragraphs.push({ element: element,
                                  keepTop: parseFloat(style.marginTop) > 1.5 * size,
                                  keepBottom: parseFloat(style.marginBottom) > 1.5 * size })
            }
            var parentSize = sizes.get(element.parentElement)
            if (parentSize && size < parentSize * 0.9 && !smallTags[element.localName]
                    && !smallOnPurpose(style, size))
                shrunk.push(element)
        }
        if (shrunk.length === 0)
            break
        for (var k = 0; k < shrunk.length; ++k)
            override(shrunk[k], "font-size", "1em")
    }
    var spacing = (o.paragraphSpacing * o.lineHeight) + "em"
    var indent = o.paragraphSpacing > 0 ? "0" : "1em"
    for (var p = 0; p < paragraphs.length; ++p) {
        var paragraph = paragraphs[p]
        if (!paragraph.keepTop)
            override(paragraph.element, "margin-top", "0")
        if (!paragraph.keepBottom)
            override(paragraph.element, "margin-bottom", spacing)
        override(paragraph.element, "text-indent", indent)
    }
    // Single blank lines between paragraphs go, runs stay: a scene break.
    // Only in books that use them between paragraphs at all; a book with a
    // few keeps them as its scene breaks.
    var single = []
    blanks.forEach(function (boxed, blank) {
        var before = blank.previousElementSibling
        var after = blank.nextElementSibling
        if (boxed && !(before && blanks.get(before)) && !(after && blanks.get(after)))
            single.push(blank)
    })
    if (single.length > 0.2 * paragraphs.length) {
        for (var b = 0; b < single.length; ++b) {
            // Folded, not hidden: an id on it may be the target of a link.
            override(single[b], "font-size", "0")
            override(single[b], "line-height", "0")
            override(single[b], "margin-top", "0")
            override(single[b], "margin-bottom", "0")
        }
    }
    for (var j = 0; j < justified.length; ++j)
        override(justified[j], "text-align", "start")
    for (var c = 0; c < centred.length; ++c)
        override(centred[c], "text-indent", "0")
    // A book's odd table must not cost the whole chapter: without the layout
    // finishing, QML keeps the view covered.
    try {
        fitTables(doc, o.margin, o.columns > 1 ? 2 : 1)
        splitTallTables(doc)
        markTables(doc)
    } catch (e) { }
}

// Only outer tables: a nested one goes along with the one around it.
function outerTables(doc) {
    // By namespace: in XML, getElementsByTagName("table") misses <h:table>,
    // which Python counts (tables.py numbers them the same way).
    return Array.prototype.filter.call(doc.body.getElementsByTagNameNS(xhtml, "table"), function (table) {
        return !table.parentElement.closest("table")
    })
}

// A table is at least as wide as the longest words of its columns together;
// overflow-wrap: break-word does not change that. What sticks out of a column
// is drawn in the next one, on the next page. So a table too wide gives up its
// own width, then shrinks its text; breaking words is the last resort, below
// minTableScale: small text reads better than broken words.
var minTableScale = 0.4

function fitTables(doc, margin, columns) {
    var tables = outerTables(doc)
    // All reads before all writes: one reflow per round, however many tables.
    function tooWide(list) {
        // Not innerWidth: rounded, and far into a long chapter the small
        // difference would put a box on the wrong page.
        var width = doc.body.getBoundingClientRect().width / columns
        var scrolled = doc.body.scrollLeft
        var wide = []
        for (var i = 0; i < list.length; ++i) {
            var box = boxes(list[i])[0]
            if (!box)
                continue
            var left = box.left + scrolled
            // With margin: a table moved left by the book may start in the
            // gap before its page.
            var room = (Math.floor((left + margin) / width) + 1) * width - margin - left
            if (box.width > room + 1)
                wide.push({ table: list[i], share: room / box.width })
        }
        return wide
    }
    function tablesOf(wide) {
        return wide.map(function (item) { return item.table })
    }
    function fontSize(element) {
        return parseFloat(content.getComputedStyle(element).fontSize)
    }
    var wide = tooWide(tables)
    // Sizes the book gives in pt or rem would not follow the table's; as
    // shares of the parent they do, and look the same.
    var scales = new Map()
    var shares = []
    wide.forEach(function (item) {
        scales.set(item.table, fontSize(item.table) / fontSize(item.table.parentElement))
        var inside = item.table.getElementsByTagName("*")
        for (var i = 0; i < inside.length; ++i) {
            var parentSize = fontSize(inside[i].parentElement)
            if (inside[i].namespaceURI === xhtml && parentSize > 0)
                shares.push([inside[i], fontSize(inside[i]) / parentSize])
        }
    })
    shares.forEach(function (share) { override(share[0], "font-size", share[1] + "em") })
    function dropWidth(table) {
        override(table, "width", "auto")
        override(table, "min-width", "0")
    }
    wide.forEach(function (item) {
        dropWidth(item.table)
        Array.prototype.forEach.call(item.table.getElementsByTagName("table"), dropWidth)
    })
    // Fixed spacing in the cells does not shrink with the text, so one round
    // falls short; with much of it, several do. A little more than the exact
    // share gets there sooner, and breaks no words for a pixel left over.
    for (var round = 0; round < 6; ++round) {
        wide = tooWide(tablesOf(wide))
        var shrunk = false
        wide.forEach(function (item) {
            var scale = Math.max(minTableScale, scales.get(item.table) * item.share * 0.98)
            if (scale < scales.get(item.table)) {
                scales.set(item.table, scale)
                override(item.table, "font-size", scale + "em")
                shrunk = true
            }
        })
        if (!shrunk)
            break
    }
    tooWide(tablesOf(wide)).forEach(function (item) {
        override(item.table, "overflow-wrap", "anywhere")
    })
}

// Gecko never splits a table over CSS columns: what is below the page is cut
// off, and the next page goes on after the table. So a table taller than the
// page turns into blocks, one grid per row, in the columns it had as a table.
// Rows are blocks and may go to the next page; a row taller than a page has to
// be split itself, so its cells stack. Other tables stay tables: a grid is no
// match for cells spanning rows, and a short table would be torn apart.
function splitTallTables(doc) {
    var rect = doc.body.getBoundingClientRect()
    var style = content.getComputedStyle(doc.body)
    var bottom = rect.bottom - parseFloat(style.paddingBottom)
    var pageHeight = bottom - rect.top - parseFloat(style.paddingTop)
    function below(element) {
        return boxes(element).some(function (box) { return box.bottom > bottom + 1 })
    }
    function own(table, selector) {
        return Array.prototype.filter.call(table.querySelectorAll(selector), function (element) {
            return element.closest("table") === table && boxes(element).length > 0
        })
    }
    // All reads before all writes.
    var plans = outerTables(doc).filter(below).map(function (table) {
        var cells = own(table, "td, th")
        var places = cells.map(function (cell) { return cell.getBoundingClientRect() })
        // Spacing between cells becomes a column of its own, so the table's
        // left edge counts too.
        var lines = [boxes(table)[0].left]
        places.forEach(function (place) { lines.push(place.left, place.right) })
        lines.sort(function (a, b) { return a - b })
        var edges = lines.filter(function (line, i) { return i === 0 || line - lines[i - 1] > 1.5 })
        function lineAt(x) {
            var n = 0
            while (n + 1 < edges.length && edges[n + 1] <= x + 1.5)
                ++n
            return n + 1
        }
        var tracks = []
        for (var i = 1; i < edges.length; ++i)
            tracks.push((edges[i] - edges[i - 1]) + "px")
        return { table: table, cells: cells, rows: own(table, "tr"), tracks: tracks.join(" "),
                 columns: places.map(function (place) { return lineAt(place.left) + " / " + lineAt(place.right) }) }
    })
    plans.forEach(function (plan) {
        var blocks = new Set([plan.table])
        Array.prototype.forEach.call(plan.table.getElementsByTagName("caption"), function (caption) {
            if (caption.closest("table") === plan.table)
                blocks.add(caption)
        })
        plan.rows.forEach(function (row) {
            override(row, "display", "grid")
            override(row, "grid-template-columns", plan.tracks)
            for (var up = row.parentElement; up !== plan.table; up = up.parentElement)
                blocks.add(up)
        })
        blocks.forEach(function (block) { override(block, "display", "block") })
        Array.prototype.forEach.call(plan.table.querySelectorAll("col, colgroup"), function (column) {
            override(column, "display", "none")
        })
        plan.cells.forEach(function (cell, i) {
            override(cell, "display", "block")
            override(cell, "grid-column", plan.columns[i])
            // Its width as a share of the table would now refer to its column;
            // a margin, without effect on a table cell, would now count.
            override(cell, "width", "auto")
            override(cell, "min-width", "0")
            override(cell, "margin", "0")
        })
    })
    var tallRows = []
    plans.forEach(function (plan) {
        plan.rows.forEach(function (row) {
            if (below(row) || boxes(row).some(function (box) { return box.height > pageHeight - 1 }))
                tallRows.push(row)
        })
    })
    tallRows.forEach(function (row) { override(row, "display", "block") })
}

// In each table, the first cell with text looks like a link, and so does the
// table's caption ("Table 2-1. ...", Huyen): a long press on either opens the
// table as the book made it (QML's table view). Numbered as Python counts
// outer tables. Only a class: places are kept as offsets in the chapter's
// text, which must not change. Paragraphs before or after a table are not
// taken for captions: in the library those beginning with "Table" are body
// text ("Table 4-3 shows ...", 16.11.2026).
var tableLinks = []

function markTables(doc) {
    function mark(element, index) {
        if (element.textContent.trim() && !element.classList.contains("bookfish-table-link")) {
            element.classList.add("bookfish-table-link")
            tableLinks.push({ element: element, table: index })
            return true
        }
        return false
    }
    outerTables(doc).forEach(function (table, index) {
        Array.prototype.forEach.call(table.children, function (child) {
            if (child.namespaceURI === xhtml && child.localName === "caption")
                mark(child, index)
        })
        var cells = table.querySelectorAll("td, th")
        for (var i = 0; i < cells.length; ++i) {
            if (cells[i].closest("table") === table && mark(cells[i], index))
                return
        }
    })
}

// The index-th outer table as the book made it, as a PNG (base64): the reader
// shrinks tables too wide for the page and breaks those taller than a page
// into rows. A copy without our changes is laid out outside the columns,
// as narrow as its words allow, drawn at twice the screen's resolution for
// zooming in, and taken out again before anything reaches the screen.
// Within the texture size of phones' GPUs (often 8192), and memory: the
// picture is held several times, as canvas, base64 and QImage.
var tableWidthFactor = 2
var maxTablePixels = 16e6
var maxTableSide = 8192

function drawTable(index) {
    var doc = state.doc
    var table = outerTables(doc)[index]
    if (!table)
        throw new Error("no table " + index)
    var copy = table.cloneNode(true)
    var originals = [table].concat(Array.prototype.slice.call(table.getElementsByTagName("*")))
    var copies = [copy].concat(Array.prototype.slice.call(copy.getElementsByTagName("*")))
    var copyOf = new Map()
    originals.forEach(function (element, i) { copyOf.set(element, copies[i]) })
    for (var i = overridden.length - 1; i >= 0; --i) {
        var o = overridden[i]
        var c = copyOf.get(o[0])
        if (!c || !c.style)
            continue
        if (o[2])
            c.style.setProperty(o[1], o[2], o[3])
        else
            c.style.removeProperty(o[1])
    }
    // Ids stay: the book's rules for #id apply to the copy too, and the
    // copy is gone before anyone looks one up.
    copies.forEach(function (element) {
        if (element.classList)
            element.classList.remove("bookfish-table-link", "bookfish-active", "bookfish-resume", "bookfish-mark")
    })
    var box = doc.createElementNS(xhtml, "div")
    box.setAttribute("class", "bookfish-table-render")
    var style = content.getComputedStyle(state.scroller)
    var textWidth = columnWidth(parseFloat(style.paddingLeft) + parseFloat(style.paddingRight))
    // Up to twice the page's width: as narrow as the text, cells broke
    // their lines after every word or two (Huyen, 16.11.2026), and the
    // picture is fitted to the screen's width. A narrower table keeps its
    // own width, a wider one its longest words.
    box.style.width = (tableWidthFactor * textWidth) + "px"
    box.appendChild(copy)
    doc.documentElement.appendChild(box)
    try {
        box.style.width = Math.ceil(copy.getBoundingClientRect().width) + "px"
        var rect = box.getBoundingClientRect()
        // What sticks out of the box counts too.
        var w = Math.ceil(Math.max(rect.width, box.scrollWidth))
        var h = Math.ceil(Math.max(rect.height, box.scrollHeight))
        var scale = Math.min(2 * (content.devicePixelRatio || 1), Math.sqrt(maxTablePixels / (w * h)),
                             maxTableSide / w, maxTableSide / h)
        var canvas = doc.createElementNS(xhtml, "canvas")
        canvas.width = Math.max(1, Math.round(w * scale))
        canvas.height = Math.max(1, Math.round(h * scale))
        var context = canvas.getContext("2d")
        context.scale(scale, scale)
        // drawWindow takes document coordinates.
        context.drawWindow(content, rect.left + content.scrollX, rect.top + content.scrollY, w, h,
                           style.backgroundColor)
        var url = canvas.toDataURL("image/png")
        return url.slice(url.indexOf(",") + 1)
    } finally {
        box.remove()
    }
}

// The number of the table whose marked cell or caption is at x, y, or -1.
function tableLinkAt(x, y) {
    for (var el = state.doc.elementFromPoint(x, y); el; el = el.parentElement) {
        for (var i = 0; i < tableLinks.length; ++i) {
            if (tableLinks[i].element === el)
                return tableLinks[i].table
        }
    }
    return -1
}

// After a layout QML covers the view until Gecko has painted it; the layout
// itself is reported before the paint. A paint of the unstyled page may
// still be under way and report afterwards, so only paints of a later
// transaction than the one current at the layout count.
var paintSerial = -1
var paintAfter = -1
addEventListener("MozAfterPaint", function (event) {
    if (paintSerial < 0)
        return
    if (paintAfter >= 0 && !(event.transactionId > paintAfter))
        return
    sendAsyncMessage("bookfish:painted", { serial: paintSerial })
    paintSerial = -1
}, true)

function awaitPaint(serial) {
    try {
        paintAfter = content.windowUtils.lastTransactionId
    } catch (e) {
        paintAfter = -1
    }
    paintSerial = serial
}

// A jump within the chapter: what was marked belongs to the place left.
addMessageListener("bookfish:goto", function (message) {
    if (!current())
        return
    state.selection = null
    if (!message.data.target.find)
        unmark()
    go(message.data.target)
})

addMessageListener("bookfish:turn", function (message) {
    if (!current())
        return
    unmark()
    var page = currentPage() + message.data.delta
    if (page < 0 || page >= pageCount()) {
        sendAsyncMessage("bookfish:edge", { serial: state.serial, delta: message.data.delta })
        return
    }
    showPage(page)
})

function pageCount() {
    return Math.max(1, Math.round(state.scroller.scrollWidth / state.width))
}

// Two columns: a chapter ending in a left column would scroll only half
// the last screen, which then showed half the screen before. A filler as
// high as a column leaves the rest of that column and fills the right one.
function evenColumns(doc) {
    var old = doc.getElementById("bookfish-filler")
    if (old)
        old.parentNode.removeChild(old)
    if (state.columns < 2)
        return
    var halves = Math.round(state.scroller.scrollWidth / (state.width / 2))
    if (halves % 2 === 0)
        return
    var style = content.getComputedStyle(state.scroller)
    var filler = doc.createElementNS(xhtml, "div")
    filler.id = "bookfish-filler"
    filler.style.setProperty("height", (state.scroller.clientHeight - parseFloat(style.paddingTop)
                                        - parseFloat(style.paddingBottom)) + "px", "important")
    filler.style.setProperty("margin", "0", "important")
    filler.style.setProperty("padding", "0", "important")
    filler.style.setProperty("border", "0", "important")
    state.scroller.appendChild(filler)
}

// The CSS columns: one screen width each, or two to a screen. Every screen
// starts exactly one width further right. Slightly narrower than exact,
// or rounding may leave room for one column only.
function columnRule(width, margin, columns) {
    var column = columns > 1 ? width / columns - 2 * margin - 0.01 : width - 2 * margin
    return "  column-width: " + column + "px; column-gap: " + (2 * margin) + "px; column-fill: auto;"
}

// The width of a column of text; padding is the page's on both sides.
function columnWidth(padding) {
    return (state.width - padding - (state.columns - 1) * 2 * state.margin) / state.columns
}

function currentPage() {
    return Math.round(state.scroller.scrollLeft / state.width)
}

// Turning pages or listening: the found text and the sentence heard last
// are no longer what the reader looks at.
function unmark() {
    state.found = null
    state.selection = null
    try {
        content.getSelection().removeAllRanges()
    } catch (e) { }
    if (state.resume) {
        state.resume.classList.remove("bookfish-resume")
        state.resume = null
    }
}

addMessageListener("bookfish:unmark", function (message) {
    if (current())
        unmark()
})

// Gecko drops the selection when the page is shown again after another
// one (the search) or laid out again; select the text found once more.
// The reader's own selection comes first: Gecko shows only one.
function remark() {
    var at = state.selection || state.found
    if (!at)
        return
    var range = rangeAt(at.start, at.end)
    var selection = content.getSelection()
    selection.removeAllRanges()
    selection.addRange(range)
}

addMessageListener("bookfish:remark", function (message) {
    if (current())
        remark()
})

// A place found by the search: offset and length in body.textContent,
// counted in UTF-16 code units, and the text expected there. Should the
// text differ, the occurrence nearest to offset is taken: the HTML parser
// may read a page slightly differently. null if it is not in the chapter.
function findRange(find) {
    var at = findOffsets(find)
    return at ? rangeAt(at.start, at.end) : null
}

// The same as offsets in body.textContent: { start, end }, or null.
function findOffsets(find) {
    var texts = textNodes()
    if (!texts || !find.text)
        return null
    var all = texts.all
    var at = find.offset
    if (all.substr(at, find.length) !== find.text) {
        var after = all.indexOf(find.text, at)
        var before = all.lastIndexOf(find.text, at)
        if (after < 0 && before < 0)
            return null
        at = after < 0 ? before : before < 0 ? after : (after - at <= at - before ? after : before)
    }
    return { start: at, end: at + find.text.length }
}

// The text nodes of the body (text and CDATA), where each starts in
// body.textContent, and that text; null without a body. Kept until the
// chapter is laid out again: our layout changes styles, not text.
function textNodes() {
    if (state.texts)
        return state.texts
    var body = state.doc.body
    if (!body)
        return null
    var nodes = []
    var starts = []
    var all = ""
    // What stands between a node and the one before, seen by a selection:
    // "line" for a line break, "gap" for a picture or formula, else "".
    var breaks = []
    var pending = ""
    // In the order textContent joins them; elements only for breaks.
    var walker = state.doc.createTreeWalker(body, 1 | 4 | 8)
    for (var n = walker.nextNode(); n; n = walker.nextNode()) {
        if (n.nodeType === 1) {
            if (n.localName === "br")
                pending = "line"
            else if (!pending && gapTags[n.localName])
                pending = "gap"
            continue
        }
        nodes.push(n)
        starts.push(all.length)
        breaks.push(pending)
        pending = ""
        all += n.data
    }
    state.texts = { nodes: nodes, starts: starts, all: all, breaks: breaks }
    return state.texts
}

var gapTags = { img: true, svg: true, math: true, video: true, audio: true, object: true, iframe: true,
                input: true, hr: true }

// The boxes of characters from to to of a text node, or of all of it.
function textBoxes(node, from, to) {
    var range = state.doc.createRange()
    if (from === undefined)
        range.selectNodeContents(node)
    else {
        range.setStart(node, from)
        range.setEnd(node, to)
    }
    return Array.prototype.filter.call(range.getClientRects(), function (r) {
        return r.width >= 1 && r.height >= 1
    })
}

// The first index from lo up to hi (exclusive) for which pageAt gives a
// page; pageAt returns -1 where nothing is shown (collapsed spaces, hidden
// text). Pages grow along the text, so the first one at or after page is
// found by halving; the -1 between are stepped over. hi if there is none.
function firstAtOrAfter(page, lo, hi, pageAt) {
    var found = hi
    while (lo < hi) {
        var mid = (lo + hi) >> 1
        var probe = mid
        var p = -1
        while (probe < hi && (p = pageAt(probe)) < 0)
            ++probe
        if (probe < hi && p < page) {
            lo = probe + 1
        } else {
            // Nothing shown from mid to hi, or the first shown is on or
            // after the page: an earlier one can only lie before mid.
            if (probe < hi)
                found = probe
            hi = mid
        }
    }
    return found
}

// Where the page begins in body.textContent, in UTF-16 code units: its
// first character shown, or the first one after it if the page holds no
// text (a picture): { offset, onPage }; offset -1 if no text follows.
// Searched by halving, first over the text nodes, then over the characters
// of one: some 30 boxes asked for instead of one per node.
function firstTextOn(page) {
    var none = { offset: -1, onPage: false }
    var texts = textNodes()
    if (!texts)
        return none
    var nodes = texts.nodes
    // The first node shown that ends on the page or after it.
    var i = firstAtOrAfter(page, 0, nodes.length, function (k) {
        var rects = textBoxes(nodes[k])
        return rects.length ? pageOfBox(rects[rects.length - 1]) : -1
    })
    if (i === nodes.length)
        return none
    var node = nodes[i]
    var c = firstAtOrAfter(page, 0, node.length, function (k) {
        var rects = textBoxes(node, k, k + 1)
        return rects.length ? pageOfBox(rects[rects.length - 1]) : -1
    })
    if (c === node.length)
        return none
    var rects = textBoxes(node, c, c + 1)
    return { offset: texts.starts[i] + c, onPage: pageOfBox(rects[0]) <= page }
}

// The printed page shown for page: the index in state.pageMarks of the last
// mark on this page or an earlier one, -1 if none. A page beginning on the
// screen counts, though the lines above it belong to the one before: going
// to page 143 shows the screen where it begins, which then says 143. A
// mark's place is its box; without one (hidden) the page of the first text
// after it, see markPage().
function pageMarkAt(page) {
    var found = -1
    var foundPage = -1
    for (var i = 0; i < state.pageMarks.length; ++i) {
        var markPage = markPageOf(i)
        if (markPage < 0 || markPage > page)
            continue
        // Several on one page: the last in the text. Pictures printed as
        // pages of their own share the offset of the text after them.
        if (found < 0 || markPage > foundPage
                || (markPage === foundPage && state.pageMarkOffsets[i] >= state.pageMarkOffsets[found])) {
            found = i
            foundPage = markPage
        }
    }
    return found
}

// The page of state.pageMarks[i], -1 if it is not in the chapter.
function markPageOf(i) {
    if (!state.pageMarkOffsets) {
        var texts = textNodes()
        state.pageMarkOffsets = state.pageMarks.map(function (id) {
            if (!texts)
                return -1
            if (id === "")
                return 0
            var el = state.doc.getElementById(id)
            if (!el)
                return -1
            // The first text node following the mark, or inside it.
            var lo = 0
            var hi = texts.nodes.length
            while (lo < hi) {
                var mid = (lo + hi) >> 1
                if (el.compareDocumentPosition(texts.nodes[mid]) & 4)
                    hi = mid
                else
                    lo = mid + 1
            }
            return lo < texts.nodes.length ? texts.starts[lo] : texts.all.length
        })
    }
    var offset = state.pageMarkOffsets[i]
    if (!(offset >= 0))
        return -1
    var id = state.pageMarks[i]
    if (id === "")
        return 0
    // Not cached: pictures loading later move the pages.
    var rects = state.doc.getElementById(id).getClientRects()
    return rects.length ? pageOfBox(rects[0]) : pageOfText(offset)
}

// The page of the first text shown at or after offset; the last page if
// none is shown after it. For a hidden mark, whose next text may be hidden
// too (display: none).
function pageOfText(offset) {
    var texts = textNodes()
    for (var i = 0; texts && i < texts.nodes.length; ++i) {
        if (texts.starts[i] + texts.nodes[i].length <= offset)
            continue
        var node = texts.nodes[i]
        var from = Math.max(0, offset - texts.starts[i])
        var rects = textBoxes(node, from, node.length)
        if (rects.length)
            return pageOfBox(rects[0])
    }
    return pageCount() - 1
}

// The first character of the line in the middle of the page shown, as an
// offset in body.textContent (see findRange); -1 if there is none there.
// Asked just inside the left margin: a short line (a paragraph's end,
// dialogue) leaves the middle of the screen empty, but every line has text
// at its start, the caret goes there also beside an indent.
function middleOffset(page, margin) {
    var pos = state.doc.caretPositionFromPoint ? state.doc.caretPositionFromPoint(margin + 2,
                                                                                   content.innerHeight / 2)
                                               : null
    // Text or CDATA, as textNodes() counts them.
    if (!pos || !pos.offsetNode || (pos.offsetNode.nodeType !== 3 && pos.offsetNode.nodeType !== 4))
        return -1
    var texts = textNodes()
    var i = texts ? texts.nodes.indexOf(pos.offsetNode) : -1
    if (i < 0)
        return -1
    var offset = texts.starts[i] + pos.offset
    // Beside a picture the nearest text may lie on another page.
    return pageOfOffset(offset) === page ? offset : -1
}

// The offset of the first character on the page, -1 if it holds no text.
function firstOffsetOn(page) {
    var text = firstTextOn(page)
    return text.onPage ? text.offset : -1
}

// The page showing the character at offset in body.textContent; -1 if it
// is not shown.
function pageOfOffset(offset) {
    var texts = textNodes()
    if (!texts || offset < 0 || offset >= texts.all.length)
        return -1
    // The last node starting at or before offset.
    var lo = 0
    var hi = texts.starts.length
    while (hi - lo > 1) {
        var mid = (lo + hi) >> 1
        if (texts.starts[mid] <= offset)
            lo = mid
        else
            hi = mid
    }
    var node = texts.nodes[lo]
    var at = offset - texts.starts[lo]
    var rects = textBoxes(node, at, Math.min(at + 1, node.length))
    return rects.length ? pageOfBox(rects[0]) : -1
}

// The sentence holding the found place, else the next one after it; "".
function sentenceAt(range) {
    for (var el = range.startContainer; el; el = el.parentNode) {
        if (el.id && state.isSentence[el.id])
            return el.id
    }
    for (var i = 0; i < state.sentences.length; ++i) {
        // DOCUMENT_POSITION_FOLLOWING
        if (range.startContainer.compareDocumentPosition(state.sentences[i]) & 4)
            return state.sentences[i].id
    }
    return ""
}

// The found text is selected, which Gecko shows marked; the WebView gets
// no touches, so the reader cannot change the selection.
function goFound(find) {
    var at = findOffsets(find)
    var range = at ? rangeAt(at.start, at.end) : null
    var id = ""
    if (state.resume) {
        state.resume.classList.remove("bookfish-resume")
        state.resume = null
    }
    if (range) {
        var rects = Array.prototype.filter.call(range.getClientRects(), function (r) {
            return r.width >= 1 && r.height >= 1
        })
        showPage(rects.length ? pageOfBox(rects[0]) : 0)
        state.found = at
        remark()
        id = sentenceAt(range)
    } else {
        // Not the previous hit's mark on another page.
        state.found = null
        content.getSelection().removeAllRanges()
        showPage(0)
    }
    sendAsyncMessage("bookfish:found", { serial: state.serial, id: id })
}

// target: { id, offset, fraction } (any may be missing; the first one
// found counts), { end: true }, { find } (see findRange), { pageMark } (an
// index in state.pageMarks: the page where that printed page begins) or
// { share } (estimated pages: the first page whose start is at least that
// share of the chapter, as ReaderPage counts it); keep is only read by the
// layout.
function go(target) {
    if (target.find) {
        goFound(target.find)
        return
    }
    if (typeof target.pageMark === "number") {
        var markPage = target.pageMark < state.pageMarks.length ? markPageOf(target.pageMark) : -1
        showPage(markPage >= 0 ? markPage : 0)
        return
    }
    if (typeof target.share === "number") {
        var pages = pageCount()
        showPage(Math.min(pages - 1, Math.ceil(target.share * pages - 1e-6)))
        return
    }
    var el = target.id ? state.doc.getElementById(target.id) : null
    var page = el || !(target.offset >= 0) ? -1 : pageOfOffset(target.offset)
    if (el)
        showPage(pageOf(el))
    else if (page >= 0)
        showPage(page)
    else if (target.end)
        showPage(pageCount() - 1)
    else
        showPage(Math.round((target.fraction || 0) * (pageCount() - 1)))
}

function showPage(page) {
    var pages = pageCount()
    state.scroller.scrollLeft = Math.max(0, Math.min(pages - 1, page)) * state.width
    // Report where the view really is, should the scroll be clamped.
    page = currentPage()
    var text = firstTextOn(page)
    // The view has another size than this layout was made for (the phone
    // is turning): the middle of the screen is elsewhere in the text.
    var stale = content.innerWidth !== state.viewWidth || content.innerHeight !== state.viewHeight
    sendAsyncMessage("bookfish:page", {
        serial: state.serial,
        page: page,
        pages: pages,
        firstId: firstSentenceStartingOn(page),
        pageMark: pageMarkAt(page),
        offset: text.offset,
        offsetOnPage: text.onPage,
        fraction: pages > 1 ? page / (pages - 1) : 0,
        textScale: state.textScale,
        // Where the page is held when the screen turns: measured now, while
        // the screen and the layout still agree.
        middle: stale ? -1 : middleOffset(page, state.margin),
        stale: stale,
        viewWidth: state.viewWidth,
        viewHeight: state.viewHeight,
        pixelRatio: content.devicePixelRatio || 1
    })
}

// Trailing whitespace inside a sentence can produce empty boxes on the next
// page; they do not count.
function boxes(el) {
    return Array.prototype.filter.call(el.getClientRects(), function (r) {
        return r.width >= 1 && r.height >= 1
    })
}

function pageOfBox(rect) {
    return Math.floor((rect.left + state.scroller.scrollLeft) / state.width)
}

function pageOf(el) {
    var first = boxes(el)[0] || el.getBoundingClientRect()
    return pageOfBox(first)
}

// The topmost sentence visible on the page, also if it is cut off at the top.
function firstSentenceOn(page) {
    for (var i = 0; i < state.sentences.length; ++i) {
        var rects = boxes(state.sentences[i])
        if (rects.length === 0)
            continue
        if (pageOfBox(rects[0]) > page)
            return ""
        if (pageOfBox(rects[rects.length - 1]) >= page)
            return state.sentences[i].id
    }
    return ""
}

// The first sentence that starts on the page. It brings back exactly this
// page; a sentence cut off at the top starts on the previous one. "" if no
// sentence starts here, then the fraction of the chapter is used.
function firstSentenceStartingOn(page) {
    for (var i = 0; i < state.sentences.length; ++i) {
        var rects = boxes(state.sentences[i])
        if (rects.length === 0)
            continue
        var start = pageOfBox(rects[0])
        if (start === page)
            return state.sentences[i].id
        if (start > page)
            return ""
    }
    return ""
}
