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
    // A hit chosen in the list, shown once this page is back.
    property int pendingHit: -1
    // An entry of the history chosen, likewise; see FindPage.
    property var pendingPlace: null
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

    // Turning pages needs the horizontal swipe; the library is in the pulley.
    backNavigation: false
    allowedOrientations: Orientation.Portrait

    function fileUrl(path) {
        return "file://" + path.split("/").map(encodeURIComponent).join("/")
    }

    // A readaloud is its own audiobook.
    function start() {
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

    // target: { id, fraction } or { end: true }, see framescript.js
    function loadChapter(index, target) {
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
                lightPage, app.controlsAtBottom].join("|")
    }

    function layout(target) {
        laidOut = layoutSettings()
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
            margin: 24,
            marginTop: 4,
            // Below the text the controls' row is margin enough; above it
            // they cover nothing.
            marginBottom: app.controlsAtBottom ? 0 : 12,
            barHeight: app.controlsAtBottom ? controls.height : 0,
            fontSize: app.fontSize,
            fontFamily: app.fontFamily === "serif" ? "serif" : "sans-serif",
            lineHeight: app.lineHeight,
            paragraphSpacing: app.paragraphSpacing,
            color: light ? "black" : "white",
            background: light ? "white" : "black"
        })
    }

    // Same chapter and sentence, new text size. While a layout is under way
    // the "page" message calls this again if the size has changed meanwhile.
    function relayout() {
        if (!ready || closed)
            return
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
            pageIndex = data.page
            pageCount = data.pages
            firstId = data.firstId
            if (data.offset >= 0 || topChapter !== chapter)
                topOffset = data.offset
            topChapter = chapter
            topOffsetOnPage = data.offsetOnPage
            fraction = data.fraction
            updateBookPages()
            savePosition()
            if (laidOut !== layoutSettings())
                relayout()
            break
        case "bookfish:painted":
            if (data.serial !== serial || !covered)
                return
            uncoverTimer.stop()
            paintedTimer.restart()
            break
        case "bookfish:edge":
            // Only the first of several quick turns past the end counts.
            if (data.serial !== serial || !ready)
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
        case "bookfish:hit":
            if (data.serial !== serial)
                return
            // A tap in the text ends looking through the hits; in a
            // readaloud by listening (startPlayer).
            if (!hasAudio)
                findShown = false
            if (data.id)
                playSentence(data.id)
            else if (!player.playing)
                playFromPage()
            break
        case "bookfish:pressed":
            if (data.serial !== serial || status !== PageStatus.Active)
                return
            if (data.picture)
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
        player.start(index, clips, i, offset)
        barShown = true
        unmark()
    }

    function playSentence(id) {
        if (listening && player.currentId === id && !player.playing) {
            // The sentence paused at: on from where it stopped.
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
        flickable.webView.sendAsyncMessage("bookfish:hitTest", { x: x, y: y })
    }

    // A long press: a picture opens, a link is followed (see notes.py).
    function pressAt(x, y) {
        flickable.webView.sendAsyncMessage("bookfish:pressAt", { x: x, y: y })
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

    function openSleepTimer() {
        pageStack.push(Qt.resolvedUrl("SleepTimerPage.qml"),
                       { timer: sleepTimer, chapterLeft: player.chapterLeft() })
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
        if (!ready)
            return
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
        if (chapter < 0 || closed || topChapter < 0)
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
        // The text's height changes too (not beside a notch): laid out once
        // it has settled, or pages would be counted at the old height.
        onControlsAtBottomChanged: controlsSettled.restart()
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
        if (status !== PageStatus.Active)
            return
        if (pendingHit >= 0 || pendingPlace || pendingPartner) {
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
        onTriggered: page.showPending()
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
    // stays put. The left side holds the controls used most; where they need
    // more room the right side helps, and the page number stands at the
    // right end.
    Item {
        id: controls

        readonly property bool atBottom: app.controlsAtBottom
        readonly property bool besideNotch: app.middleNotch && !atBottom
        // Room for a notch above the text, also with the controls below.
        readonly property real cutoutHeight: Screen.hasCutouts === true && Screen.topCutout.height > 0
                                             ? Screen.topCutout.y + Screen.topCutout.height : 0
        readonly property real gap: Theme.paddingSmall
        readonly property real leftEnd: (besideNotch ? Screen.topCutout.x : width / 2) - gap
        readonly property real rightStart: (besideNotch ? Screen.topCutout.x + Screen.topCutout.width
                                                        : width / 2) + gap
        // Taps beyond the row, over the first or last line of text (80 px
        // on a screen of pixel ratio 1.5): a sentence there can still be
        // tapped on its other lines or the next page. At the top not while
        // the pulley is open, whose top item is there then.
        readonly property real reach: atBottom || !pulley.active ? Math.round(53 * Theme.pixelRatio) : 0
        // Three buttons fill the left side; below the text it is wider.
        readonly property real buttonWidth: atBottom ? (leftEnd - gap) / 3
                                                     : Math.min(Theme.itemSizeExtraSmall, (leftEnd - gap) / 3)
        readonly property string mode: barShown ? "listen" : findShown ? "find"
                                                : partnerShown ? "partner" : "read"
        // The same size in both places; the symbol fills only the middle of
        // the icon (its disc is not drawn), so the icon is a little larger
        // than a small one.
        readonly property real iconSize: Math.round(1.15 * Theme.iconSizeSmall)
        // Where icons and texts are centred: a little away from the screen's
        // edge, as far as the row allows.
        readonly property real edge: Math.max(0, Math.min(Theme.paddingMedium, (height - iconSize) / 2))
        readonly property real faceTop: atBottom ? 0 : edge
        readonly property real faceHeight: height - edge

        // Above the text: its buttons take taps beyond the row.
        z: 1
        y: atBottom ? parent.height - height : 0
        width: parent.width
        // As high as the notch, also below the text; without one (or with a
        // cutout elsewhere) a little lower than a small list item.
        height: app.middleNotch ? cutoutHeight : Math.round(0.8 * Theme.itemSizeExtraSmall)

        // A swipe begun on a button's reach over the text turns the page,
        // by the same rule as on the page (see the flickable's MouseArea).
        function swiped(dx, dy) {
            if (Math.abs(dx) > width / 8 && Math.abs(dx) > Math.abs(dy))
                turn(dx < 0 ? 1 : -1)
        }

        // Taps beside the buttons must not reach anything below.
        MouseArea {
            anchors.fill: parent
        }

        // Left of the notch or the middle.
        Item {
            x: controls.gap
            width: controls.leftEnd - x
            height: parent.height

            Row {
                height: parent.height
                visible: controls.mode === "read"

                BarButton {
                    strip: controls
                    width: controls.buttonWidth
                    iconName: "icon-m-search"
                    iconScale: 0.7
                    onActivated: openFind()
                }
                BarButton {
                    strip: controls
                    width: controls.buttonWidth
                    visible: hasAudio
                    iconName: "icon-m-play"
                    iconOpacity: 0.8
                    onActivated: play()
                }
            }

            Row {
                height: parent.height
                visible: controls.mode === "listen"

                BarButton {
                    strip: controls
                    width: controls.buttonWidth
                    iconName: "icon-m-previous"
                    onActivated: player.previous()
                }
                BarButton {
                    strip: controls
                    width: controls.buttonWidth
                    iconName: player.playing ? "icon-m-pause" : "icon-m-play"
                    iconOpacity: 0.8
                    onActivated: togglePlay()
                }
                BarButton {
                    strip: controls
                    width: controls.buttonWidth
                    iconName: "icon-m-next"
                    onActivated: player.next()
                }
            }

            Row {
                height: parent.height
                visible: controls.mode === "find"

                BarButton {
                    strip: controls
                    width: controls.buttonWidth
                    iconName: "icon-m-left"
                    available: findIndex > 0
                    onActivated: showHit(findIndex - 1)
                }
                BarButton {
                    strip: controls
                    width: controls.buttonWidth
                    // Back to the list of hits.
                    //: Search hit shown and number of hits, e.g. "3 / 39"
                    text: qsTr("%1 / %2").arg(findIndex + 1).arg(findHits.length)
                    onActivated: openFind()
                }
                BarButton {
                    strip: controls
                    width: controls.buttonWidth
                    iconName: "icon-m-right"
                    available: findIndex + 1 < findHits.length
                    onActivated: showHit(findIndex + 1)
                }
            }

            Label {
                y: controls.faceTop
                width: parent.width
                height: controls.faceHeight
                visible: controls.mode === "partner"
                verticalAlignment: Text.AlignVCenter
                truncationMode: TruncationMode.Fade
                font.pixelSize: Theme.fontSizeExtraSmall
                color: palette.secondaryHighlightColor
                //: Offer on opening a book whose audiobook was listened to later, e.g. "Listened to 43 %"
                text: partner ? qsTr("Listened to %1 %").arg(app.percent(partner.progress)) : ""
            }
        }

        // Right of the notch or the middle, ending with the page number.
        Row {
            id: rightSide

            anchors.right: parent.right
            anchors.rightMargin: controls.gap
            height: parent.height
            layoutDirection: Qt.RightToLeft

            Label {
                id: pageLabel

                // What the buttons beside it leave, so it shrinks rather
                // than pushes them over the notch or the middle.
                readonly property real room: controls.width - controls.gap - controls.rightStart
                                             - (findButtons.visible ? findButtons.width : 0)
                y: controls.faceTop
                width: Math.min(implicitWidth, Math.max(0, room))
                height: controls.faceHeight
                // Not beside the player's buttons: there it distracts.
                visible: bookPages > 0 && controls.mode !== "partner" && controls.mode !== "listen"
                verticalAlignment: Text.AlignVCenter
                horizontalAlignment: Text.AlignRight
                fontSizeMode: Text.HorizontalFit
                minimumPixelSize: Theme.fontSizeTiny / 2
                // As small as the buttons' texts.
                font.pixelSize: Math.round(0.85 * Theme.fontSizeTiny)
                color: palette.secondaryColor
                //: Estimated page in the whole book, e.g. "30/295"
                text: qsTr("%1/%2").arg(bookPage).arg(bookPages)
            }

            Row {
                id: listenButtons

                height: parent.height
                visible: controls.mode === "listen"
                layoutDirection: Qt.RightToLeft

                BarButton {
                    strip: controls
                    width: controls.buttonWidth
                    iconName: sleepTimer.mode === "off" ? "icon-m-timer" : ""
                    iconScale: 0.65
                    text: sleepTimer.mode === "off" ? ""
                          : sleepTimer.mode === "chapter"
                            //: Sleep timer button while it waits for the end of the chapter
                            ? qsTr("Chapter")
                            //: Sleep timer button with the minutes left, e.g. "23 min"
                            : qsTr("%1 min").arg(Math.ceil(sleepTimer.remaining / 60000))
                    onActivated: openSleepTimer()
                }
                BarButton {
                    strip: controls
                    width: implicitWidth
                    //: Playback speed on the button that opens the settings, e.g. "1.25×"
                    text: qsTr("%1×").arg(Number(app.playbackRate).toLocaleString(Qt.locale(), "f", 2))
                    onActivated: pageStack.push(Qt.resolvedUrl("SettingsPage.qml"))
                }
            }

            Row {
                id: findButtons

                height: parent.height
                visible: controls.mode === "find"

                BarButton {
                    strip: controls
                    width: controls.buttonWidth
                    iconName: "icon-m-clear"
                    onActivated: {
                        findShown = false
                        unmark()
                    }
                }
            }

            Row {
                height: parent.height
                visible: controls.mode === "partner"
                layoutDirection: Qt.RightToLeft

                BarButton {
                    strip: controls
                    width: controls.buttonWidth
                    iconName: "icon-m-clear"
                    onActivated: partnerShown = false
                }
                BarButton {
                    strip: controls
                    width: implicitWidth
                    textColor: palette.highlightColor
                    fontSize: Theme.fontSizeExtraSmall
                    //: Goes to the place in the book or audiobook offered
                    text: qsTr("Go there")
                    onActivated: goToPartner()
                }
            }
        }
    }

    WebViewFlickable {
        id: flickable

        anchors {
            top: parent.top
            topMargin: controls.atBottom ? Math.max(controls.cutoutHeight, Theme.paddingSmall)
                                         : controls.height
            left: parent.left
            right: parent.right
            bottom: parent.bottom
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
                                             { toc: book.toc, currentChapter: chapter })
                    toc.selected.connect(function (index, fragment) {
                        findShown = false
                        jumpTo(index, fragment ? { id: fragment } : { fraction: 0 })
                    })
                }
            }
            MenuItem {
                //: Opens the search in the book and its history of reading and listening
                text: qsTr("Find & history")
                onClicked: openFind()
            }
        }

        webView.active: true
        onHeightChanged: {
            if (page.pendingHit >= 0 || page.pendingPlace)
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
            webView.addMessageListener("bookfish:highlighted")
            webView.addMessageListener("bookfish:hit")
            webView.addMessageListener("bookfish:pressed")
            webView.addMessageListener("bookfish:start")
            webView.addMessageListener("bookfish:found")
            page.start()
        }

        webView.onRecvAsyncMessage: page.handleMessage(message, data)


        // The WebView itself gets no touches: no links, no zooming, no text
        // selection. Swipes and taps are handled here.
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
                    if (mouse.x < width / 4)
                        turn(-1)
                    else if (mouse.x > width * 3 / 4)
                        turn(1)
                    else if (ready)
                        hit(mouse.x / width, mouse.y / height)
                }
            }
        }
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

    // See onControlsAtBottomChanged; as long as heightSettled.
    Timer {
        id: controlsSettled
        interval: 250
        onTriggered: page.relayout()
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
