import QtQuick 2.0
import Sailfish.Silica 1.0
import Sailfish.WebView 1.0
import Sailfish.WebEngine 1.0
import "../components"

WebViewPage {
    id: page

    property var book
    // chapter is the one in the WebView; requested the one being prepared.
    property int chapter: -1
    property int requested: -1
    property var sentenceIds: []
    // The clips of the chapter in the view, for starting playback there.
    property var sentenceClips: []
    property var pendingTarget: null
    property string loadingUrl: ""
    // Messages from the frame script carry the serial of their layout, so
    // late messages about a previous chapter are recognised and dropped.
    property int serial: 0
    property bool ready: false
    property bool covered: true
    // The settings of the last layout; another layout follows if they
    // changed while one was under way.
    property string laidOut: ""
    // A relayout asked for while a layout was under way, see relayout().
    property bool relayoutWanted: false
    property int pageIndex: 0
    property int pageCount: 0
    property string firstId: ""
    // Where the page shown begins in the text of chapter topChapter
    // (UTF-16), or the text after it if it holds none (see framescript.js
    // firstTextOn); with no text after it either, the last one known in the
    // chapter. Kept apart from chapter, which changes as soon as another
    // chapter is asked for: until it is shown, this is the place left.
    property int topChapter: -1
    property int topOffset: -1
    property bool topOffsetOnPage: false
    // Page numbers across the book are estimated: only the current chapter
    // is laid out, the others are counted by their characters. Python counts
    // them once the first chapter is shown, so opening is not delayed.
    property var chapterChars: []
    property bool countingChars: false
    property real charsPerPage: 0
    property int bookPage: 0
    property int bookPages: 0
    // The page of the printed book shown in the corner: from the book's
    // page list (book.pages, see pages.py), else estimated by characters.
    // pageMark is the frame script's mark in effect on the page shown
    // (index in book.pages.marks[topChapter]). pageTotal 0: no total.
    property int pageMark: -1
    property string pageLabel: ""
    property int pageTotal: 0
    property bool pageEstimated: false
    property real fraction: 0
    // Chosen in the settings; until then as the ambience.
    readonly property bool lightPage: app.pageColors === "light"
                                      || (app.pageColors === "" && Theme.colorScheme === Theme.DarkOnLight)
    readonly property color pageColor: lightPage ? "white" : "black"

    // Listening. The bar appears with playback and goes when the reader
    // turns pages while paused.
    property bool barShown: false
    // The sentence spoken (or paused at), marked while listening.
    property string highlightId: ""
    // Further pages of the sentence spoken: [{page, share}], see framescript.js.
    property var splits: []
    // The next chapter with audio, read ahead: {after, chapter, clips};
    // chapter -1 at the end of the book.
    property var upcoming: null
    // Sentence heard last before the book was closed; listening resumes there.
    property string resumeId: ""
    // The sentence of the place jumped to from the search; Play starts there.
    property string jumpId: ""
    // Going from hit to hit: the hits of the last search, the one shown, and
    // the words, shown again on the search page. The bar shows while the
    // reader looks through the hits.
    property var findHits: []
    property int findIndex: -1
    property string findQuery: ""
    property bool findShown: false
    // The page flip view. While it is open the reading page is
    // browsing: the view may load other chapters to draw their pages, and
    // the place read, the history and the corner stay as they were. Its
    // bar's stops (see bridge.flip_stops) are read once. flipOrigin is the
    // place it was opened at; gridCenter the screen page in the middle
    // ({chapter, page}); pageCounts the screen pages of each chapter laid
    // out, thumbCache the pages drawn ("chapter:page" → {url, mark}), both
    // in this layout. browseIntent says what the next page report is for:
    // "center" shows the page for the middle, "fill" a chapter to draw.
    property bool flipShown: false
    property bool browsing: false
    property var flipStops: []
    property bool flipEstimated: false
    property int flipSerial: -1
    property var flipOrigin: null
    property var gridCenter: null
    property var pageCounts: ({})
    property var thumbCache: ({})
    property var gridTiles: []
    property string browseIntent: ""
    // Another chapter was loaded or the page moved: closing goes back.
    property bool browseMoved: false
    // One drawing asked of the frame script at a time; gridGen tells
    // answers to a view closed meanwhile.
    property bool drawAsked: false
    property int gridGen: 0
    // A stop of the bar to go to once the page asked for before is shown.
    property int pendingStop: -1
    // The stop shown for the middle until its page is drawn.
    property int lastStop: -1
    // Play pressed while browsing: from the page read, once it is back.
    property bool playAfterLoad: false
    readonly property bool flipAllowed: controls.mode === "read" || controls.mode === "find"
    onFlipAllowedChanged: {
        if (!flipAllowed)
            closeFlip()
    }
    onOrientationChanged: closeFlip()
    // A stop of the page flip view typed in (GoToPageDialog), gone to
    // once this page is back.
    property int pendingFlip: -1
    // A hit chosen in the list, shown once this page is back.
    property int pendingHit: -1
    // An entry of the history chosen, likewise; see FindPage.
    property var pendingPlace: null
    // Text selected by a long press (see framescript.js selectionAnswer):
    // where its ends are on the view, as shares of it, and its text; null
    // if none. Its actions replace the other controls while it lasts.
    property var selection: null
    readonly property bool selecting: selection !== null
    // Dragging a handle: the latest point not yet sent, and whether an
    // answer is awaited; one move at a time, the latest wins.
    property var pendingMove: null
    property bool moveAsked: false
    // Making a bookmark from the selection, until it is stored: a second tap
    // must not make another.
    property bool taking: false
    // Looking up the selection: it stays while the dictionary is shown, so
    // that a handle can be moved and the words looked up again.
    property bool lookingUp: false
    // The bookmarks and notes of the book, in its order (see bookmarks.py).
    property var bookmarks: []
    // The audiobook of this EPUB, see bridge.partner; null if none.
    property var partner: null
    // Offering to go where the audiobook was listened to last.
    property bool partnerShown: false
    // Going there from the history, once this page is back.
    property bool pendingPartner: false
    // Pages turned, a jump or listening since the place was saved: the
    // book has been used. A layout alone moves the page a little.
    property bool moved: false
    readonly property bool listening: player.active && player.chapter === chapter
    // A table's picture is being stored, see showTable().
    property bool tableSaving: false
    // The sentence spoken and the one before it, with the time until which
    // a tap on that one still pauses (see isSpoken()). Until startedUntil a
    // tap does not pause: it repeats one that seemed to do nothing while the
    // sentence it started was being loaded.
    property real startedUntil
    property string spokenId
    property int spokenChapter: -1
    property string previousId
    property int previousChapter: -1
    property real previousUntil
    readonly property bool playing: player.playing
    readonly property bool hasAudio: book.spine.some(function (item) { return !!item.overlay })
    // For the lock screen and headphone controls.
    readonly property string coverUrl: book.cover ? player.fileUrl(book.cover) : ""
    // The chapter heard, or read; for the lock screen.
    readonly property string chapterTitle: tocTitle(player.active ? player.chapter : chapter)
    property double savedAt: 0
    // Left for the library: the page is going, and must neither lay out
    // nor save again (it would save the top of the page over the sentence).
    property bool closed: false
    // How the next end of listening goes into the history, if not as the
    // player says: "timer", "close" or "end".
    property string stopKind: ""
    // Reading, for the history: a session is open from the first page
    // turned or jump made while nothing plays, until listening, leaving the
    // app or the book. Pages turned since the last entry, and since the
    // last jump: going from hit to hit notes only the place left first.
    property bool reading: false
    property bool turnedSinceEntry: false
    property bool turnedSinceJump: true
    // When reading last ended by leaving the app; coming back soon goes on
    // with the same session (see history.SHORT_PAUSE).
    property double awayAt: 0
    // The place of the last reading entry, "spine:offset".
    property string notedPlace: ""

    // Turning the phone. Where the notch is on this page: "top", "bottom"
    // (upside down), "left", "right"; "" without one in the middle of an edge.
    readonly property string notchSide: !app.middleNotch ? ""
                                        : orientation === Orientation.Landscape ? "left"
                                        : orientation === Orientation.LandscapeInverted ? "right"
                                        : orientation === Orientation.PortraitInverted ? "bottom" : "top"
    // As deep as the notch reaches into the screen.
    readonly property real notchDepth: Screen.hasCutouts === true && Screen.topCutout.height > 0
                                       ? Screen.topCutout.y + Screen.topCutout.height : 0
    // In landscape the text takes two columns, if so chosen.
    readonly property int columns: isLandscape ? app.landscapeColumns : 1
    // CSS pixels to screen pixels in the view, as the frame script reports.
    property real pixelRatio: 1
    // The view's size the chapter was laid out for, and the one Gecko has
    // now; both in CSS pixels. Gecko gets a new size up to a second after
    // Qt (measured on turning the phone), see geckoSettled.
    property real laidWidth: 0
    property real laidHeight: 0
    property real geckoWidth: 0
    property real geckoHeight: 0
    // The place held when the page is laid out for another size: the start
    // of the middle line of the page shown (two columns: the left one),
    // measured while it was shown, as the screen still matched the layout.
    property int anchorChapter: -1
    property int anchorOffset: -1
    // Covered for turning the phone: taps would act on a page not shown.
    property bool turning: false
    // The first page painted: the book is reopened at the next start (see
    // positions.load_last).
    property bool shown: false
    onCoveredChanged: {
        if (covered)
            return
        turning = false
        if (!shown) {
            shown = true
            py.call("bookfish.bridge.book_shown", [app.positionsFile])
        }
    }

    // Turning pages needs the horizontal swipe; the library is in the pulley.
    backNavigation: false
    allowedOrientations: app.pageOrientations
    // In landscape the notch is beside the text; the page keeps the strip
    // there free itself and shows the page number in it.
    cutoutMode: isLandscape && app.middleNotch ? CutoutMode.FullScreen : CutoutMode.AvoidLandscapeCutout

    // While the screen turns, the old page would show stretched; it stays
    // covered until laid out for the new size and painted. Turning between
    // the two landscape sides keeps the size: then it shows again at once.
    onOrientationTransitionRunningChanged: {
        if (orientationTransitionRunning) {
            turning = true
            covered = true
            uncoverTimer.stop()
            paintedTimer.stop()
            turnedTimer.stop()
        } else if (ready && geckoSettled.sizeMatches(laidWidth, laidHeight)) {
            covered = false
        } else {
            turnedTimer.restart()
        }
    }

    function fileUrl(path) {
        return "file://" + path.split("/").map(encodeURIComponent).join("/")
    }

    // A readaloud is its own audiobook.
    function start() {
        loadBookmarks()
        if (hasAudio) {
            resume()
            return
        }
        py.call("bookfish.bridge.partner", [book.path, app.libraryCache, app.positionsFile],
                function (found) {
            if (typeof page === "undefined" || !page)
                return
            partner = found
            resume()
        })
    }

    function resume() {
        py.call("bookfish.bridge.load_position", [app.positionsFile, book.key], function (pos) {
            if (typeof page === "undefined" || !page)
                return  // the page was closed meanwhile
            partnerShown = app.partnerOffered(pos, partner)
            if (pos && pos.spine < book.spine.length) {
                if (pos.heard)
                    resumeId = pos.id
                loadChapter(pos.spine, { id: pos.id, offset: pos.offset, fraction: pos.fraction })
            } else
                loadChapter(Math.max(0, nextLinear(-1, 1)), { fraction: 0 })
        })
    }

    // target: where to go in the chapter, see go() in framescript.js
    function loadChapter(index, target) {
        // The frame script drops it with the jump or the new chapter.
        selection = null
        if (index === chapter && ready) {
            flickable.webView.sendAsyncMessage("bookfish:goto", { target: target })
            return
        }
        var item = book.spine[index]
        requested = index
        serial++
        ready = false
        covered = true
        // Timers of the layout before must not uncover the new chapter.
        uncoverTimer.stop()
        paintedTimer.stop()
        turnedTimer.stop()
        if (!item.overlay) {
            show(index, [], [], target)
            return
        }
        py.call("bookfish.bridge.read_chapter", [book.root, item.path, item.overlay], function (result) {
            if (typeof page === "undefined" || !page || requested !== index)
                return  // page closed, or another chapter was asked for meanwhile
            if (result.error) {
                // The text can still be read without sentences.
                console.warn("Cannot read overlay", item.overlay, result.error, result.detail)
                show(index, [], [], target)
            } else {
                show(index, result.ids, result.sentences, target)
            }
        })
    }

    function show(index, ids, clips, target) {
        chapter = index
        requested = -1
        sentenceIds = ids
        sentenceClips = clips
        pendingTarget = target
        var view = flickable.webView
        var url = fileUrl(book.root + "/" + book.spine[index].path)
        if (view.url.toString() === url) {
            // Still loading: that load will be laid out with the new target.
            if (loadingUrl === url)
                return
            // Setting the same URL again would not load anything.
            loadingUrl = url
            view.reload()
        } else {
            loadingUrl = url
            view.url = url
        }
    }

    function layoutSettings() {
        return [app.fontSize, app.fontFamily, app.lineHeight, app.paragraphSpacing,
                app.textAlign, lightPage, app.controlsAtBottom, app.controlsScale].join("|")
    }

    function layout(target) {
        laidOut = layoutSettings()
        relayoutWanted = false
        // From lightPage itself: the palette and pageColor may still hold
        // the old colours while lightPage changes (seen on the device).
        var light = lightPage
        // While listening the page shows the sentence spoken; paused, it
        // stays where the reader is.
        if (listening && player.playing && highlightId)
            target = { id: highlightId }
        flickable.webView.sendAsyncMessage("bookfish:layout", {
            serial: serial,
            ids: sentenceIds,
            target: target,
            // Paused and turned away, the sentence would pull the page back.
            highlight: listening && barShown ? highlightId : "",
            resume: !player.active ? resumeId : "",
            // Highlighter yellow: the ambience's colour may be too dark to
            // see on a black page. Dimmed there, so white text stays legible.
            markColor: light ? "rgba(255,225,0,0.55)" : "rgba(230,190,0,0.45)",
            marks: chapterMarks(chapter),
            pageMarks: pageMarksOf(chapter),
            underlineColor: light ? "rgba(0,0,0,0.5)" : "rgba(255,255,255,0.55)",
            margin: 24,
            marginTop: 4,
            // Below the text the controls' row is margin enough; above it
            // they cover nothing. In landscape there are none.
            marginBottom: isPortrait && app.controlsAtBottom ? 0 : 12,
            barHeight: isPortrait && app.controlsAtBottom ? controls.height : 0,
            columns: columns,
            fontSize: app.fontSize,
            fontFamily: app.fontFamily === "serif" ? "serif" : "sans-serif",
            lineHeight: app.lineHeight,
            paragraphSpacing: app.paragraphSpacing,
            justify: app.textAlign === "justify",
            language: book.language || "",
            color: light ? "black" : "white",
            background: light ? "white" : "black"
        })
    }

    // Same chapter and place, new settings or size. While a layout is under way
    // the "page" message calls this again if the size has changed meanwhile.
    function relayout() {
        if (closed)
            return
        // The pictures drawn no longer fit: back to the page read.
        closeFlip()
        // Under way: done after it ("page"); it may have begun before the
        // view took a new height.
        if (!ready) {
            relayoutWanted = true
            return
        }
        // The frame script drops it with the layout.
        selection = null
        serial++
        ready = false
        covered = true
        // Timers of the layout before must not uncover this one.
        uncoverTimer.stop()
        paintedTimer.stop()
        charsPerPage = 0
        // Page numbers of the old layout no longer fit.
        splits = []
        if (listening)
            player.setMarks([])
        turnedTimer.stop()
        // The place measured while it was shown; the frame script could
        // measure it now only if the view still had the size it was laid
        // out for (not after turning the phone).
        if (anchorChapter === chapter && anchorOffset >= 0)
            layout({ offset: anchorOffset, fraction: fraction })
        else if (geckoWidth > 0 && (geckoWidth !== laidWidth || geckoHeight !== laidHeight))
            layout({ id: firstId, fraction: fraction })
        else
            layout({ keep: true, id: firstId, fraction: fraction })
    }

    function estimatedPages(index) {
        var perPage = charsPerPage
        if (perPage <= 0) {
            // Nothing laid out yet: assume half a text size per character
            // and 1.3 per line on the screen area.
            perPage = ((flickable.width - 2 * Theme.horizontalPageMargin) / (0.5 * app.fontSize))
                    * (flickable.height / (1.3 * app.fontSize))
        }
        return Math.max(1, Math.round(chapterChars[index] / perPage))
    }

    function updateBookPages() {
        if (chapterChars.length !== book.spine.length) {
            updatePageNumber()
            if (!countingChars) {
                countingChars = true
                var paths = book.spine.map(function (item) { return item.path })
                py.call("bookfish.bridge.chapter_lengths", [book.root, paths], function (lengths) {
                    if (typeof page === "undefined" || !page)
                        return
                    chapterChars = lengths
                    updateBookPages()
                    // Now with progress; not while a chapter is loading,
                    // whose place is not known yet.
                    if (ready)
                        savePosition()
                })
            }
            return
        }
        // Browsing: the chapter laid out is not the one whose page is shown.
        if (browsing) {
            updatePageNumber()
            return
        }
        var spine = book.spine
        // Short chapters (titles, pictures) say little about a full page.
        if (chapterChars[chapter] >= 1000 && pageCount > 1)
            charsPerPage = chapterChars[chapter] / pageCount
        var before = 0
        var after = 0
        for (var i = 0; i < spine.length; ++i) {
            // Chapters outside the reading order are never paged through.
            if (i === chapter || !spine[i].linear)
                continue
            if (i < chapter)
                before += estimatedPages(i)
            else
                after += estimatedPages(i)
        }
        bookPage = before + pageIndex + 1
        bookPages = before + pageCount + after
        updatePageNumber()
    }

    function pageMarksOf(index) {
        var marks = book.pages ? book.pages.marks[index] : null
        return marks ? marks.map(function (mark) { return mark[0] }) : []
    }

    // Of the page last reported (topChapter), so a chapter asked for but
    // not shown yet does not mix with the old chapter's mark.
    function updatePageNumber() {
        var pages = book.pages
        if (pages) {
            var marks = pages.marks[topChapter]
            var entry = marks && pageMark >= 0 && pageMark < marks.length ? marks[pageMark].slice(1)
                                                                         : pages.start[topChapter]
            pageEstimated = false
            pageLabel = entry ? entry[0] : ""
            pageTotal = entry && entry[1] ? pages.total : 0
            return
        }
        pageEstimated = true
        pageLabel = estimatedPage(topChapter, pageIndex, pageCount)
        pageTotal = pageLabel !== "" ? estimatedTotal() : 0
    }

    // Measured on the library's page lists: German books print
    // 1590 characters a page (median), English ones 1690. As
    // pages.chars_per_page, which counts the pages in lists.
    function printedPageChars() {
        return (book.language || "").toLowerCase().indexOf("de") === 0 ? 1600 : 1700
    }

    function estimatedTotal() {
        var total = 0
        for (var i = 0; i < chapterChars.length; ++i) {
            if (book.spine[i].linear)
                total += chapterChars[i]
        }
        return Math.max(1, Math.ceil(total / printedPageChars()))
    }

    // The estimated printed page for screen page k of n in chapter c: as
    // with a page list, the last page beginning on the screen, which is the
    // page of its last character. Going to a page (framescript.js go,
    // share) shows the screen where it begins, which then says so. "" while
    // the chapters' characters are not counted.
    function estimatedPage(c, k, n) {
        if (chapterChars.length !== book.spine.length || c < 0 || c >= book.spine.length)
            return ""
        var before = 0
        for (var i = 0; i < c; ++i) {
            if (book.spine[i].linear)
                before += chapterChars[i]
        }
        var length = book.spine[c].linear ? chapterChars[c] : 0
        var end = n > 0 ? (k + 1) / n : 0
        return String(Math.max(1, Math.min(estimatedTotal(),
                                           Math.floor((before + end * length - 1) / printedPageChars()) + 1)))
    }

    // wide: in landscape, with spaces.
    function pageNumberText(wide) {
        if (!pageLabel)
            return ""
        if (!pageTotal)
            return pageLabel
        if (pageEstimated)
            //: Estimated page of the printed book in landscape, e.g. "≈ 30 / 295"
            return wide ? qsTr("≈ %1 / %2").arg(pageLabel).arg(pageTotal)
                          //: Estimated page of the printed book, e.g. "≈30/295"
                        : qsTr("≈%1/%2").arg(pageLabel).arg(pageTotal)
        //: Page of the printed book in landscape, e.g. "30 / 295"
        return wide ? qsTr("%1 / %2").arg(pageLabel).arg(pageTotal)
                      //: Page of the printed book, e.g. "30/295"
                    : qsTr("%1/%2").arg(pageLabel).arg(pageTotal)
    }

    // The stop of the page flip view for the page shown: the one of the
    // printed page in the corner (pageMark in chapter), else the last one
    // before it; for estimated pages the page's number.
    function currentStop(stops, chapter, mark, label) {
        if (stops.length === 0)
            return -1
        if (flipEstimated) {
            var n = parseInt(label, 10)
            return isNaN(n) ? 0 : Math.max(0, Math.min(stops.length - 1, n - 1))
        }
        var found = 0
        for (var i = 0; i < stops.length; ++i) {
            var stop = stops[i]
            if (stop.spine > chapter || (stop.spine === chapter && stop.mark > mark))
                break
            found = i
        }
        return found
    }

    function toggleFlip() {
        if (flipShown)
            closeFlip()
        else
            openFlip()
    }

    function openFlip() {
        if (!ready || requested >= 0 || topChapter !== chapter || !flipAllowed)
            return
        // The line in the middle of the page, as when laying out anew:
        // closing shows this very page again.
        flipOrigin = { spine: topChapter,
                       offset: anchorChapter === topChapter && anchorOffset >= 0 ? anchorOffset
                               : topOffsetOnPage ? topOffset : -1,
                       fraction: fraction }
        var counts = {}
        counts[chapter] = pageCount
        pageCounts = counts
        thumbCache = {}
        gridGen++
        drawAsked = false
        pendingStop = -1
        browseIntent = ""
        browseMoved = false
        gridCenter = { chapter: chapter, page: pageIndex }
        lastStop = currentStop(flipStops, topChapter, pageMark, pageLabel)
        browsing = true
        flipShown = true
        if (flipStops.length === 0 && flipSerial < 0) {
            flipSerial = ++app.searchSerial
            py.call("bookfish.bridge.flip_stops", [book.root, flipSerial])
        }
        fillGrid()
    }

    function endBrowsing() {
        holdTimer.stop()
        browsing = false
        flipShown = false
        gridTiles = []
        thumbCache = {}
        gridGen++
        pendingStop = -1
        browseIntent = ""
    }

    // Back to where the view was opened, the very line; not a jump.
    function closeFlip() {
        if (!flipShown)
            return
        var origin = flipOrigin
        var moved = browseMoved
        var left = chapter !== (origin ? origin.spine : -1) || requested >= 0
        endBrowsing()
        if (!moved || !origin)
            return
        // Another chapter was laid out: the hit looked at is marked anew
        // (the bar still shows it). The sentence heard last comes back with
        // the layout; bookmarks too.
        var hit = findShown && findIndex >= 0 ? findHits[findIndex] : null
        if (left && hit && hit.spine === origin.spine)
            loadChapter(origin.spine, { find: { offset: hit.offset, length: hit.length, text: hit.text } })
        else
            loadChapter(origin.spine, origin.offset >= 0
                        ? { offset: origin.offset, fraction: origin.fraction, browse: true }
                        : { fraction: origin.fraction, browse: true })
    }

    // Reading on at a page of the view: a jump, as from the contents.
    function openTile(index) {
        var tile = browsing ? gridTiles[index] : null
        if (!tile || tile.page < 0)
            return
        // The page read itself: nothing to go to.
        if (!browseMoved && tile.chapter === flipOrigin.spine && tile.page === pageIndex) {
            closeFlip()
            return
        }
        endBrowsing()
        findShown = false
        jumpTo(tile.chapter, { page: tile.page })
    }

    // A page typed in: read there.
    function flipTo(index) {
        var stop = flipStops[index]
        if (!stop)
            return
        endBrowsing()
        findShown = false
        jumpTo(stop.spine, stopTarget(stop))
    }

    // Going there while browsing keeps what is marked on the page read.
    function browseTarget(target) {
        target.browse = true
        return target
    }

    function stopTarget(stop) {
        return flipEstimated ? { share: stop.share } : stop.mark >= 0 ? { pageMark: stop.mark } : { fraction: 0 }
    }

    // The screen page d pages from the page from ({chapter, page}) in
    // reading order: {chapter, page}, page -1 if a chapter on the way is
    // not laid out yet (that chapter); null beyond the book.
    function gridLocate(from, d) {
        var c = from.chapter
        var p = from.page + d
        // Chapters may be empty; never more steps than chapters.
        for (var steps = 0; steps <= book.spine.length; ++steps) {
            var n = pageCounts[c]
            if (n === undefined)
                return { chapter: c, page: -1 }
            if (p < 0) {
                var before = nextLinear(c, -1)
                if (before < 0)
                    return null
                c = before
                if (pageCounts[c] === undefined)
                    return { chapter: c, page: -1 }
                p += pageCounts[c]
            } else if (p >= n) {
                var after = nextLinear(c, 1)
                if (after < 0)
                    return null
                p -= n
                c = after
            } else {
                return { chapter: c, page: p }
            }
        }
        return null
    }

    // Shows what is there for the nine pages around the middle and draws or
    // loads what is missing, nearest the middle first: pages of the chapter
    // laid out by the frame script, others by loading their chapter.
    function fillGrid() {
        if (!browsing || !gridCenter)
            return
        var at = []
        var tiles = []
        for (var i = 0; i < 9; ++i) {
            var place = gridLocate(gridCenter, i - 4)
            at.push(place)
            if (!place) {
                tiles.push(null)
                continue
            }
            var hit = place.page >= 0 ? thumbCache[place.chapter + ":" + place.page] : null
            tiles.push({ chapter: place.chapter, page: place.page, url: hit ? hit.url : "",
                         label: place.page >= 0 ? tileLabel(place.chapter, place.page, hit ? hit.mark : -2) : "" })
        }
        gridTiles = tiles
        var here = []
        var load = -1
        var nearest = [4, 3, 5, 2, 6, 1, 7, 0, 8]
        for (i = 0; i < nearest.length; ++i) {
            place = at[nearest[i]]
            if (!place || (place.page >= 0 && thumbCache[place.chapter + ":" + place.page]))
                continue
            if (place.page >= 0 && place.chapter === chapter)
                here.push(place.page)
            else if (load < 0)
                load = place.chapter
        }
        if (drawAsked || requested >= 0 || !ready || browseIntent !== "")
            return
        // All nine there: further pages of this chapter, a few at a time,
        // so swiping on shows them at once.
        if (here.length === 0 && load < 0) {
            for (var d = 5; d <= 16 && here.length < 6; ++d) {
                [d, -d].forEach(function (step) {
                    var ahead = gridLocate(gridCenter, step)
                    if (ahead && ahead.page >= 0 && ahead.chapter === chapter
                            && !thumbCache[ahead.chapter + ":" + ahead.page] && here.length < 6)
                        here.push(ahead.page)
                })
            }
        }
        if (here.length > 0) {
            drawAsked = true
            flickable.webView.sendAsyncMessage("bookfish:drawPages", {
                serial: serial, gen: gridGen, pages: here, width: flipGrid.cellWidth
            })
        } else if (load >= 0 && load !== chapter) {
            browseIntent = "fill"
            browseMoved = true
            loadChapter(load, browseTarget({ fraction: 0 }))
        }
    }

    // The printed page shown below a picture: mark is the frame script's
    // (see pageMarkAt), -2 while the page is not drawn.
    function tileLabel(c, k, mark) {
        var pages = book.pages
        if (!pages) {
            var label = estimatedPage(c, k, pageCounts[c] || 1)
            //: Estimated page of the printed book below a picture of the page flip view, e.g. "≈143"
            return label ? qsTr("≈%1").arg(label) : ""
        }
        if (mark === -2)
            return ""
        var marks = pages.marks[c]
        var entry = marks && mark >= 0 && mark < marks.length ? marks[mark].slice(1) : pages.start[c]
        return entry ? entry[0] : ""
    }

    // The stop of the bar for the page in the middle, -1 until known.
    function gridStop() {
        if (!gridCenter || flipStops.length === 0)
            return -1
        var c = gridCenter.chapter
        if (flipEstimated)
            return currentStop(flipStops, c, -1, estimatedPage(c, gridCenter.page, pageCounts[c] || 1))
        var hit = thumbCache[c + ":" + gridCenter.page]
        return hit ? currentStop(flipStops, c, hit.mark, "") : lastStop
    }

    // Dragging the bar: the page of the stop to the middle; in the chapter
    // laid out at once, else once the finger rests or lets go.
    function dragStop(index) {
        if (!browsing)
            return
        pendingStop = index
        var stop = flipStops[index]
        if (stop && stop.spine === chapter && ready && requested < 0)
            centerOnStop()
        else
            holdTimer.restart()
    }

    function chooseStop(index) {
        // Let go (or cancelled) where the middle already is: it stays.
        if (!browsing || (index === flipGrid.current && pendingStop < 0 && !holdTimer.running))
            return
        pendingStop = index
        centerOnStop()
    }

    // One at a time: the page report goes on with the latest stop.
    function centerOnStop() {
        holdTimer.stop()
        if (!browsing || pendingStop < 0 || browseIntent === "center")
            return
        var stop = flipStops[pendingStop]
        lastStop = pendingStop
        pendingStop = -1
        if (!stop)
            return
        browseIntent = "center"
        browseMoved = true
        loadChapter(stop.spine, browseTarget(stopTarget(stop)))
    }

    function gridStep(delta) {
        if (!browsing || !gridCenter || browseIntent === "center")
            return
        var place = gridLocate(gridCenter, delta)
        if (!place)
            return
        if (place.page >= 0) {
            gridCenter = place
            fillGrid()
            return
        }
        // A chapter not laid out yet: its first or last page.
        browseIntent = "center"
        browseMoved = true
        loadChapter(place.chapter, browseTarget(delta > 0 ? { fraction: 0 } : { end: true }))
    }

    // A page reported while browsing: the chapter's pages, and the middle
    // if it was asked for.
    function browsed(data) {
        var counts = {}
        for (var key in pageCounts)
            counts[key] = pageCounts[key]
        counts[chapter] = data.pages
        pageCounts = counts
        if (browseIntent === "center") {
            browseIntent = ""
            gridCenter = { chapter: chapter, page: data.page }
            if (pendingStop >= 0) {
                centerOnStop()
                return
            }
        } else if (browseIntent === "fill") {
            browseIntent = ""
        }
        fillGrid()
    }

    function thumbsDrawn(data) {
        if (data.gen !== gridGen)
            return
        drawAsked = false
        if (!browsing || data.serial !== serial) {
            fillGrid()
            return
        }
        var keep = {}
        if (Object.keys(thumbCache).length > 100) {
            // Only the pages shown stay.
            gridTiles.forEach(function (tile) {
                if (tile && tile.page >= 0)
                    keep[tile.chapter + ":" + tile.page] = true
            })
        }
        var cache = {}
        for (var key in thumbCache) {
            if (Object.keys(keep).length === 0 || keep[key])
                cache[key] = thumbCache[key]
        }
        data.thumbs.forEach(function (thumb) {
            cache[chapter + ":" + thumb.page] = { url: thumb.url, mark: thumb.mark }
        })
        thumbCache = cache
        fillGrid()
    }

    function openGoToPage() {
        var dialog = pageStack.push(Qt.resolvedUrl("GoToPageDialog.qml"), {
            stops: flipStops, current: Math.max(0, flipGrid.current), estimated: flipEstimated,
            total: flipGrid.total
        })
        dialog.accepted.connect(function () {
            pendingFlip = dialog.chosen
        })
    }

    Connections {
        target: app
        onPagesFound: {
            if (serial !== page.flipSerial)
                return
            if (result.error) {
                console.warn("Cannot read the pages", result.error, result.detail)
                // Asked again on opening the view.
                page.flipSerial = -1
                return
            }
            page.flipEstimated = result.estimated
            page.flipStops = result.stops
        }
    }

    // How far into the book a place is, 0 to 1: the characters of the
    // chapters before and the share of this one by pages. The frame script
    // counts the characters of a chapter differently (with the spaces of
    // the source), so a place in it goes by pages. Chapters outside the
    // reading order (notes) are not in the audiobook and not counted. -1
    // while the lengths are not known.
    function progressAt(spine, fraction) {
        if (chapterChars.length !== book.spine.length)
            return -1
        var before = 0
        var total = 0
        for (var i = 0; i < chapterChars.length; ++i) {
            if (!book.spine[i].linear)
                continue
            if (i < spine)
                before += chapterChars[i]
            total += chapterChars[i]
        }
        if (total <= 0)
            return -1
        var length = book.spine[spine] && book.spine[spine].linear ? chapterChars[spine] : 0
        return Math.min(1, (before + fraction * length) / total)
    }

    // The other way: chapter and share of it for progress.
    function placeAt(progress) {
        var total = 0
        var last = -1
        for (var i = 0; i < chapterChars.length; ++i) {
            if (book.spine[i].linear) {
                total += chapterChars[i]
                last = i
            }
        }
        if (last < 0)
            return null
        var goal = progress * total
        for (i = 0; i < chapterChars.length; ++i) {
            if (!book.spine[i].linear)
                continue
            if (goal < chapterChars[i])
                return { spine: i, fraction: goal / chapterChars[i] }
            goal -= chapterChars[i]
        }
        return { spine: last, fraction: 1 }
    }

    // Where the audiobook was listened to last, roughly.
    function goToPartner() {
        partnerShown = false
        if (!partner)
            return
        if (chapterChars.length !== book.spine.length) {
            var paths = book.spine.map(function (item) { return item.path })
            py.call("bookfish.bridge.chapter_lengths", [book.root, paths], function (lengths) {
                if (typeof page === "undefined" || !page || closed)
                    return
                chapterChars = lengths
                goToPartner()
            })
            return
        }
        var place = placeAt(partner.progress)
        if (place)
            jumpTo(place.spine, { fraction: place.fraction })
    }

    function sameUrl(a, b) {
        try {
            return decodeURIComponent(a) === decodeURIComponent(b)
        } catch (e) {
            return a === b
        }
    }

    function handleMessage(message, data) {
        switch (message) {
        case "bookfish:loaded":
            // A load that was replaced by another one may still report.
            if (loadingUrl === "" || !sameUrl(data.url, loadingUrl))
                return
            loadingUrl = ""
            layout(pendingTarget)
            pendingTarget = null
            break
        case "bookfish:page":
            if (data.serial !== serial)
                return
            if (data.textScale > 0)
                app.setTextScale(data.textScale)
            ready = true
            if (covered && !uncoverTimer.running)
                uncoverTimer.restart()
            if (browsing) {
                pixelRatio = data.pixelRatio
                laidWidth = data.viewWidth
                laidHeight = data.viewHeight
                browsed(data)
                if (laidOut !== layoutSettings() || relayoutWanted)
                    relayout()
                break
            }
            pageIndex = data.page
            pageCount = data.pages
            firstId = data.firstId
            if (data.offset >= 0 || topChapter !== chapter)
                topOffset = data.offset
            topChapter = chapter
            topOffsetOnPage = data.offsetOnPage
            pageMark = data.pageMark
            fraction = data.fraction
            pixelRatio = data.pixelRatio
            laidWidth = data.viewWidth
            laidHeight = data.viewHeight
            if (!data.stale) {
                anchorChapter = chapter
                anchorOffset = data.middle >= 0 ? data.middle : data.offsetOnPage ? data.offset : -1
            }
            // Laid out while the phone was turning: again for the new size.
            if (laidWidth !== geckoWidth || laidHeight !== geckoHeight)
                geckoSettled.restart()
            updateBookPages()
            savePosition()
            if (playAfterLoad) {
                playAfterLoad = false
                play()
            }
            if (laidOut !== layoutSettings() || relayoutWanted)
                relayout()
            break
        case "bookfish:resized":
            geckoWidth = data.width
            geckoHeight = data.height
            geckoSettled.restart()
            break
        case "bookfish:painted":
            if (data.serial !== serial || !covered)
                return
            uncoverTimer.stop()
            paintedTimer.restart()
            break
        case "bookfish:thumbs":
            thumbsDrawn(data)
            break
        case "bookfish:edge":
            // Only the first of several quick turns past the end counts.
            if (data.serial !== serial || !ready || browsing)
                return
            var next = nextLinear(chapter, data.delta)
            if (next >= 0)
                loadChapter(next, data.delta > 0 ? { fraction: 0 } : { end: true })
            break
        case "bookfish:highlighted":
            if (data.serial !== serial || data.id !== player.currentId || !listening)
                return
            splits = data.splits
            var clip = player.clips[player.index]
            if (player.hasEnd(clip)) {
                player.setMarks(splits.map(function (split) {
                    return clip.begin + split.share * (clip.end - clip.begin)
                }))
            }
            break
        case "bookfish:found":
            if (data.serial === serial)
                jumpId = data.id
            break
        case "bookfish:selectionTaken":
            if (data.serial !== serial || !selection) {
                taking = false
                return
            }
            var mark = { spine: chapter, offset: data.offset, length: data.length, raw: data.raw,
                         quote: data.quote, note: "" }
            if (data.action === "note") {
                taking = false
                openNoteDialog(mark, null)
            } else {
                addBookmark(mark, function (ok) {
                    taking = false
                    if (ok) {
                        endSelection()
                        bookmarkNotice.show()
                    }
                })
            }
            break
        case "bookfish:selected":
            moveAsked = false
            if (data.error)
                console.warn("Cannot move the selection", data.error)
            if (data.serial !== serial || !selection)
                return
            // Dragged past the other end: the finger now moves that one.
            var dragged = handleA.dragging ? handleA : handleB.dragging ? handleB : null
            if (dragged && dragged.role !== data.moving) {
                var other = dragged === handleA ? handleB : handleA
                dragged.role = data.moving
                other.role = data.moving === "start" ? "end" : "start"
            }
            selection = data
            sendMove()
            break
        case "bookfish:hit":
            if (data.serial !== serial)
                return
            // A tap in the text ends looking through the hits; in a
            // readaloud by listening (startPlayer).
            if (!hasAudio)
                findShown = false
            if (data.id && isSpoken(data.id))
                pause()
            else if (data.id)
                playSentence(data.id)
            else if (!player.playing)
                playFromPage()
            break
        case "bookfish:pressed":
            if (data.serial !== serial || status !== PageStatus.Active) {
                // The frame script has selected the word already.
                if (data.selection)
                    flickable.webView.sendAsyncMessage("bookfish:selectClear", {})
                return
            }
            if (data.tableImage)
                showTable(data.tableImage)
            else if (data.tableError)
                console.warn("Cannot draw the table", data.tableError)
            else if (data.selection && isLandscape)
                lookUpWord(data.selection.text)
            else if (data.selection)
                startSelection(data.selection)
            else if (data.picture)
                showPicture(data.picture)
            else if (data.href)
                followLink(data.href, data.ordinal)
            break
        case "bookfish:start":
            if (data.serial !== serial)
                return
            if (data.id) {
                playSentence(data.id)
            } else {
                // Nothing to hear on this page: the next chapter with audio.
                fetchAudioChapter(chapter, function (index, clips) {
                    if (index >= 0)
                        startPlayer(index, clips, 0)
                })
            }
            break
        }
    }

    function nextAudio(from) {
        for (var i = from + 1; i < book.spine.length; ++i) {
            if (book.spine[i].linear && book.spine[i].overlay)
                return i
        }
        return -1
    }

    // Calls back with the next chapter after from that has clips, or -1.
    function fetchAudioChapter(from, callback) {
        var index = nextAudio(from)
        if (index < 0) {
            callback(-1, [])
            return
        }
        var item = book.spine[index]
        py.call("bookfish.bridge.read_chapter", [book.root, item.path, item.overlay], function (result) {
            if (typeof page === "undefined" || !page)
                return
            if (result.error || result.sentences.length === 0)
                fetchAudioChapter(index, callback)
            else
                callback(index, result.sentences)
        })
    }

    function stopPlayer() {
        player.stop()
        sleepTimer.cancel()
        barShown = false
        highlightId = ""
    }

    function startPlayer(index, clips, i, offset) {
        resumeId = ""
        startedUntil = Date.now() + 1000
        player.start(index, clips, i, offset)
        barShown = true
        unmark()
    }

    // A tap on the sentence spoken pauses. The narration may have moved on
    // between the touch and the frame script's answer: the sentence just
    // before counts as spoken for a moment.
    function isSpoken(id) {
        return listening && player.playing && Date.now() >= startedUntil
                && (id === player.currentId
                    || (id === previousId && chapter === previousChapter && Date.now() < previousUntil))
    }

    function playSentence(id) {
        if (listening && player.currentId === id && !player.playing) {
            // The sentence paused at: on from where it stopped.
            startedUntil = Date.now() + 1000
            player.resume()
            barShown = true
            unmark()
            return
        }
        for (var i = 0; i < sentenceClips.length; ++i) {
            if (sentenceClips[i].id === id) {
                startPlayer(chapter, sentenceClips, i)
                return
            }
        }
    }

    function playFromPage() {
        if (!ready || !hasAudio)
            return
        var prefer = jumpId || (player.active ? (listening ? player.currentId : "") : resumeId)
        flickable.webView.sendAsyncMessage("bookfish:startSentence", { prefer: prefer })
    }

    // Listening or turning pages: what was found or heard before is no
    // longer marked.
    function unmark() {
        jumpId = ""
        findShown = false
        selection = null
        flickable.webView.sendAsyncMessage("bookfish:unmark", {})
    }

    // To a place from the contents, the search or the history: reading
    // there, not listening. Like a back button, the history notes the place
    // left.
    // Not gated on ready: while a layout is under way the place left is
    // still the one shown.
    function jumpTo(index, target) {
        if (!player.playing && topChapter >= 0) {
            // Back soon after leaving the app, the session goes on: its "read"
            // takes back the "away", so the place left is noted as a jump.
            // Otherwise a new session begins with that place.
            var goesOn = reading || Date.now() - awayAt <= 120 * 1000
            beginReading()
            if (goesOn && turnedSinceJump)
                note("jump")
            turnedSinceJump = false
        }
        partnerShown = false
        selection = null
        moved = true
        resumeId = ""
        jumpId = ""
        pause()
        if (player.active)
            barShown = false
        loadChapter(index, target)
    }

    function showHit(index) {
        var hit = findHits[index]
        findIndex = index
        findShown = true
        jumpTo(hit.spine, { find: { offset: hit.offset, length: hit.length, text: hit.text } })
    }

    function openFind() {
        var find = pageStack.push(Qt.resolvedUrl("FindPage.qml"),
                                  { root: book.root, here: here(), initialQuery: findQuery,
                                    bookKey: book.key, partner: partner })
        find.selected.connect(function (hits, index, query) {
            findHits = hits
            findQuery = query
            pendingHit = index
        })
        find.chosen.connect(function (place) {
            pendingPlace = place
        })
        find.partnerChosen.connect(function () {
            pendingPartner = true
        })
    }

    // A place from the history: marked like a hit, without going on to
    // other hits.
    function showPlace(place) {
        // The book may have changed since.
        if (place.spine >= book.spine.length)
            return
        findShown = false
        jumpTo(place.spine, place.offset >= 0
               ? { find: { offset: place.offset, length: place.length, text: place.text } }
               : { fraction: 0 })
    }

    // The place shown in the search as the reader's: the sentence heard,
    // or the page read.
    function here() {
        if (listening && (player.playing || barShown))
            return { spine: chapter, id: player.currentId, fraction: fraction, heard: true }
        if (!player.active && resumeId)
            return { spine: chapter, id: resumeId, fraction: fraction, heard: true }
        return { spine: chapter, id: firstId, fraction: fraction, heard: false,
                 offset: topChapter === chapter && topOffsetOnPage ? topOffset : -1 }
    }

    function hit(x, y) {
        if (turning)
            return
        flickable.webView.sendAsyncMessage("bookfish:hitTest", { x: x, y: y })
    }

    // A long press: a table or picture opens, a word is selected (looked up in
    // landscape), or a link is followed (see notes.py).
    function pressAt(x, y) {
        flickable.webView.sendAsyncMessage("bookfish:pressAt", { x: x, y: y })
    }

    function startSelection(data) {
        taking = false
        handleA.role = "start"
        handleB.role = "end"
        pendingMove = null
        moveAsked = false
        selection = data
    }

    // By the reader (a tap, ✕, Copy, leaving the page); turning pages,
    // jumps and layouts drop it in the frame script themselves. Sent also
    // without one here: an answer dropped on the way may have left one there.
    function endSelection() {
        var had = selection !== null
        selection = null
        pendingMove = null
        flickable.webView.sendAsyncMessage("bookfish:selectClear", {})
        // The page stood still while the narration went on, also if it was
        // paused meanwhile (as in layout()).
        if (had && listening && barShown && highlightId)
            flickable.webView.sendAsyncMessage("bookfish:highlight", { id: highlightId })
    }

    function loadBookmarks() {
        py.call("bookfish.bridge.load_bookmarks", [app.bookmarksFile, book.key], function (list) {
            if (typeof page === "undefined" || !page)
                return
            if (list.error) {
                console.warn("Cannot load bookmarks", list.error, list.detail)
                return
            }
            bookmarks = list
            // Also during a layout: the frame script takes messages in order.
            // A chapter still loading brings them with its layout.
            if (chapter >= 0 && loadingUrl === "")
                flickable.webView.sendAsyncMessage("bookfish:marks", { marks: chapterMarks(chapter) })
        })
    }

    // The bookmarks of chapter index, for the frame script to underline.
    function chapterMarks(index) {
        return bookmarks.filter(function (mark) { return mark.spine === index }).map(function (mark) {
            return { id: mark.id, offset: mark.offset, length: mark.length, raw: mark.raw }
        })
    }

    function bookmark(ident) {
        for (var i = 0; i < bookmarks.length; ++i) {
            if (bookmarks[i].id === ident)
                return bookmarks[i]
        }
        return null
    }

    // action "bookmark" or "note"; the frame script answers with the place
    // (selectionTaken).
    function takeSelection(action) {
        if (!selection || taking)
            return
        taking = true
        flickable.webView.sendAsyncMessage("bookfish:takeSelection", { action: action })
    }

    // done(ok), if given, once it is stored or has failed. A note that
    // could not be stored comes back on its page, so nothing typed is lost.
    function addBookmark(mark, done) {
        py.call("bookfish.bridge.add_bookmark", [app.bookmarksFile, book.key, mark], function (result) {
            if (typeof page === "undefined" || !page)
                return
            var ok = !result.error
            if (!ok) {
                console.warn("Cannot add bookmark", result.error, result.detail)
                app.showError(mark.note !== "" ? qsTr("The note could not be saved.")
                                               : qsTr("The bookmark could not be saved."))
                if (mark.note !== "")
                    openNoteDialog(mark, null, mark.note)
            }
            loadBookmarks()
            if (done)
                done(ok)
        })
    }

    function setNote(existing, note) {
        py.call("bookfish.bridge.set_bookmark_note", [app.bookmarksFile, book.key, existing.id, note],
                function (result) {
            if (typeof page === "undefined" || !page)
                return
            if (result.error) {
                console.warn("Cannot change note", result.error, result.detail)
                app.showError(qsTr("The note could not be saved."))
                // Gone meanwhile: kept as a new one.
                openNoteDialog(existing, result.error === "missing" ? null : existing, note)
            }
            loadBookmarks()
        })
    }

    function deleteBookmarkNow(ident) {
        py.call("bookfish.bridge.delete_bookmark", [app.bookmarksFile, book.key, ident], function (result) {
            if (typeof page === "undefined" || !page)
                return
            if (result !== true)
                console.warn("Cannot delete bookmark", result.error, result.detail)
            loadBookmarks()
        })
    }

    // mark: a new place ({spine, offset, length, raw, quote}), existing null;
    // or an existing bookmark as both. note, if given, is shown instead of
    // the stored one (typed before, not stored).
    function openNoteDialog(mark, existing, note) {
        var dialog = pageStack.push(Qt.resolvedUrl("BookmarkDialog.qml"), {
            quote: mark.quote || mark.raw, chapterTitle: tocTitle(mark.spine),
            note: note !== undefined ? note : existing ? existing.note : "", existing: !!existing,
            hasNote: !!existing && existing.note !== ""
        })
        dialog.accepted.connect(function () {
            if (existing)
                setNote(existing, dialog.note)
            else
                addBookmark({ spine: mark.spine, offset: mark.offset, length: mark.length, raw: mark.raw,
                              quote: mark.quote, note: dialog.note })
        })
        dialog.deleteRequested.connect(function () {
            if (existing)
                deleteBookmarkNow(existing.id)
        })
    }

    // From the list of bookmarks.
    function editNote(mark) {
        openNoteDialog(mark, mark)
    }

    // The bookmark the selection lies in (Delete in the controls).
    function deleteMarked() {
        var mark = selection ? bookmark(selection.mark) : null
        endSelection()
        if (mark) {
            // A delete still waiting would be dropped by a second execute.
            if (remorse.active)
                remorse.trigger()
            // A note is what the reader sees in it.
            remorse.execute(mark.note !== "" ? qsTr("Deleting note") : qsTr("Deleting bookmark"),
                            function () { deleteBookmarkNow(mark.id) })
        }
    }

    function openMarked() {
        var mark = selection ? bookmark(selection.mark) : null
        if (mark)
            openNoteDialog(mark, mark)
    }

    // In landscape there is no bar to act on a selection: a word pressed is
    // looked up at once.
    function lookUpWord(text) {
        flickable.webView.sendAsyncMessage("bookfish:selectClear", {})
        pageStack.push(Qt.resolvedUrl("DictionaryPage.qml"), {
            query: text, language: book.language || "", lightPage: lightPage
        })
    }

    function lookUp() {
        if (!selection)
            return
        lookingUp = true
        pageStack.push(Qt.resolvedUrl("DictionaryPage.qml"), {
            query: selection.text, language: book.language || "", lightPage: lightPage
        })
    }

    function copySelection() {
        if (!selection)
            return
        Clipboard.text = selection.text
        endSelection()
        copiedNotice.show()
    }

    // x, y in the view; the frame script takes shares of it, inside it.
    function moveEdge(handle, x, y) {
        var view = flickable.webView
        pendingMove = { handle: handle,
                        x: Math.max(0, Math.min(view.width - 1, x)) / view.width,
                        y: Math.max(0, Math.min(view.height - 1, y)) / view.height }
        if (!moveAsked)
            sendMove()
    }

    function sendMove() {
        if (!pendingMove || !selection)
            return
        moveAsked = true
        flickable.webView.sendAsyncMessage("bookfish:moveEdge", {
            edge: pendingMove.handle.role, x: pendingMove.x, y: pendingMove.y
        })
        pendingMove = null
    }

    function followLink(href, ordinal) {
        var from = chapter
        py.call("bookfish.bridge.follow_link",
                [book.root, book.spine, book.toc, book.spine[from].path, href, ordinal],
                function (result) {
            if (typeof page === "undefined" || !page || closed || chapter !== from
                    || status !== PageStatus.Active)
                return
            if (typeof result.jump === "number") {
                // As from the contents.
                findShown = false
                jumpTo(result.jump, result.id ? { id: result.id } : { fraction: 0 })
            } else if (result.paragraphs) {
                pageStack.push(Qt.resolvedUrl("NotePage.qml"), {
                    mark: result.mark, paragraphs: result.paragraphs, first: result.first, last: result.last,
                    lightPage: lightPage
                })
            }
        })
    }

    // The address comes from the book: only its own files are shown.
    function showPicture(src) {
        if (src.indexOf("file:///") !== 0)
            return
        var path
        try {
            path = decodeURIComponent(src.slice(7))
        } catch (e) {
            return
        }
        if (path.indexOf(book.root.replace(/\/+$/, "") + "/") !== 0 || /\/\.\.?(\/|$)/.test(path))
            return
        pageStack.push(Qt.resolvedUrl("ImagePage.qml"), { source: src, pageColor: pageColor })
    }

    // A table as the book made it, drawn by the frame script as a PNG
    // (base64): Python stores it in the book's folder for the picture view.
    function showTable(png) {
        // A second long press meanwhile would remove this picture before it
        // is shown.
        if (tableSaving)
            return
        tableSaving = true
        var from = chapter
        py.call("bookfish.bridge.save_table_image", [book.root, png], function (result) {
            if (typeof page === "undefined" || !page)
                return
            tableSaving = false
            if (closed || chapter !== from || status !== PageStatus.Active)
                return
            if (result.error) {
                console.warn("Cannot show the table", result.error, result.detail)
                return
            }
            pageStack.push(Qt.resolvedUrl("ImagePage.qml"),
                           { source: fileUrl(result.path), pageColor: pageColor, doubleTapZoom: 1.75,
                             fitWidth: true })
        })
    }

    function togglePlay() {
        if (player.playing)
            pause()
        else
            play()
    }

    // Paused while listening: on where it stopped, without a round trip to
    // the page, which nobody looks at on the lock screen. Otherwise from the
    // page shown.
    function play() {
        // Closing: the page stays until its animation ends.
        if (player.playing || closed || !hasAudio)
            return
        // From the cover or the lock screen while browsing: from the page
        // read, once it is shown again.
        if (browsing) {
            var reload = browseMoved
            closeFlip()
            if (reload) {
                playAfterLoad = true
                return
            }
        }
        if (player.active && barShown)
            player.resume()
        else
            playFromPage()
    }

    // Paused by hand, also on the lock screen or the headphones: whoever
    // pauses is awake, so the sleep timer goes off. Saved in
    // playbackChanged().
    function pause() {
        if (!player.playing) {
            // Paused by an alarm or a call: then not on by itself.
            player.busy = false
            return
        }
        // First, or the volume the timer turns up would be heard.
        player.pause()
        sleepTimer.cancel()
    }

    // Every end of listening saves the place first, however it came: by
    // hand, by Sailfish, the timer, an error, the library or the end of the
    // book. Then the listening history notes it.
    function playbackChanged() {
        if (player.playing) {
            // Pages now follow the narration; that is listening.
            reading = false
            awayAt = 0
            // One set while not playing would apply to a later pause.
            stopKind = ""
            moved = true
            record("start")
            return
        }
        savePosition()
        var kinds = { pause: "pause", interrupted: "interrupted", error: "interrupted", held: "timer" }
        record(stopKind || kinds[player.why] || "pause")
        stopKind = ""
    }

    function record(kind) {
        if (player.index < 0)
            return
        addHistory(kind, { spine: player.chapter, id: player.currentId })
    }

    // Reading: the page shown, or the text after it if it holds none (a
    // picture), see topOffset. A chapter without text has its start.
    function note(kind) {
        if (topChapter < 0)
            return
        turnedSinceEntry = false
        var offset = Math.max(0, topOffset)
        notedPlace = topChapter + ":" + offset
        addHistory(kind, { spine: topChapter, offset: offset })
    }

    function addHistory(kind, place) {
        py.call("bookfish.bridge.add_history", [app.historyFile, book.key, kind, place],
                function (result) {
                    if (result !== true)
                        console.warn("Cannot note history", kind, result.error, result.detail)
                })
    }

    function beginReading() {
        if (reading || player.playing)
            return
        note("read")
        reading = true
    }

    // Reading ends: the place it ended at goes into the history.
    function endReading(kind) {
        if (!reading)
            return
        note(kind)
        reading = false
        if (kind === "away")
            awayAt = Date.now()
    }

    // For PlaybackPage: its sleep timer works while a book plays.
    readonly property bool timerAvailable: player.active
    readonly property var playbackTimer: sleepTimer

    function chapterTimeLeft() {
        return player.chapterLeft()
    }

    function openPlayback() {
        pageStack.push(Qt.resolvedUrl("PlaybackPage.qml"))
    }

    // Next and previous sentence, from the lock screen and the headphones.
    // Only while listening: paused and turned away, a sentence would pull
    // the page back.
    function forward() {
        if (barShown)
            player.next()
    }

    function back() {
        if (barShown)
            player.previous()
    }

    function followSentence(index, i) {
        // Here, not on currentId: that one passes through a wrong sentence
        // while the player takes a new chapter (clips before index).
        previousId = spokenId
        previousChapter = spokenChapter
        previousUntil = Date.now() + 600
        spokenId = player.clips[i].id
        spokenChapter = index
        highlightId = player.clips[i].id
        splits = []
        if (index !== chapter && index !== requested)
            loadChapter(index, { id: highlightId })
        else if (index === chapter)
            // Also during a layout: the frame script takes messages in order,
            // and ignores this one if a new chapter is still loading.
            flickable.webView.sendAsyncMessage("bookfish:highlight", { id: highlightId })
        // Pages change rarely while listening; save now and then.
        if (Date.now() - savedAt > 20000)
            savePosition()
        if (!upcoming || upcoming.after !== index) {
            upcoming = { after: index, chapter: -2 }
            fetchAudioChapter(index, function (next, clips) {
                if (upcoming && upcoming.after === index)
                    upcoming = { after: index, chapter: next, clips: clips }
                handOver()
            })
        }
    }

    // The player finished a chapter; give it the next one when it is read.
    function handOver() {
        if (!player.waiting || !upcoming || upcoming.after !== player.chapter
                || upcoming.chapter === -2)
            return
        if (upcoming.chapter < 0) {
            stopKind = "end"
            stopPlayer()  // end of the book
        } else {
            player.continueWith(upcoming.chapter, upcoming.clips)
        }
    }

    // The title of the first entry of the contents in chapter index.
    function tocTitle(index) {
        for (var i = 0; i < book.toc.length; ++i) {
            if (book.toc[i].spine === index)
                return book.toc[i].title
        }
        //: Chapter without a title in the contents, e.g. "Chapter 12"
        return index >= 0 ? qsTr("Chapter %1").arg(index + 1) : ""
    }

    function nextLinear(from, delta) {
        for (var i = from + delta; i >= 0 && i < book.spine.length; i += delta) {
            if (book.spine[i].linear)
                return i
        }
        return -1
    }

    function turn(delta) {
        // Browsing, the view shows another page than the one read.
        if (!ready || turning || browsing)
            return
        // The frame script drops it on turning.
        selection = null
        // Paused and turning pages: reading, not listening; also after an
        // alarm or a call, so it does not play on by itself.
        if (player.active && !player.playing) {
            barShown = false
            player.busy = false
        }
        if (!player.playing) {
            // The place before the first page turned begins the session.
            beginReading()
            turnedSinceEntry = true
            turnedSinceJump = true
        }
        moved = true
        resumeId = ""
        jumpId = ""
        partnerShown = false
        flickable.webView.sendAsyncMessage("bookfish:turn", { delta: delta })
    }

    function savePosition() {
        // Not before the first page is shown: its place is not known yet.
        // Not while browsing: the page shown is not the one read.
        if (chapter < 0 || closed || topChapter < 0 || browsing)
            return
        savedAt = Date.now()
        // The sentence heard, unless the reader paused and turned away; or
        // the one heard before the book was closed, until pages are turned.
        // The player's chapter: on a new one it is ahead of the page until
        // that is laid out.
        var heard = player.active && (player.playing || barShown)
        var spine = heard ? player.chapter : chapter
        var heardId = heard ? player.currentId : !player.active ? resumeId : ""
        // The page read, by its first character: also right after a change
        // of font size in books without sentences. Not while listening.
        var offset = heardId === "" && spine === topChapter && topOffsetOnPage ? topOffset : -1
        var share = spine === chapter ? fraction : 0
        var used = moved || player.playing
        moved = false
        py.call("bookfish.bridge.save_position",
                [app.positionsFile, book.key, { spine: spine, id: heardId || firstId,
                                                fraction: share, heard: heardId !== "",
                                                offset: offset, progress: progressAt(spine, share) },
                 used],
                function (result) {
                    if (result !== true)
                        console.warn("Cannot save position", result.error, result.detail)
                })
    }

    Connections {
        target: app
        // Leaving the settings stores several at once: one layout for all.
        onFontSizeChanged: settingsTimer.restart()
        onFontFamilyChanged: settingsTimer.restart()
        onLineHeightChanged: settingsTimer.restart()
        onParagraphSpacingChanged: settingsTimer.restart()
        onTextAlignChanged: settingsTimer.restart()
        // The text's height changes too (not beside a notch): laid out once
        // it has settled, or pages would be counted at the old height.
        onControlsAtBottomChanged: controlsSettled.restart()
        // Turning the phone lays out anew for its size (geckoSettled).
        onLandscapeColumnsChanged: {
            if (isLandscape)
                settingsTimer.restart()
        }
        onControlsScaleChanged: controlsSettled.restart()
    }

    onLightPageChanged: relayout()
    // Listening marks the sentence spoken, reading does not, as in layout();
    // the bar no longer lays the chapter out, so mark or unmark it here.
    onBarShownChanged: flickable.webView.sendAsyncMessage("bookfish:highlight", {
        id: barShown && listening && highlightId === player.currentId ? highlightId : ""
    })

    // Silica items inside take their colours from this palette.
    palette.colorScheme: lightPage ? Theme.DarkOnLight : Theme.LightOnDark

    // Closing the app gives no further chance to save.
    Connections {
        target: Qt.application
        onStateChanged: {
            if (Qt.application.state !== Qt.ApplicationActive) {
                page.savePosition()
                page.endReading("away")
            }
        }
    }

    // Back from the search page: see showPending().
    onStatusChanged: {
        if (status === PageStatus.Deactivating && !lookingUp)
            endSelection()
        // Turned while another page was on top: the old layout would show
        // in the new size until laid out again.
        if (status === PageStatus.Activating && ready && laidWidth > 0
                && !geckoSettled.sizeMatches(laidWidth, laidHeight)) {
            turning = true
            covered = true
            turnedTimer.restart()
        }
        if (status !== PageStatus.Active)
            return
        lookingUp = false
        // Turned while another page was on top: laid out now.
        geckoSettled.restart()
        if (pendingHit >= 0 || pendingPlace || pendingPartner || pendingFlip >= 0) {
            keyboardGone.restart()
            heightSettled.restart()
        } else if (ready) {
            // Gecko drops the selection while another page is shown.
            flickable.webView.sendAsyncMessage("bookfish:remark", {})
        }
    }

    // A hit or a place from the search page, once this page is back, the
    // keyboard has gone and the view has its full height again: until then
    // it is lower, and a chapter laid out meanwhile has far more pages (seen
    // on the device: 64 instead of 13). The view grows back for some 300 ms
    // after the keyboard reports it has gone and this page is active.
    function showPending(force) {
        if (status !== PageStatus.Active || (!force && (keyboardShown() || heightSettled.running)))
            return
        keyboardGone.stop()
        if (pendingHit >= 0) {
            var index = pendingHit
            pendingHit = -1
            showHit(index)
        } else if (pendingPlace) {
            var place = pendingPlace
            pendingPlace = null
            showPlace(place)
        } else if (pendingPartner) {
            pendingPartner = false
            findShown = false
            goToPartner()
        } else if (pendingFlip >= 0) {
            var stop = pendingFlip
            pendingFlip = -1
            flipTo(stop)
        }
    }

    function keyboardShown() {
        return Qt.inputMethod.visible || Qt.inputMethod.keyboardRectangle.height > 0
    }

    Connections {
        target: Qt.inputMethod
        onVisibleChanged: page.showPending()
        onKeyboardRectangleChanged: page.showPending()
    }

    Timer {
        id: heightSettled
        interval: 250
        onTriggered: {
            page.showPending()
            geckoSettled.restart()
        }
    }

    Timer {
        id: keyboardGone
        // Should the keyboard never report that it has gone.
        interval: 1500
        onTriggered: page.showPending(true)
    }

    Component.onCompleted: {
        // Before the view is initialised: only our frame script may run code
        // in the book's pages; scripts that came with a book never run. Here,
        // not at the start of the app: the web engine starts with this
        // import, and the app then hangs on closing if no page was ever shown
        // in it (seen on the device after listening to an audiobook).
        WebEngineSettings.javascriptEnabled = false
        app.reader = page
    }
    Component.onDestruction: {
        if (app.reader === page)
            app.reader = null
        py.call("bookfish.bridge.drop_search", [book.root])
    }

    Player {
        id: player

        root: book.root
        rate: app.playbackRate
        onSentence: page.followSentence(chapter, index)
        onFinished: page.handOver()
        onMarked: {
            if (n < page.splits.length)
                flickable.webView.sendAsyncMessage("bookfish:show", { page: page.splits[n].page })
        }
        onPlayingChanged: page.playbackChanged()
        // Saved already, see playbackChanged().
        onFailed: {
            page.stopPlayer()
            app.showError(qsTr("The narration could not be played."))
        }
    }

    SleepTimer {
        id: sleepTimer

        player: player
        onExpired: {
            if (player.playing) {
                stopKind = "timer"
                player.pause()
            } else {
                // Expired during an alarm or a call: not on by itself after.
                player.busy = false
            }
        }
    }

    Timer {
        // Where listening was every few minutes, to find the place again
        // where one fell asleep.
        interval: 5 * 60 * 1000
        repeat: true
        running: player.playing
        onTriggered: page.record("mark")
    }

    Timer {
        // Where reading was every few minutes, if pages were turned: to
        // find the place again after turning too far by mistake.
        interval: 5 * 60 * 1000
        repeat: true
        running: page.reading && Qt.application.state === Qt.ApplicationActive
        onTriggered: {
            if (page.turnedSinceEntry
                    && page.notedPlace !== page.topChapter + ":" + Math.max(0, page.topOffset))
                page.note("page")
        }
    }

    Rectangle {
        anchors.fill: parent
        color: pageColor
    }

    // All controls in one row, above the text beside the notch or below the
    // text (app.controlsAtBottom): a bar coming or going never changes the
    // height of the text, so the chapter is not laid out again and the page
    // stays put. Five places of equal width hold the buttons, the same in
    // every mode, so Play and Pause share a place; beside a notch three are
    // left of it and two right. The page number stands in the last place.
    Item {
        id: controls

        readonly property bool atBottom: app.controlsAtBottom
        readonly property bool besideNotch: notchSide === "top" && !atBottom
        // Room for a notch above the text, also with the controls below.
        readonly property real cutoutHeight: page.notchDepth
        readonly property real notchLeft: besideNotch ? Screen.topCutout.x : 0
        readonly property real notchRight: besideNotch ? Screen.topCutout.x + Screen.topCutout.width : 0
        // Taps beyond the row, over the first or last line of text (80 px
        // on a screen of pixel ratio 1.5): a sentence there can still be
        // tapped on its other lines or the next page. At the top not while
        // the pulley is open, whose top item is there then.
        // Not while text is selected: the handles in those lines come first.
        readonly property real reach: !selecting && (atBottom || !pulley.active)
                                      ? Math.round(53 * Theme.pixelRatio) : 0
        readonly property string mode: selecting ? "select" : barShown ? "listen"
                                                : findShown ? "find" : partnerShown ? "partner" : "read"
        // The size chosen in the settings scales the row, icons and texts.
        readonly property real fontScale: app.controlsScale
        // The same size in both places; the symbol fills only the middle of
        // the icon (its disc is not drawn), so the icon is a little larger
        // than a small one. Never wider than the narrowest place.
        readonly property real iconSize: Math.min(Math.round(app.controlsScale * 1.15 * Theme.iconSizeSmall),
                                                  Math.floor(placeWidth(0) - 2 * Theme.paddingSmall))
        // Where icons and texts are centred: a little away from the screen's
        // edge, as far as the row allows.
        readonly property real edge: Math.max(0, Math.min(Theme.paddingMedium, (height - iconSize) / 2))
        readonly property real faceTop: atBottom ? 0 : edge
        readonly property real faceHeight: height - edge

        // Above the text: its buttons take taps beyond the row.
        z: 1
        // In landscape the page is for reading alone.
        visible: page.isPortrait
        // Upside down, the notch is below: the controls stay above it.
        y: atBottom ? parent.height - height - (notchSide === "bottom" ? cutoutHeight : 0) : 0
        width: parent.width
        // As high as the notch, also below the text; without one (or with a
        // cutout elsewhere) a little lower than a small list item. Larger
        // as chosen in the settings.
        height: Math.round(app.controlsScale * (app.middleNotch ? cutoutHeight
                                                                : Math.round(0.8 * Theme.itemSizeExtraSmall)))

        function placeX(i) {
            if (besideNotch)
                return i < 3 ? i * notchLeft / 3 : notchRight + (i - 3) * (width - notchRight) / 2
            return i * width / 5
        }

        function placeWidth(i) {
            if (besideNotch)
                return i < 3 ? notchLeft / 3 : (width - notchRight) / 2
            return width / 5
        }

        // The number of places from first to last, but not across the notch:
        // a button takes the empty places right of it.
        function spanTo(first, last) {
            if (besideNotch && first < 3)
                last = Math.min(last, 2)
            return last - first + 1
        }

        // A swipe begun on a button's reach over the text turns the page,
        // by the same rule as on the page (see the flickable's MouseArea).
        function isSwipe(dx, dy) {
            return Math.abs(dx) > width / 8 && Math.abs(dx) > Math.abs(dy)
        }

        function swiped(dx, dy) {
            if (isSwipe(dx, dy))
                turn(dx < 0 ? 1 : -1)
        }

        // What it shows is taken when pressed: Play turns into Pause.
        function showPreview(button) {
            previewTimer.stop()
            preview.button = button
            preview.slot = button.slot
            preview.iconName = button.iconName
            preview.iconScale = button.iconScale
            preview.text = button.text
            preview.textSize = Math.max(2 * button.baseFontSize, Math.round(1.5 * button.fontSize))
            preview.name = button.name
            preview.shownAt = Date.now()
            preview.visible = true
        }

        // A tap shows it for a moment at least, or a quick one would show
        // nothing; moving away hides it at once.
        function endPreview(button, cancelled) {
            if (preview.button !== button)
                return
            preview.button = null
            var left = 400 - (Date.now() - preview.shownAt)
            if (cancelled || left <= 0) {
                preview.visible = false
            } else {
                previewTimer.interval = left
                previewTimer.restart()
            }
        }

        // Another button pressed while one is still shown.
        function clearPreview() {
            previewTimer.stop()
            preview.button = null
            preview.visible = false
        }

        Timer {
            id: previewTimer
            onTriggered: preview.visible = false
        }

        // Taps beside the buttons must not reach anything below.
        MouseArea {
            anchors.fill: parent
        }

        // Reading.
        BarButton {
            strip: controls
            slot: 0
            span: hasAudio ? 1 : controls.spanTo(0, 3)
            visible: controls.mode === "read"
            iconName: "icon-m-search"
            iconScale: 0.7
            //: Name of a button of the reading page, shown while it is pressed
            name: qsTr("Find")
            onActivated: openFind()
        }
        BarButton {
            strip: controls
            slot: 1
            span: controls.spanTo(1, 3)
            visible: controls.mode === "read" && hasAudio
            iconName: "icon-m-play"
            iconOpacity: 0.8
            //: Name of a button of the reading page, shown while it is pressed
            name: qsTr("Play")
            onActivated: play()
        }

        // Listening.
        BarButton {
            strip: controls
            slot: 0
            visible: controls.mode === "listen"
            iconName: "icon-m-previous"
            //: Name of a button of the reading page, shown while it is pressed
            name: qsTr("Previous sentence")
            onActivated: player.previous()
        }
        BarButton {
            strip: controls
            slot: 1
            visible: controls.mode === "listen"
            iconName: player.playing ? "icon-m-pause" : "icon-m-play"
            iconOpacity: 0.8
            //: Name of a button of the reading page, shown while it is pressed
            name: player.playing ? qsTr("Pause") : qsTr("Play")
            onActivated: togglePlay()
        }
        BarButton {
            strip: controls
            slot: 2
            visible: controls.mode === "listen"
            iconName: "icon-m-next"
            //: Name of a button of the reading page, shown while it is pressed
            name: qsTr("Next sentence")
            onActivated: player.next()
        }
        BarButton {
            strip: controls
            slot: 3
            visible: controls.mode === "listen"
            //: Playback speed on the button that opens the page for speed and sleep timer, e.g. "1.25×"
            text: qsTr("%1×").arg(Number(app.playbackRate).toLocaleString(Qt.locale(), "f", 2))
            //: Name of a button of the reading page, shown while it is pressed
            name: qsTr("Speed")
            onActivated: openPlayback()
        }
        BarButton {
            strip: controls
            slot: 4
            visible: controls.mode === "listen"
            iconName: sleepTimer.mode === "off" ? "icon-m-timer" : ""
            iconScale: 0.65
            text: sleepTimer.mode === "off" ? ""
                  : sleepTimer.mode === "chapter"
                    //: Sleep timer button while it waits for the end of the chapter
                    ? qsTr("Chapter")
                    //: Sleep timer button with the minutes left, e.g. "23 min"
                    : qsTr("%1 min").arg(Math.ceil(sleepTimer.remaining / 60000))
            //: Name of a button of the reading page, shown while it is pressed
            name: qsTr("Sleep timer")
            onActivated: openPlayback()
        }

        // A search's hits.
        BarButton {
            strip: controls
            slot: 0
            visible: controls.mode === "find"
            iconName: "icon-m-left"
            available: findIndex > 0
            //: Name of a button of the reading page, shown while it is pressed
            name: qsTr("Previous hit")
            onActivated: showHit(findIndex - 1)
        }
        BarButton {
            strip: controls
            slot: 1
            visible: controls.mode === "find"
            // Back to the list of hits.
            //: Search hit shown and number of hits, e.g. "3 / 39"
            text: qsTr("%1 / %2").arg(findIndex + 1).arg(findHits.length)
            //: Name of a button of the reading page, shown while it is pressed
            name: qsTr("All hits")
            onActivated: openFind()
        }
        BarButton {
            strip: controls
            slot: 2
            visible: controls.mode === "find"
            iconName: "icon-m-right"
            available: findIndex + 1 < findHits.length
            //: Name of a button of the reading page, shown while it is pressed
            name: qsTr("Next hit")
            onActivated: showHit(findIndex + 1)
        }
        BarButton {
            strip: controls
            slot: 3
            visible: controls.mode === "find"
            iconName: "icon-m-clear"
            //: Name of a button of the reading page, shown while it is pressed
            name: qsTr("Close search")
            onActivated: {
                findShown = false
                unmark()
            }
        }

        // Text selected.
        BarButton {
            strip: controls
            slot: 0
            visible: controls.mode === "select"
            iconName: "icon-m-clipboard"
            iconScale: 0.8
            //: Name of a button of the reading page, shown while it is pressed
            name: qsTr("Copy")
            onActivated: copySelection()
        }
        // In a bookmark: delete it; else make one.
        BarButton {
            strip: controls
            slot: 1
            visible: controls.mode === "select"
            iconName: selecting && selection.mark ? "icon-m-delete" : "icon-m-favorite"
            iconScale: 0.8
            name: selecting && selection.mark
                  //: Name of a button of the reading page, shown while it is pressed
                  ? qsTr("Delete bookmark")
                  //: Name of a button of the reading page, shown while it is pressed
                  : qsTr("Bookmark")
            onActivated: {
                if (selection && selection.mark)
                    deleteMarked()
                else
                    takeSelection("bookmark")
            }
        }
        BarButton {
            strip: controls
            slot: 2
            visible: controls.mode === "select"
            iconName: "icon-m-question"
            iconScale: 0.8
            //: Name of a button of the reading page, shown while it is pressed
            name: qsTr("Dictionary")
            onActivated: lookUp()
        }
        // In a bookmark: its note; else a new note.
        BarButton {
            strip: controls
            slot: 3
            visible: controls.mode === "select"
            iconName: "icon-m-note"
            iconScale: 0.8
            //: Name of a button of the reading page, shown while it is pressed
            name: qsTr("Note")
            onActivated: {
                if (selection && selection.mark)
                    openMarked()
                else
                    takeSelection("note")
            }
        }
        BarButton {
            strip: controls
            slot: 4
            visible: controls.mode === "select"
            iconName: "icon-m-clear"
            //: Name of a button of the reading page, shown while it is pressed
            name: qsTr("Cancel")
            onActivated: endSelection()
        }

        // The offer to go where the audiobook (or book) was left.
        Label {
            x: controls.placeX(0) + Theme.paddingMedium
            y: controls.faceTop
            width: controls.placeX(2) + controls.placeWidth(2) - x
            height: controls.faceHeight
            visible: controls.mode === "partner"
            verticalAlignment: Text.AlignVCenter
            // Larger controls: it shrinks rather than lose the figure.
            fontSizeMode: Text.HorizontalFit
            minimumPixelSize: Theme.fontSizeTiny / 2
            font.pixelSize: Math.round(controls.fontScale * Theme.fontSizeExtraSmall)
            color: palette.secondaryHighlightColor
            //: Offer on opening a book whose audiobook was listened to later, e.g. "Listened to 43 %"
            text: partner ? qsTr("Listened to %1 %").arg(app.percent(partner.progress)) : ""
        }
        BarButton {
            strip: controls
            slot: 3
            visible: controls.mode === "partner"
            textColor: palette.highlightColor
            baseFontSize: Theme.fontSizeExtraSmall
            //: Goes to the place in the book or audiobook offered
            text: qsTr("Go there")
            name: qsTr("Go there")
            onActivated: goToPartner()
        }
        BarButton {
            strip: controls
            slot: 4
            visible: controls.mode === "partner"
            iconName: "icon-m-clear"
            //: Name of a button of the reading page, shown while it is pressed
            name: qsTr("Dismiss")
            onActivated: partnerShown = false
        }

        Label {
            x: controls.placeX(4) + Theme.paddingSmall
            y: controls.faceTop
            width: controls.placeWidth(4) - 2 * Theme.paddingSmall
            height: controls.faceHeight
            // Not beside the player's buttons: there it distracts.
            visible: pageLabel !== "" && (controls.mode === "read" || controls.mode === "find")
            verticalAlignment: Text.AlignVCenter
            horizontalAlignment: Text.AlignHCenter
            fontSizeMode: Text.HorizontalFit
            minimumPixelSize: Theme.fontSizeTiny / 2
            // As small as the buttons' texts.
            font.pixelSize: Math.round(controls.fontScale * Math.round(0.85 * Theme.fontSizeTiny))
            color: palette.secondaryColor
            text: pageNumberText(false)
        }
        // Opens the page flip view; also where no page is shown (the front
        // matter), so it can be opened there too.
        MouseArea {
            x: controls.placeX(4)
            width: controls.placeWidth(4)
            height: controls.height
            enabled: flipAllowed
            onClicked: toggleFlip()
        }
    }

    PageFlipGrid {
        id: flipGrid

        // Above the controls; clear of a notch above it.
        z: 3
        visible: flipShown
        x: notchSide === "left" ? notchDepth : 0
        y: notchSide === "top" ? notchDepth : 0
        width: page.width - (notchSide === "left" || notchSide === "right" ? notchDepth : 0)
        height: page.height - (notchSide === "top" || notchSide === "bottom" ? notchDepth : 0)
        tiles: gridTiles
        stops: flipStops
        estimated: flipEstimated
        total: flipEstimated ? flipStops.length : book.pages ? book.pages.total : 0
        current: gridStop()
        currentText: pageNumberText(true)
        tileAspect: flickable.width > 0 ? flickable.height / flickable.width : 1.5
        busy: browseIntent !== "" || requested >= 0
        pageColor: page.pageColor
        lineColor: lightPage ? "#8c8c8c" : "#808080"
        onTileTapped: openTile(index)
        onSwiped: gridStep(delta)
        onDragged: dragStop(index)
        onChosen: chooseStop(index)
        onGoToRequested: openGoToPage()
        onCloseRequested: closeFlip()
    }

    // Dragging the bar into another chapter: loaded once the finger rests.
    Timer {
        id: holdTimer
        interval: 300
        onTriggered: page.centerOnStop()
    }

    // The button pressed, large and with its name, beside it over the text:
    // above the controls at the bottom, past the reach; well below them at
    // the top, where the finger reaching up covers less.
    Rectangle {
        id: preview

        // The button still pressed; null once released.
        property Item button: null
        property int slot
        property string iconName
        property real iconScale: 1
        property string text
        property real textSize: Theme.fontSizeMedium
        property string name
        property real shownAt
        readonly property real iconSize: Math.max(2 * Math.round(1.15 * Theme.iconSizeSmall),
                                                  Math.round(1.5 * controls.iconSize))
        readonly property real centerX: controls.placeX(slot) + controls.placeWidth(slot) / 2

        // Above the controls and the handles.
        z: 3
        visible: false
        width: Math.max(previewContent.width, iconSize) + 2 * Theme.paddingLarge
        height: previewContent.height + 2 * Theme.paddingMedium
        x: Math.max(Theme.paddingSmall, Math.min(parent.width - width - Theme.paddingSmall,
                                                 centerX - width / 2))
        y: controls.atBottom ? controls.y - controls.reach - Theme.paddingMedium - height
                             : controls.y + controls.height + 3 * Math.round(53 * Theme.pixelRatio)
        radius: Theme.paddingMedium
        color: pageColor
        border.width: Math.max(1, Math.round(Theme.pixelRatio))
        border.color: palette.secondaryColor

        Column {
            id: previewContent

            anchors.centerIn: parent
            spacing: Theme.paddingSmall

            Item {
                anchors.horizontalCenter: parent.horizontalCenter
                width: preview.iconSize
                height: preview.iconSize
                visible: preview.iconName !== ""

                BarIcon {
                    anchors.centerIn: parent
                    width: Math.round(preview.iconScale * preview.iconSize)
                    height: width
                    name: preview.iconName
                    color: palette.highlightColor
                }
            }
            Label {
                anchors.horizontalCenter: parent.horizontalCenter
                visible: preview.iconName === ""
                color: palette.highlightColor
                font.pixelSize: preview.textSize
                text: preview.text
            }
            Label {
                anchors.horizontalCenter: parent.horizontalCenter
                color: palette.highlightColor
                font.pixelSize: Theme.fontSizeSmall
                text: preview.name
            }
        }
    }

    WebViewFlickable {
        id: flickable

        anchors {
            top: parent.top
            topMargin: !isPortrait ? 0
                       : controls.atBottom ? Math.max(notchSide === "top" ? notchDepth : 0, Theme.paddingSmall)
                       : controls.height
            left: parent.left
            leftMargin: notchSide === "left" ? notchDepth : 0
            right: parent.right
            rightMargin: notchSide === "right" ? notchDepth : 0
            bottom: parent.bottom
            bottomMargin: notchSide === "bottom" ? notchDepth : 0
        }
        // The pulley sits above the flickable; unclipped it would cover the
        // controls.
        clip: true

        PullDownMenu {
            id: pulley

            // No highlight strip between the controls and the text; the
            // chosen item is still shown by its text colour.
            highlightColor: "transparent"
            backgroundColor: pageColor

            MenuItem {
                text: qsTr("Settings")
                onClicked: pageStack.push(Qt.resolvedUrl("SettingsPage.qml"))
            }
            MenuItem {
                text: qsTr("Library")
                onClicked: {
                    savePosition()
                    endReading("close")
                    closed = true
                    stopKind = "close"
                    stopPlayer()
                    pageStack.pop()
                }
            }
            MenuItem {
                text: qsTr("Contents")
                onClicked: {
                    var toc = pageStack.push(Qt.resolvedUrl("TocPage.qml"),
                                             { toc: book.toc, currentChapter: chapter, bookRoot: book.root })
                    toc.selected.connect(function (index, fragment) {
                        findShown = false
                        jumpTo(index, fragment ? { id: fragment } : { fraction: 0 })
                    })
                }
            }
            MenuItem {
                //: Opens the list of bookmarks and notes
                text: qsTr("Bookmarks")
                onClicked: pageStack.push(Qt.resolvedUrl("BookmarksPage.qml"), { reader: page })
            }
            MenuItem {
                //: Opens the search in the book and its history of reading and listening
                text: qsTr("Find & history")
                onClicked: openFind()
            }
        }

        webView.active: true
        onWidthChanged: geckoSettled.restart()
        onHeightChanged: {
            geckoSettled.restart()
            if (page.pendingHit >= 0 || page.pendingPlace || page.pendingFlip >= 0)
                heightSettled.restart()
            if (controlsSettled.running)
                controlsSettled.restart()
        }
        // WebViewFlickable assumes the page fills the screen; below the
        // header, 100vh would reach past the bottom edge.
        webView.viewportHeight: flickable.height

        webView.onViewInitialized: {
            webView.loadFrameScript(Qt.resolvedUrl("../js/framescript.js"))
            webView.addMessageListener("bookfish:loaded")
            webView.addMessageListener("bookfish:page")
            webView.addMessageListener("bookfish:edge")
            webView.addMessageListener("bookfish:painted")
            webView.addMessageListener("bookfish:resized")
            webView.addMessageListener("bookfish:highlighted")
            webView.addMessageListener("bookfish:hit")
            webView.addMessageListener("bookfish:pressed")
            webView.addMessageListener("bookfish:start")
            webView.addMessageListener("bookfish:found")
            webView.addMessageListener("bookfish:selected")
            webView.addMessageListener("bookfish:selectionTaken")
            webView.addMessageListener("bookfish:thumbs")
            page.start()
        }

        webView.onRecvAsyncMessage: page.handleMessage(message, data)


        // The WebView itself gets no touches (no zooming, no native selection);
        // swipes, taps and long presses are handled here.
        MouseArea {
            parent: flickable.webView
            anchors.fill: parent

            property real startX
            property real startY
            // A long press is never also a tap.
            property bool held: false

            onPressed: {
                startX = mouse.x
                startY = mouse.y
                held = false
                preventStealing = false
            }
            // Qt reports a hold even after the finger moved: a slow swipe
            // still turns the page.
            onPressAndHold: {
                if (preventStealing || Math.abs(mouse.x - startX) >= Theme.startDragDistance
                        || Math.abs(mouse.y - startY) >= Theme.startDragDistance)
                    return
                held = true
                if (ready)
                    pressAt(mouse.x / width, mouse.y / height)
            }
            onPositionChanged: {
                // Claim a clearly horizontal swipe before Silica takes it;
                // vertical drags stay with the pulley.
                var dx = Math.abs(mouse.x - startX)
                if (!preventStealing && dx > Theme.startDragDistance / 3
                        && dx > Math.abs(mouse.y - startY)) {
                    preventStealing = true
                }
            }
            onReleased: {
                if (held)
                    return
                var dx = mouse.x - startX
                var dy = mouse.y - startY
                if (Math.abs(dx) > width / 8 && Math.abs(dx) > Math.abs(dy)) {
                    turn(dx < 0 ? 1 : -1)
                } else if (Math.abs(dx) < Theme.startDragDistance
                           && Math.abs(dy) < Theme.startDragDistance) {
                    // With text selected a tap only ends the selection.
                    if (selecting)
                        endSelection()
                    // Two columns: only the outer eighths, or each would
                    // be half a column.
                    else if (mouse.x < width / (columns > 1 ? 8 : 4))
                        turn(-1)
                    else if (mouse.x > width * (columns > 1 ? 7 / 8 : 3 / 4))
                        turn(1)
                    else if (ready)
                        hit(mouse.x / width, mouse.y / height)
                }
            }
        }
    }

    // The handles of a selection, over the view and above the controls: a
    // handle hanging below the last line reaches into the controls when they
    // sit below the text. Moves with the view (the pulley).
    // The WebView goes first when the page is destroyed.
    Item {
        readonly property Item view: flickable.webView
        x: view ? flickable.x + flickable.contentItem.x + view.x : 0
        y: view ? flickable.y + flickable.contentItem.y + view.y : 0
        z: 2
        width: view ? view.width : 0
        height: view ? view.height : 0
        visible: selecting && !pulley.active

        SelectionHandle {
            id: handleA

            color: palette.highlightColor
            edgeX: !selecting ? 0 : (role === "start" ? selection.startX : selection.endX) * width
            lineTop: !selecting ? 0 : (role === "start" ? selection.startTop : selection.endTop) * height
            lineBottom: !selecting ? 0 : (role === "start" ? selection.startBottom : selection.endBottom) * height
            onMoved: page.moveEdge(handleA, x, y)
        }
        SelectionHandle {
            id: handleB

            role: "end"
            color: palette.highlightColor
            edgeX: !selecting ? 0 : (role === "start" ? selection.startX : selection.endX) * width
            lineTop: !selecting ? 0 : (role === "start" ? selection.startTop : selection.endTop) * height
            lineBottom: !selecting ? 0 : (role === "start" ? selection.startBottom : selection.endBottom) * height
            onMoved: page.moveEdge(handleB, x, y)
        }
    }

    Notice {
        id: bookmarkNotice

        duration: 2000
        //: Shown briefly after a bookmark was made
        text: qsTr("Bookmark added")
    }

    RemorsePopup {
        id: remorse

        // Above the controls and the handles.
        z: 3
    }

    Notice {
        id: copiedNotice

        duration: 2000
        //: Shown briefly after the selected text was copied
        text: qsTr("Copied")
    }

    // Until a chapter is laid out and painted the WebView shows the book's
    // own white page; cover it. Gecko reports the paint (framescript.js);
    // measured 2 to 400 ms after the layout, so no fixed delay fits.
    Rectangle {
        anchors.fill: flickable
        color: pageColor
        visible: covered
    }

    Timer {
        id: settingsTimer
        interval: 0
        onTriggered: page.relayout()
    }

    // See onControlsAtBottomChanged and onControlsScaleChanged; as long as
    // heightSettled.
    Timer {
        id: controlsSettled
        interval: 250
        // Not if laid out meanwhile for the new size (geckoSettled).
        onTriggered: {
            if (laidOut !== layoutSettings())
                page.relayout()
        }
    }

    // Laid out for a new size once Gecko has it (see laidWidth): up to a
    // second after Qt, passing other sizes on the way (516 × 1070 between
    // portrait and landscape); laid out before, the page was a different
    // one.
    Timer {
        id: geckoSettled

        function sizeMatches(width, height) {
            return Math.abs(flickable.width / pixelRatio - width) <= 1
                    && Math.abs(flickable.height / pixelRatio - height) <= 1
        }

        interval: 150
        onTriggered: {
            if (geckoWidth <= 0 || !sizeMatches(geckoWidth, geckoHeight)
                    || (geckoWidth === laidWidth && geckoHeight === laidHeight))
                return
            // Again when back (onStatusChanged); with the keyboard of
            // another page the view is lower only for a while, and grows
            // back after it has gone (heightSettled).
            if (status !== PageStatus.Active || keyboardShown() || heightSettled.running)
                return
            relayout()
        }
    }

    // Should Gecko not report the new size: uncovered after a while, laid
    // out first if the view no longer fits the layout.
    Timer {
        id: turnedTimer
        interval: 1500
        onTriggered: {
            if (!ready || status !== PageStatus.Active || keyboardShown())
                return
            if (!geckoSettled.sizeMatches(laidWidth, laidHeight))
                relayout()
            else
                covered = false
        }
    }

    // The page number in landscape, upright as on a book's spine: beside
    // the notch above it, without one in the right margin near the top.
    Item {
        id: spine

        readonly property bool inStrip: notchSide === "left" || notchSide === "right"

        // Under the page flip view the page read is not shown.
        visible: isLandscape && !flipShown
        // Above the strip that turns pages: a tap on the number opens the
        // page flip view.
        z: 2
        x: notchSide === "left" ? 0 : page.width - width
        width: inStrip ? notchDepth : Math.round(24 * pixelRatio)
        // In landscape the notch's left end is at the bottom on the left side.
        height: notchSide === "left" ? page.height - Screen.topCutout.x - Screen.topCutout.width
              : notchSide === "right" ? Screen.topCutout.x
              : Math.round(page.height * 0.3)

        Label {
            id: spineLabel

            anchors.centerIn: parent
            rotation: -90
            font.pixelSize: Math.round(0.85 * Theme.fontSizeTiny)
            // As the hints elsewhere: secondaryColor hardly shows on white.
            color: lightPage ? "#8c8c8c" : "#808080"
            text: pageNumberText(true)
        }

        // Only around the number: the rest of the strip still turns pages.
        // Without a notch it lies on the text's margin, where a swipe to
        // the next page often begins: a swipe still turns.
        MouseArea {
            property real startX
            property real startY

            width: parent.width
            height: Math.min(parent.height, Math.max(Theme.itemSizeSmall, spineLabel.width + 2 * Theme.paddingLarge))
            anchors.verticalCenter: parent.verticalCenter
            enabled: flipAllowed
            onPressed: {
                startX = mouse.x
                startY = mouse.y
            }
            onReleased: {
                var dx = mouse.x - startX
                var dy = mouse.y - startY
                if (Math.abs(dx) > page.width / 8 && Math.abs(dx) > Math.abs(dy))
                    turn(dx < 0 ? 1 : -1)
                else if (Math.abs(dx) < Theme.startDragDistance && Math.abs(dy) < Theme.startDragDistance)
                    toggleFlip()
            }
        }
    }

    // The strip beside the notch turns pages, as the edge of the text there.
    MouseArea {
        visible: isLandscape && spine.inStrip
        z: 1
        x: notchSide === "left" ? 0 : page.width - width
        width: notchDepth
        height: page.height
        onClicked: turn(notchSide === "left" ? -1 : 1)
    }

    Timer {
        id: uncoverTimer
        // Fallback should the paint never be reported.
        interval: 1000
        onTriggered: covered = false
    }

    Timer {
        id: paintedTimer
        // The paint reaches the screen a frame or two after Gecko reports it.
        interval: 50
        onTriggered: covered = false
    }
}
