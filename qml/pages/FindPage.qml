import QtQuick 2.0
import Sailfish.Silica 1.0

// Search in the open book: every paragraph holding all words typed. With
// nothing typed, the history: where reading and listening started, went on
// and ended, newest first. For an audiobook only the history.
Page {
    id: page

    property string root
    property string bookKey
    // The reader's place: {spine, id, fraction, heard, offset}, see ReaderPage.here().
    property var here
    // The words searched last in this book, shown again.
    property string initialQuery: ""
    property int serial: 0
    property string query: ""
    property bool searching: false
    // {hits, total, before} of the last search, see search.py, and its words.
    property var result: null
    property string resultQuery: ""
    property string searchedQuery: ""
    // The entries of the history shown, in the order of the rows.
    property var places: []
    // An audiobook's chapters, [{title, begin}]; null for an EPUB.
    property var audioChapters: null
    readonly property bool audio: audioChapters !== null
    // The other form of the book, see bridge.partner: its place is offered
    // above the history.
    property var partner: null

    // The hits and the one chosen, for going from hit to hit in the book.
    signal selected(var hits, int index, string query)
    // An entry of the history chosen: {spine, offset, length, text},
    // see bridge.history.
    signal chosen(var place)
    // The place of the partner chosen.
    signal partnerChosen()

    function chapterName(item) {
        //: Chapter of a search hit without a title, e.g. "Chapter 12"
        return item.chapter || qsTr("Chapter %1").arg(item.spine + 1)
    }

    // Rows are hits ("hit"), the line at the reader's place ("here"),
    // headings of sessions of reading or listening ("session") and their entries
    // ("entry"). A ListModel, not an array: a new array resets the list's
    // current item, which then takes the focus from the search field.
    function fillRows() {
        rows.clear()
        places = []
        if (!result || !result.hits)
            return
        var hits = result.hits
        for (var i = 0; i < hits.length; ++i) {
            if (i === result.before)
                rows.append(row("here", "", "", "", -1))
            rows.append(row("hit", "", snippetText(hits[i].snippet), chapterName(hits[i]), i))
        }
        // The place after the last hit; not if hits after it were left out.
        if (hits.length > 0 && result.before === hits.length && result.total === hits.length)
            rows.append(row("here", "", "", "", -1))
    }

    function fillHistory(sessions) {
        rows.clear()
        var list = []
        for (var i = 0; i < sessions.length; ++i) {
            rows.append(row("session", sessionText(sessions[i]), "", "", -1))
            var entries = sessions[i].entries
            for (var j = 0; j < entries.length; ++j) {
                var entry = entries[j]
                var info = timeText(entry.time) + " · " + kindText(entry.kind)
                if (audio)
                    rows.append(row("entry", info, escaped(audioPlace(entry)), "", list.length))
                else
                    rows.append(row("entry", info, escaped(entry.line), chapterName(entry), list.length))
                list.push(entry)
            }
        }
        places = list
    }

    // "Chapter 12 · 23:45": the time in the chapter.
    function audioPlace(entry) {
        var chapter = audioChapters[entry.spine]
        if (!chapter)
            return chapterName({ spine: entry.spine })
        var s = Math.max(0, Math.floor((entry.ms - chapter.begin) / 1000))
        var h = Math.floor(s / 3600)
        var m = Math.floor(s / 60) % 60
        s = s % 60
        var time = (h > 0 ? h + ":" + (m < 10 ? "0" : "") : "") + m + ":" + (s < 10 ? "0" : "") + s
        return chapter.title + " · " + time
    }

    function row(type, info, html, chapter, hit) {
        return { type: type, info: info, html: html, chapter: chapter, hit: hit }
    }

    function timeText(seconds) {
        return new Date(seconds * 1000).toLocaleTimeString(Qt.locale(), Locale.ShortFormat)
    }

    // "Today", "Yesterday" or the date.
    function dayText(seconds) {
        var start = new Date(seconds * 1000)
        var day = new Date(start.getFullYear(), start.getMonth(), start.getDate())
        var now = new Date()
        var today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
        var days = Math.round((today - day) / 86400000)
        return days === 0
                //: Heading of a session of reading or listening today, before its times
                ? qsTr("Today")
                : days === 1
                  //: Heading of a session of reading or listening yesterday, before its times
                  ? qsTr("Yesterday")
                  : start.toLocaleDateString(Qt.locale(), Locale.ShortFormat)
    }

    // "Audiobook · Today, 14:05"; without the time if it is not known (a
    // place stored before it was kept).
    function partnerInfo() {
        if (!partner)
            return ""
        var audiobook = partner.kind === "audiobook"
        if (!(partner.time > 0))
            //: Above the history: the place of this book's audiobook follows
            return audiobook ? qsTr("Audiobook")
                             //: Above an audiobook's history: the place of its book follows
                             : qsTr("Book")
        var day = dayText(partner.time)
        var time = timeText(partner.time)
        return audiobook
                //: Above the history: when the audiobook of this book was listened to last, e.g. "Audiobook · Today, 14:05"
                ? qsTr("Audiobook · %1, %2").arg(day).arg(time)
                //: Above an audiobook's history: when its book was read last, e.g. "Book · Today, 14:05"
                : qsTr("Book · %1, %2").arg(day).arg(time)
    }

    // "Reading · Today, 22:40–23:15"
    function sessionText(session) {
        var date = dayText(session.start)
        var times = timeText(session.start)
        if (timeText(session.end) !== times)
            times += "–" + timeText(session.end)
        return session.mode === "reading"
                //: Heading of a reading session: day and times, e.g. "Reading · Today, 22:40–23:15"
                ? qsTr("Reading · %1, %2").arg(date).arg(times)
                //: Heading of a listening session: day and times, e.g. "Listening · Today, 22:40–23:15"
                : qsTr("Listening · %1, %2").arg(date).arg(times)
    }

    function kindText(kind) {
        switch (kind) {
        case "start":
            //: Listening history: listening began here
            return qsTr("Started")
        case "mark":
            //: Listening history: noted every few minutes while listening
            return qsTr("Listening")
        case "pause":
            //: Listening history: paused here
            return qsTr("Paused")
        case "interrupted":
            //: Listening history: stopped by the phone (headphones gone, a call, an error)
            return qsTr("Interrupted")
        case "timer":
            //: Listening history: the sleep timer ended listening here
            return qsTr("Sleep timer")
        case "close":
            //: History: the book was closed while reading or listening
            return qsTr("Book closed")
        case "read":
            //: History: reading began here (the page the book was opened at, or came back to)
            return qsTr("Started reading")
        case "page":
            //: History: noted every few minutes while reading
            return qsTr("Reading")
        case "jump":
            //: History: left this page for the contents, a search hit or the history
            return qsTr("Jumped away")
        case "away":
            //: History: left the app while reading here
            return qsTr("Left the app")
        default:
            //: Listening history: the narration reached the end of the book
            return qsTr("End of book")
        }
    }

    function escaped(text) {
        return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    }

    // The words of the book are plain text; only our own tags mark them.
    function snippetText(parts) {
        var color = Theme.highlightColor
        return parts.map(function (part) {
            var text = escaped(part.text)
            return part.match ? "<font color=\"" + color + "\"><b>" + text + "</b></font>" : text
        }).join("")
    }

    function search() {
        if (audio) {
            searching = true
            py.call("bookfish.bridge.audio_history", [app.historyFile, bookKey], function (result) {
                searching = false
                fillHistory(result.sessions)
            })
            return
        }
        var text = query.trim()
        serial = ++app.searchSerial
        if (text.length < 2) {
            result = null
            fillRows()
            searching = true
            py.call("bookfish.bridge.history", [root, app.historyFile, bookKey, serial])
            return
        }
        searching = true
        searchedQuery = text
        py.call("bookfish.bridge.search", [root, text, here, serial])
    }

    Component.onCompleted: {
        if (audio) {
            search()
            return
        }
        py.call("bookfish.bridge.prepare_search", [root])
        // A text set in the field does not change it when empty.
        if (initialQuery.trim().length < 2)
            search()
    }
    // The keyboard only when there is nothing else to see: it would push
    // the history out of sight.
    onStatusChanged: {
        if (status === PageStatus.Active && !audio && query === "" && !searching
                && places.length === 0)
            listView.headerItem.field.forceActiveFocus()
    }

    Connections {
        target: app
        onSearchFinished: {
            if (serial !== page.serial)
                return
            searching = false
            if (result.error) {
                page.result = null
                app.showError(app.errorText(result.error))
            } else {
                page.result = result
                resultQuery = searchedQuery
            }
            fillRows()
        }
        onHistoryFinished: {
            if (serial !== page.serial)
                return
            searching = false
            if (result.error) {
                // The search is still there; it reports the error itself.
                console.warn("Cannot show history", result.error, result.detail)
                fillHistory([])
            } else {
                fillHistory(result.sessions)
            }
            if (places.length === 0 && query === "" && status === PageStatus.Active)
                listView.headerItem.field.forceActiveFocus()
        }
    }

    Timer {
        id: typingTimer
        interval: 300
        onTriggered: page.search()
    }

    SilicaListView {
        id: listView

        anchors.fill: parent
        model: ListModel { id: rows }
        // Otherwise the current item takes the focus from the search field
        // whenever the hits change.
        currentIndex: -1

        header: Column {
            property alias field: field

            width: listView.width

            // Search and history, each with a heading instead of one for
            // the page.
            Column {
                visible: !page.audio
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x

                Item {
                    width: 1
                    height: Theme.paddingLarge
                }

                Label {
                    width: parent.width
                    color: Theme.highlightColor
                    truncationMode: TruncationMode.Fade
                    //: Heading of the search on the page with search and history
                    text: qsTr("Find in this book")
                }

                Label {
                    width: parent.width
                    // Room for the hits while typing.
                    visible: page.query.trim().length < 2
                    truncationMode: TruncationMode.Fade
                    font.pixelSize: Theme.fontSizeExtraSmall
                    color: Theme.secondaryHighlightColor
                    //: Below the heading of the search
                    text: qsTr("All words, in any order")
                }
            }

            SearchField {
                id: field
                visible: !page.audio
                width: parent.width
                //: Placeholder of the search field
                placeholderText: qsTr("Words in the book")
                inputMethodHints: Qt.ImhNoPredictiveText
                Component.onCompleted: text = page.initialQuery
                onTextChanged: {
                    page.query = text
                    typingTimer.restart()
                }
                EnterKey.iconSource: "image://theme/icon-m-enter-close"
                EnterKey.onClicked: focus = false
            }

            // Where the other form of the book is, above the history.
            BackgroundItem {
                width: parent.width
                height: partnerColumn.height + 2 * Theme.paddingMedium
                visible: !!page.partner && page.partner.progress >= 0
                         && page.query.trim().length < 2
                onClicked: {
                    Qt.inputMethod.hide()
                    page.partnerChosen()
                    pageStack.pop()
                }

                Column {
                    id: partnerColumn

                    x: Theme.horizontalPageMargin
                    y: Theme.paddingMedium
                    width: parent.width - 2 * x

                    Label {
                        width: parent.width
                        truncationMode: TruncationMode.Fade
                        font.pixelSize: Theme.fontSizeExtraSmall
                        color: parent.parent.highlighted ? Theme.highlightColor : Theme.secondaryHighlightColor
                        text: page.partnerInfo()
                    }

                    Label {
                        width: parent.width
                        truncationMode: TruncationMode.Fade
                        color: parent.parent.highlighted ? Theme.highlightColor : Theme.primaryColor
                        text: !page.partner ? ""
                              : page.partner.kind === "audiobook"
                                //: Offer on opening a book whose audiobook was listened to later, e.g. "Listened to 43 %"
                                ? qsTr("Listened to %1 %").arg(app.percent(page.partner.progress))
                                //: Offer on opening an audiobook whose book was read later, e.g. "Read to 43 %"
                                : qsTr("Read to %1 %").arg(app.percent(page.partner.progress))
                    }
                }
            }

            // Which of the two lists is shown: the history or the hits.
            Column {
                readonly property bool history: page.query.trim().length < 2 && page.places.length > 0
                readonly property bool hits: page.query.trim().length >= 2 && !!page.result
                                             && !!page.result.hits

                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                visible: history || hits

                Item {
                    width: 1
                    height: Theme.paddingLarge
                }

                Label {
                    width: parent.width
                    color: Theme.highlightColor
                    truncationMode: TruncationMode.Fade
                    text: parent.history
                          //: Heading of the history of reading and listening on the search page
                          ? qsTr("History")
                          : !parent.hits ? ""
                          : page.result.total === 1
                            //: Heading of the search hits, one hit
                            ? qsTr("1 hit")
                            //: Heading of the search hits, e.g. "39 hits"
                            : qsTr("%1 hits").arg(page.result.total)
                }

                Label {
                    width: parent.width
                    visible: parent.history
                    truncationMode: TruncationMode.Fade
                    font.pixelSize: Theme.fontSizeExtraSmall
                    color: Theme.secondaryHighlightColor
                    text: page.audio
                          //: Below the heading of an audiobook's history
                          ? qsTr("Newest first – tap to listen there")
                          //: Below the heading of the history
                          : qsTr("Newest first – tap to go there")
                }
            }
        }

        delegate: ListItem {
            id: item

            readonly property bool heading: model.type === "here" || model.type === "session"

            contentHeight: heading ? Theme.itemSizeExtraSmall
                                   : column.height + 2 * Theme.paddingMedium
            enabled: !heading

            // The reader's place among the hits, or a session of the history.
            SectionHeader {
                visible: item.heading
                anchors.verticalCenter: parent.verticalCenter
                text: model.type === "session" ? model.info
                      : page.here && page.here.heard
                        //: Line in the search hits: hits below it have not been heard yet
                        ? qsTr("Last heard")
                        //: Line in the search hits: hits below it come after the page shown
                        : qsTr("Current page")
            }

            Column {
                id: column

                visible: !item.heading
                x: Theme.horizontalPageMargin
                y: Theme.paddingMedium
                width: parent.width - 2 * x

                Label {
                    width: parent.width
                    visible: model.type === "entry"
                    font.pixelSize: Theme.fontSizeExtraSmall
                    color: item.highlighted ? Theme.highlightColor : Theme.secondaryHighlightColor
                    text: model.info
                }

                Label {
                    width: parent.width
                    wrapMode: Text.Wrap
                    maximumLineCount: 4
                    elide: Text.ElideRight
                    textFormat: Text.StyledText
                    text: model.html
                    color: item.highlighted ? Theme.highlightColor : Theme.primaryColor
                }

                Label {
                    width: parent.width
                    truncationMode: TruncationMode.Fade
                    font.pixelSize: Theme.fontSizeExtraSmall
                    color: Theme.secondaryColor
                    text: model.chapter
                    // Text from the book, never markup.
                    textFormat: Text.PlainText
                }
            }

            onClicked: {
                // The reader lays the chapter out for the full height.
                Qt.inputMethod.hide()
                if (model.type === "entry")
                    page.chosen(page.places[model.hit])
                else
                    page.selected(result.hits, model.hit, resultQuery)
                pageStack.pop()
            }
        }

        footer: Label {
            x: Theme.horizontalPageMargin
            width: listView.width - 2 * x
            height: visible ? implicitHeight + 2 * Theme.paddingLarge : 0
            verticalAlignment: Text.AlignVCenter
            visible: !!result && !!result.hits && result.total > result.hits.length
            wrapMode: Text.Wrap
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.secondaryHighlightColor
            //: Shown below a cut-off list of search hits, e.g. "200 of 1534 hits. Add a word to narrow them down."
            text: result ? qsTr("%1 of %2 hits. Add a word to narrow them down.")
                           .arg(result.hits.length).arg(result.total) : ""
        }

        ViewPlaceholder {
            enabled: !searching && rows.count === 0
            text: page.audio
                  //: An audiobook not listened to yet
                  ? qsTr("No history yet")
                  : query.trim().length < 2
                  //: Hint on the empty search page
                  ? qsTr("Type words from the book")
                  //: The search found nothing
                  : qsTr("Nothing found")
        }

        BusyIndicator {
            anchors.horizontalCenter: parent.horizontalCenter
            y: page.height / 2
            size: BusyIndicatorSize.Large
            running: searching && rows.count === 0
        }

        VerticalScrollDecorator { }
    }
}
