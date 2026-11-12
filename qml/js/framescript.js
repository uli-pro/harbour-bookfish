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
    // Laid out again (new text size): replace our style and stay with the
    // sentence at the top of the page, even if it began on the page before.
    // The first sentence starting on the page would drift forward.
    var style = current() ? state.style : null
    if (style && target.keep) {
        var top = firstSentenceOn(currentPage())
        target = { id: top, offset: firstOffsetOn(currentPage()), fraction: target.fraction }
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
        "  column-width: " + (width - 2 * margin) + "px; column-gap: " + (2 * margin) + "px; column-fill: auto;" +
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
        // Links cannot be followed, so they look like the text around them.
        "body a, body a:link, body a:visited { color: inherit; text-decoration: none; }" +
        // Books are made for white pages: their own black text or light
        // backgrounds would be unreadable on a black one. A rule may be drawn
        // with its background.
        (o.background === "black" ? "body h|*:not(h|hr) { color: inherit; background-color: transparent; }" : "") +
        // Our own mark for the sentence spoken, and for the one heard last
        // where listening goes on: the book's style for its active class is
        // made for white pages.
        "body .bookfish-active, body .bookfish-resume { background-color: " + o.markColor + "; }")
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
        width: width,
        // The WebView enlarges text by itself (measured: 1.6); the settings
        // page shows its sample at the size the reader sees. A page Gecko
        // could not parse has no body.
        textScale: doc.body ? parseFloat(content.getComputedStyle(doc.body).fontSize) / fontSize : 0,
        sentences: sentences,
        isSentence: isSentence,
        active: active,
        resume: resume,
        // The text found, kept to select it again (see remark).
        found: found,
        // See textNodes().
        texts: null
    }
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
        if (first !== currentPage())
            showPage(first)
    }
    sendAsyncMessage("bookfish:highlighted", { serial: state.serial, id: id, splits: splits })
}

addMessageListener("bookfish:highlight", function (message) {
    if (current())
        highlight(message.data.id)
})

addMessageListener("bookfish:show", function (message) {
    if (current() && message.data.page !== currentPage())
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
        fitTables(doc, o.margin)
        splitTallTables(doc)
    } catch (e) { }
}

// Only outer tables: a nested one goes along with the one around it.
function outerTables(doc) {
    return Array.prototype.filter.call(doc.body.getElementsByTagName("table"), function (table) {
        return table.namespaceURI === xhtml && !table.parentElement.closest("table")
    })
}

// A table is at least as wide as the longest words of its columns together;
// overflow-wrap: break-word does not change that. What sticks out of a column
// is drawn in the next one, on the next page. So a table too wide gives up its
// own width, then shrinks its text; breaking words is the last resort, below
// minTableScale: small text reads better than broken words.
var minTableScale = 0.4

function fitTables(doc, margin) {
    var tables = outerTables(doc)
    // All reads before all writes: one reflow per round, however many tables.
    function tooWide(list) {
        // Not innerWidth: rounded, and far into a long chapter the small
        // difference would put a box on the wrong page.
        var width = doc.body.getBoundingClientRect().width
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

function currentPage() {
    return Math.round(state.scroller.scrollLeft / state.width)
}

// Turning pages or listening: the found text and the sentence heard last
// are no longer what the reader looks at.
function unmark() {
    state.found = null
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
function remark() {
    if (!state.found)
        return
    var selection = content.getSelection()
    selection.removeAllRanges()
    selection.addRange(state.found)
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
    var texts = textNodes()
    if (!texts)
        return null
    var nodes = texts.nodes
    var starts = texts.starts
    var all = texts.all
    var at = find.offset
    if (all.substr(at, find.length) !== find.text) {
        var after = all.indexOf(find.text, at)
        var before = all.lastIndexOf(find.text, at)
        if (after < 0 && before < 0)
            return null
        at = after < 0 ? before : before < 0 ? after : (after - at <= at - before ? after : before)
    }
    var end = at + find.text.length
    var range = state.doc.createRange()
    for (var i = 0; i < nodes.length; ++i) {
        var nodeEnd = starts[i] + nodes[i].length
        if (at >= starts[i] && at < nodeEnd)
            range.setStart(nodes[i], at - starts[i])
        if (end > starts[i] && end <= nodeEnd) {
            range.setEnd(nodes[i], end - starts[i])
            break
        }
    }
    return range
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
    // In the order textContent joins them.
    var walker = state.doc.createTreeWalker(body, 4 | 8)
    for (var n = walker.nextNode(); n; n = walker.nextNode()) {
        nodes.push(n)
        starts.push(all.length)
        all += n.data
    }
    state.texts = { nodes: nodes, starts: starts, all: all }
    return state.texts
}

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
    var range = findRange(find)
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
        state.found = range
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
// found counts), { end: true } or { find } (see findRange); keep is only
// read by the layout.
function go(target) {
    if (target.find) {
        goFound(target.find)
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
    sendAsyncMessage("bookfish:page", {
        serial: state.serial,
        page: page,
        pages: pages,
        firstId: firstSentenceStartingOn(page),
        offset: text.offset,
        offsetOnPage: text.onPage,
        fraction: pages > 1 ? page / (pages - 1) : 0,
        textScale: state.textScale
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
