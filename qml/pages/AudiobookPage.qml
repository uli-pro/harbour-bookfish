import QtQuick 2.0
import Sailfish.Silica 1.0
import "../components"

// An audiobook without text: cover, chapter, place and controls. It plays
// with the readaloud's player, each chapter one clip: a part of a file, or
// a whole file of a folder. Offers what the reading page offers to the
// cover and the lock screen (app.reader).
Page {
    id: page

    // From bridge.open_audiobook.
    property var book
    property var chapters: book.chapters
    property double duration: book.duration
    // The place whenever nothing plays: chapter and ms from its start. Set
    // at every end of listening and every jump, so it never depends on
    // what the audio reports after a stop.
    property int chapter: 0
    property double offset: 0
    // The place heard last while playing, every second: after the system
    // has stopped the audio, the audio itself is back at 0.
    property var lastHeard: null
    // The saved place is loaded; Play before would start at 0.
    property bool ready: false
    // The end of the book was reached; Play starts again.
    property bool atEnd: false
    // The place shown, in ms from the start of the chapter.
    property double shown: 0
    // Left for the library: no further saving.
    property bool closed: false
    // The EPUB of this audiobook, see bridge.partner; null if none.
    property var partner: null
    // Offering to go where the EPUB was read last.
    property bool partnerShown: false
    // Listened or gone elsewhere since the place was saved: the book has
    // been used.
    property bool moved: false
    // How the next end of listening goes into the history, if not as the
    // player says: "timer", "close" or "end".
    property string stopKind: ""

    readonly property bool hasAudio: true
    readonly property bool playing: player.playing
    readonly property int current: player.playing ? player.chapter : chapter
    readonly property string coverUrl: book.cover ? fileUrl(book.cover) : ""
    readonly property string chapterTitle: titleOf(current)

    // Leaving goes through the pulley, which saves and notes the end.
    backNavigation: false
    allowedOrientations: Orientation.Portrait

    function fileUrl(path) {
        return "file://" + path.split("/").map(encodeURIComponent).join("/")
    }

    function titleOf(index) {
        var item = chapters[index]
        if (!item)
            return ""
        if (item.title)
            return item.title
        // A file without chapter marks is one chapter: the book.
        //: Chapter of an audiobook without a title, e.g. "Chapter 12"
        return chapters.length === 1 ? book.title : qsTr("Chapter %1").arg(index + 1)
    }

    function clipOf(index) {
        var item = chapters[index]
        return { id: "c" + index, audio: item.file, begin: item.begin, end: item.end }
    }

    // A chapter ending at a mark; the others run to the end of their file,
    // whose length may still be an estimate.
    function hasEnd(item) {
        return typeof item.end === "number"
    }

    function limit(index, ms) {
        ms = Math.max(0, ms)
        return hasEnd(chapters[index]) ? Math.min(ms, chapters[index].length) : ms
    }

    // ms from the start of the chapter the player plays.
    function live() {
        return Math.max(0, player.currentPosition() - chapters[player.chapter].begin)
    }

    // ms from the start of the current chapter.
    function place() {
        return player.playing ? live() : offset
    }

    // "1:02:03", or "2:03" below an hour.
    function clock(ms) {
        var s = Math.max(0, Math.floor(ms / 1000))
        var h = Math.floor(s / 3600)
        var m = Math.floor(s / 60) % 60
        s = s % 60
        return (h > 0 ? h + ":" + (m < 10 ? "0" : "") : "") + m + ":" + (s < 10 ? "0" : "") + s
    }

    // "15 h 48 min", "48 min"
    function hours(ms) {
        var minutes = Math.round(ms / 60000)
        if (minutes < 60)
            //: Time left in an audiobook, e.g. "48 min"
            return qsTr("%1 min").arg(minutes)
        //: Time left in an audiobook, e.g. "15 h 48 min"
        return qsTr("%1 h %2 min").arg(Math.floor(minutes / 60)).arg(minutes % 60)
    }

    function refresh() {
        shown = place()
        if (!slider.down)
            slider.value = Math.min(shown, slider.maximumValue)
    }

    function start() {
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
            // A file renamed or gone: from the start.
            if (pos && typeof pos.ms === "number") {
                for (var i = chapters.length - 1; i >= 0; --i) {
                    if (chapters[i].file === pos.file && chapters[i].begin <= pos.ms) {
                        chapter = i
                        offset = limit(i, pos.ms - chapters[i].begin)
                        break
                    }
                }
            }
            ready = true
            refresh()
        })
    }

    // To ms in chapter index; playing on if it played.
    function seek(index, ms) {
        index = Math.max(0, Math.min(chapters.length - 1, index))
        ms = limit(index, ms)
        chapter = index
        offset = ms
        moved = true
        lastHeard = { chapter: index, offset: ms }
        atEnd = false
        // Stopped by the system, the file is loaded afresh by play().
        if (player.active && player.stoppedOutside && !player.playing)
            player.stop()
        if (player.active) {
            if (index === player.chapter)
                player.jump(0, ms)
            else
                player.start(index, [clipOf(index)], 0, ms, !player.playing)
        }
        if (!player.playing)
            savePosition()
        refresh()
    }

    // Where the EPUB was read last, roughly; paused until Play.
    function goToPartner() {
        partnerShown = false
        if (!partner || !ready)
            return
        // Not at the very end: Play would begin the book again.
        var goal = Math.min(partner.progress * duration, Math.max(0, duration - 10000))
        var index = 0
        while (index + 1 < chapters.length && chapters[index + 1].start <= goal)
            ++index
        seek(index, goal - chapters[index].start)
    }

    // To ms in chapter index, and play.
    function playAt(index, ms) {
        seek(index, ms)
        play()
    }

    // By delta ms across the book, chapter by chapter: the lengths of
    // chapters not played yet may be estimates.
    function skip(delta) {
        var index = current
        var ms = place() + delta
        while (ms < 0 && index > 0) {
            --index
            ms += chapters[index].length
        }
        while (ms >= chapters[index].length && index + 1 < chapters.length) {
            ms -= chapters[index].length
            ++index
        }
        seek(index, ms)
    }

    // As in music players: to the start of the chapter, or to the previous
    // one right after a chapter began.
    function previousChapter() {
        seek(place() > 3000 || current === 0 ? current : current - 1, 0)
    }

    function nextChapter() {
        if (current + 1 < chapters.length)
            seek(current + 1, 0)
    }

    function togglePlay() {
        if (player.playing)
            pause()
        else
            play()
    }

    function play() {
        if (player.playing || closed || !ready)
            return
        if (player.active && !player.stoppedOutside) {
            player.resume()
            return
        }
        // Stopped by the system: nothing is left of the file.
        if (player.active)
            player.stop()
        var last = chapters.length - 1
        if (atEnd || chapter === last && chapters[last].length > 0
                && offset >= chapters[last].length - 1000) {
            atEnd = false
            chapter = 0
            offset = 0
        }
        player.start(chapter, [clipOf(chapter)], 0, offset)
    }

    // Paused by hand, also on the lock screen or the headphones: whoever
    // pauses is awake, so the sleep timer goes off.
    function pause() {
        if (!player.playing) {
            // Paused by an alarm or a call: then not on by itself.
            player.busy = false
            return
        }
        player.pause()
        sleepTimer.cancel()
    }

    // From the lock screen and the headphones: a chapter can last an hour,
    // and a double tap must not skip it.
    function forward() {
        skip(30000)
    }

    function back() {
        skip(-30000)
    }

    // The player first; it saves and notes the end of listening.
    function stopPlayer() {
        player.stop()
        sleepTimer.cancel()
    }

    // The player finished a chapter: on with the next, or the book is over.
    function handOver(index) {
        if (index + 1 < chapters.length) {
            player.continueWith(index + 1, [clipOf(index + 1)])
            return
        }
        atEnd = true
        stopKind = "end"
        stopPlayer()
    }

    // Every end of listening keeps the place, saves it and notes it in the
    // history, however it came.
    function playbackChanged() {
        if (player.playing) {
            partnerShown = false
            moved = true
            stopKind = ""
            // Once the player has gone to the place it starts at.
            startNote.restart()
            return
        }
        if (startNote.running) {
            startNote.stop()
            record("start")
        }
        // Still the player's chapter: stop() clears it only after this.
        if (player.index >= 0) {
            chapter = player.chapter
            if (atEnd)
                offset = chapters[chapter].length
            else if (player.why === "held")
                // The next chapter is set, its file loaded only after this.
                offset = 0
            else if (player.stoppedOutside || player.why === "error")
                offset = lastHeard && lastHeard.chapter === chapter ? lastHeard.offset : 0
            else
                offset = live()
        }
        savePosition()
        var kinds = { pause: "pause", interrupted: "interrupted", error: "interrupted", held: "timer" }
        record(stopKind || kinds[player.why] || "pause")
        stopKind = ""
        refreshSoon.restart()
    }

    // In the history and the saved place: the file and the ms in it.
    function record(kind) {
        if (player.index < 0)
            return
        var index = current
        py.call("bookfish.bridge.add_history",
                [app.historyFile, book.key, kind,
                 { spine: index, ms: Math.round(chapters[index].begin + place()) }],
                function (result) {
                    if (result !== true)
                        console.warn("Cannot note history", kind, result.error, result.detail)
                })
    }

    function savePosition() {
        // Not before the place saved has been read: it would be lost.
        if (closed || !ready)
            return
        var item = chapters[current]
        var progress = duration > 0 ? Math.min(1, (item.start + place()) / duration) : -1
        var used = moved || player.playing
        moved = false
        py.call("bookfish.bridge.save_position",
                [app.positionsFile, book.key, { file: item.file, ms: Math.round(item.begin + place()),
                                                progress: progress }, used],
                function (result) {
                    if (result !== true)
                        console.warn("Cannot save position", result.error, result.detail)
                })
    }

    // GStreamer's duration of the file playing replaces the estimate of a
    // folder opened for the first time (and a wrong one in the tags).
    function fixLength() {
        var ms = player.fileDuration
        if (!(ms > 0) || !player.active)
            return
        var changed = false
        var start = 0
        var list = chapters.map(function (item) {
            var copy = {}
            for (var key in item)
                copy[key] = item[key]
            if (copy.file === player.loadedPath && !hasEnd(copy)
                    && Math.abs(ms - copy.begin - copy.length) > 1000) {
                copy.length = Math.max(0, ms - copy.begin)
                changed = true
            }
            copy.start = start
            start += copy.length
            return copy
        })
        if (!changed)
            return
        chapters = list
        duration = start
        refresh()
    }

    function openContents() {
        var toc = chapters.map(function (item, index) {
            return { title: titleOf(index), level: 0, spine: index, fragment: "", start: item.start }
        })
        var contents = pageStack.push(Qt.resolvedUrl("TocPage.qml"),
                                      { toc: toc, currentChapter: current })
        contents.selected.connect(function (index) {
            playAt(index, 0)
        })
    }

    function openHistory() {
        var names = chapters.map(function (item, index) {
            return { title: titleOf(index), begin: item.begin }
        })
        var history = pageStack.push(Qt.resolvedUrl("FindPage.qml"),
                                     { root: book.root, bookKey: book.key, audioChapters: names,
                                       partner: partner })
        history.partnerChosen.connect(goToPartner)
        history.chosen.connect(function (place) {
            // The book may have changed since.
            if (place.spine < chapters.length)
                playAt(place.spine, place.ms - chapters[place.spine].begin)
        })
    }

    function openSleepTimer() {
        var left = chapters[current].length - place()
        pageStack.push(Qt.resolvedUrl("SleepTimerPage.qml"),
                       { timer: sleepTimer, chapterLeft: left > 0 ? left / app.playbackRate : -1 })
    }

    Component.onCompleted: {
        app.reader = page
        start()
    }
    Component.onDestruction: {
        if (app.reader === page)
            app.reader = null
    }

    // Closing the app gives no further chance to save.
    Connections {
        target: Qt.application
        onStateChanged: {
            if (Qt.application.state !== Qt.ApplicationActive)
                page.savePosition()
        }
    }

    // The files of a folder read: real lengths and names. Only if they are
    // still the same files, so the chapters played keep their numbers.
    Connections {
        target: app
        onAudiobookRead: {
            if (path !== book.path || result.error || result.chapters.length !== chapters.length)
                return
            for (var i = 0; i < chapters.length; ++i) {
                if (result.chapters[i].file !== chapters[i].file)
                    return
            }
            chapters = result.chapters
            duration = result.duration
            // The file playing knows its length best.
            fixLength()
            refresh()
        }
    }

    Player {
        id: player

        root: book.root
        rate: app.playbackRate
        onFinished: page.handOver(chapter)
        onPlayingChanged: page.playbackChanged()
        onFileDurationChanged: page.fixLength()
        // Saved already, see playbackChanged().
        onFailed: {
            page.stopPlayer()
            app.showError(qsTr("The audiobook could not be played."))
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
        id: startNote
        interval: 0
        onTriggered: page.record("start")
    }

    // After the player has loaded the place it stopped at.
    Timer {
        id: refreshSoon
        interval: 0
        onTriggered: page.refresh()
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
        interval: 20000
        repeat: true
        running: player.playing
        onTriggered: page.savePosition()
    }

    Timer {
        // Also with the screen off: see lastHeard.
        interval: 1000
        repeat: true
        running: player.playing
        onTriggered: page.lastHeard = { chapter: player.chapter, offset: page.live() }
    }

    Timer {
        interval: 500
        repeat: true
        running: player.playing && Qt.application.state === Qt.ApplicationActive
        onTriggered: page.refresh()
    }

    SilicaFlickable {
        anchors.fill: parent
        contentHeight: column.height + Theme.paddingLarge

        PullDownMenu {
            MenuItem {
                text: qsTr("Settings")
                onClicked: pageStack.push(Qt.resolvedUrl("SettingsPage.qml"))
            }
            MenuItem {
                text: qsTr("Library")
                onClicked: {
                    savePosition()
                    closed = true
                    stopKind = "close"
                    stopPlayer()
                    pageStack.pop()
                }
            }
            MenuItem {
                text: qsTr("Contents")
                onClicked: openContents()
            }
            MenuItem {
                //: Opens the listening history of an audiobook
                text: qsTr("History")
                onClicked: openHistory()
            }
        }

        Column {
            id: column

            width: parent.width
            spacing: Theme.paddingMedium

            Item {
                width: 1
                height: Theme.paddingLarge
            }

            Item {
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(page.width, page.height) * 0.6
                height: width

                Rectangle {
                    anchors.fill: parent
                    visible: cover.status !== Image.Ready
                    color: Theme.rgba(Theme.highlightBackgroundColor, Theme.opacityFaint)

                    Icon {
                        anchors.centerIn: parent
                        source: "image://theme/icon-l-music"
                    }
                }

                Image {
                    id: cover

                    anchors.fill: parent
                    source: page.coverUrl
                    sourceSize.width: width
                    sourceSize.height: height
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                }
            }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                maximumLineCount: 2
                elide: Text.ElideRight
                font.pixelSize: Theme.fontSizeLarge
                color: Theme.highlightColor
                // Text from the book, never markup.
                textFormat: Text.PlainText
                text: book.title
            }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                horizontalAlignment: Text.AlignHCenter
                truncationMode: TruncationMode.Fade
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.secondaryHighlightColor
                textFormat: Text.PlainText
                text: book.authors.join("; ")
            }

            Item {
                width: 1
                height: Theme.paddingMedium
            }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                horizontalAlignment: Text.AlignHCenter
                truncationMode: TruncationMode.Fade
                color: Theme.highlightColor
                textFormat: Text.PlainText
                text: page.chapterTitle
            }

            Slider {
                id: slider

                width: parent.width
                minimumValue: 0
                // A Slider needs a range above 0.
                maximumValue: Math.max(1, chapters[current] ? chapters[current].length : 1)
                stepSize: 1000
                // Dragging: the time under the finger.
                onValueChanged: if (down) page.shown = value
                onDownChanged: {
                    if (!down)
                        page.seek(page.current, value)
                }
            }

            Item {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                height: elapsed.height

                Label {
                    id: elapsed
                    font.pixelSize: Theme.fontSizeSmall
                    color: Theme.secondaryColor
                    text: page.clock(page.shown)
                }

                Label {
                    anchors.right: parent.right
                    font.pixelSize: Theme.fontSizeSmall
                    color: Theme.secondaryColor
                    text: chapters[current] ? "−" + page.clock(chapters[current].length - page.shown) : ""
                }
            }

            Label {
                readonly property double done: chapters[current] ? chapters[current].start + page.shown : 0

                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                horizontalAlignment: Text.AlignHCenter
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.secondaryColor
                //: Progress in an audiobook, e.g. "Book 31 % · 15 h 48 min left" (time at the speed set)
                text: qsTr("Book %1 % · %2 left")
                      .arg(page.duration > 0 ? Math.floor(100 * done / page.duration) : 0)
                      .arg(page.hours(Math.max(0, page.duration - done) / app.playbackRate))
            }

            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: Theme.paddingMedium

                IconButton {
                    anchors.verticalCenter: parent.verticalCenter
                    icon.source: "image://theme/icon-m-previous"
                    onClicked: page.previousChapter()
                }
                IconButton {
                    anchors.verticalCenter: parent.verticalCenter
                    icon.source: "image://theme/icon-m-media-rewind"
                    onClicked: page.skip(-30000)
                }
                IconButton {
                    anchors.verticalCenter: parent.verticalCenter
                    icon.source: player.playing ? "image://theme/icon-l-pause" : "image://theme/icon-l-play"
                    onClicked: page.togglePlay()
                }
                IconButton {
                    anchors.verticalCenter: parent.verticalCenter
                    icon.source: "image://theme/icon-m-media-forward"
                    onClicked: page.skip(30000)
                }
                IconButton {
                    anchors.verticalCenter: parent.verticalCenter
                    icon.source: "image://theme/icon-m-next"
                    enabled: page.current + 1 < chapters.length
                    onClicked: page.nextChapter()
                }
            }

            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: Theme.paddingLarge

                BackgroundItem {
                    width: Theme.itemSizeLarge
                    height: Theme.itemSizeSmall
                    onClicked: pageStack.push(Qt.resolvedUrl("SettingsPage.qml"))

                    Label {
                        anchors.centerIn: parent
                        color: parent.highlighted ? Theme.highlightColor : Theme.primaryColor
                        //: Playback speed on the button that opens the settings, e.g. "1.25×"
                        text: qsTr("%1×").arg(Number(app.playbackRate).toLocaleString(Qt.locale(), "f", 2))
                    }
                }
                BackgroundItem {
                    width: Theme.itemSizeLarge
                    height: Theme.itemSizeSmall
                    onClicked: page.openSleepTimer()

                    Image {
                        anchors.centerIn: parent
                        visible: sleepTimer.mode === "off"
                        source: "image://theme/icon-m-timer?" + (parent.highlighted ? Theme.highlightColor
                                                                                    : Theme.primaryColor)
                    }
                    Label {
                        anchors.centerIn: parent
                        visible: sleepTimer.mode !== "off"
                        color: parent.highlighted ? Theme.highlightColor : Theme.primaryColor
                        font.pixelSize: Theme.fontSizeSmall
                        text: sleepTimer.mode === "chapter"
                              //: Sleep timer button while it waits for the end of the chapter
                              ? qsTr("Chapter")
                              //: Sleep timer button with the minutes left, e.g. "23 min"
                              : qsTr("%1 min").arg(Math.ceil(sleepTimer.remaining / 60000))
                    }
                }
            }

            // Offered when the EPUB was read later, see start().
            Item {
                x: Theme.horizontalPageMargin
                width: parent.width - x - Theme.paddingMedium
                height: Theme.itemSizeMedium
                visible: partnerShown

                Label {
                    anchors {
                        left: parent.left
                        right: partnerButtons.left
                        verticalCenter: parent.verticalCenter
                    }
                    truncationMode: TruncationMode.Fade
                    color: Theme.secondaryHighlightColor
                    //: Offer on opening an audiobook whose book was read later, e.g. "Read to 43 %"
                    text: partner ? qsTr("Read to %1 %").arg(app.percent(partner.progress)) : ""
                }

                Row {
                    id: partnerButtons

                    anchors {
                        right: parent.right
                        verticalCenter: parent.verticalCenter
                    }
                    spacing: Theme.paddingMedium

                    Button {
                        anchors.verticalCenter: parent.verticalCenter
                        preferredWidth: Theme.buttonWidthExtraSmall
                        //: Goes to the place in the book or audiobook offered
                        text: qsTr("Go there")
                        onClicked: page.goToPartner()
                    }
                    IconButton {
                        anchors.verticalCenter: parent.verticalCenter
                        icon.source: "image://theme/icon-m-clear"
                        onClicked: partnerShown = false
                    }
                }
            }
        }

        VerticalScrollDecorator { }
    }
}
