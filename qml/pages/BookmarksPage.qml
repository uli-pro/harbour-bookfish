import QtQuick 2.0
import Sailfish.Silica 1.0

// The bookmarks and notes of the book (ReaderPage), in the order of the
// book. A tap goes there; the place is marked like a search hit.
Page {
    id: page

    // The reading page: its bookmarks, chapter titles and actions.
    property Item reader
    // The printed page of each bookmark, by id (bridge.page_labels).
    property var pageLabels: ({})
    property bool pagesEstimated: false
    property int pagesSerial: -1
    property var askedFor: []

    function askPages() {
        if (!reader || !reader.book)
            return
        var marks = reader.bookmarks
        askedFor = marks.map(function (mark) { return mark.id })
        pagesSerial = ++app.searchSerial
        py.call("bookfish.bridge.page_labels", [reader.book.root, marks.map(function (mark) {
            return { spine: mark.spine, offset: mark.offset }
        }), pagesSerial])
    }

    Connections {
        target: app
        onPagesFound: {
            if (serial !== page.pagesSerial)
                return
            if (result.error) {
                console.warn("Cannot read the pages", result.error, result.detail)
                return
            }
            var labels = {}
            for (var i = 0; i < page.askedFor.length; ++i)
                labels[page.askedFor[i]] = result.labels[i]
            page.pagesEstimated = result.estimated
            page.pageLabels = labels
        }
    }

    // Rows are changed where they are, not the whole list replaced: a row
    // rebuilt while its delete counts down would delete at once (Silica),
    // and the list would jump to the top.
    function sync() {
        var marks = reader ? reader.bookmarks : []
        var ids = {}
        marks.forEach(function (mark) { ids[mark.id] = true })
        for (var i = rows.count - 1; i >= 0; --i) {
            if (!ids[rows.get(i).ident])
                rows.remove(i)
        }
        for (var j = 0; j < marks.length; ++j) {
            var row = { ident: marks[j].id, spine: marks[j].spine, offset: marks[j].offset,
                        chars: marks[j].length, raw: marks[j].raw, quote: marks[j].quote,
                        note: marks[j].note }
            var k = j
            while (k < rows.count && rows.get(k).ident !== row.ident)
                ++k
            if (k === rows.count) {
                rows.insert(j, row)
            } else {
                if (k !== j)
                    rows.move(k, j, 1)
                rows.set(j, row)
            }
        }
    }

    Component.onCompleted: {
        sync()
        askPages()
    }

    Connections {
        target: reader
        onBookmarksChanged: {
            page.sync()
            page.askPages()
        }
    }

    ListModel {
        id: rows
    }

    SilicaListView {
        id: list

        anchors.fill: parent
        model: rows

        header: PageHeader {
            //: Title of the list of bookmarks and notes
            title: qsTr("Bookmarks")
        }

        ViewPlaceholder {
            enabled: list.count === 0
            text: qsTr("No bookmarks yet")
            hintText: qsTr("Long press on text to add one")
        }

        delegate: ListItem {
            id: item

            contentHeight: column.height + 2 * Theme.paddingMedium

            menu: ContextMenu {
                MenuItem {
                    text: qsTr("Edit note")
                    onClicked: {
                        var mark = reader.bookmark(model.ident)
                        if (mark)
                            reader.editNote(mark)
                    }
                }
                MenuItem {
                    text: qsTr("Delete")
                    onClicked: {
                        // Taken now: the row may be gone when it runs.
                        var target = reader
                        var ident = model.ident
                        item.remorseAction(qsTr("Deleting"), function () {
                            target.deleteBookmarkNow(ident)
                        })
                    }
                }
            }

            onClicked: {
                // Shown once the reading page is back (showPending).
                reader.pendingPlace = { spine: model.spine, offset: model.offset,
                                        length: model.chars, text: model.raw }
                pageStack.pop()
            }

            Column {
                id: column

                x: Theme.horizontalPageMargin
                y: Theme.paddingMedium
                width: parent.width - 2 * x

                // The chapter, and the page right beside it: never cut off.
                Item {
                    width: parent.width
                    height: chapterLabel.height

                    Label {
                        id: chapterLabel

                        width: parent.width - (pageLabel.text !== "" ? pageLabel.width + Theme.paddingMedium : 0)
                        text: reader ? reader.tocTitle(model.spine) : ""
                        textFormat: Text.PlainText
                        truncationMode: TruncationMode.Fade
                        font.pixelSize: Theme.fontSizeExtraSmall
                        color: item.highlighted ? Theme.secondaryHighlightColor : Theme.secondaryColor
                    }
                    Label {
                        id: pageLabel

                        anchors.right: parent.right
                        text: app.pageText(page.pageLabels[model.ident] || "", page.pagesEstimated)
                        font.pixelSize: Theme.fontSizeExtraSmall
                        color: item.highlighted ? Theme.secondaryHighlightColor : Theme.secondaryColor
                    }
                }
                Label {
                    width: parent.width
                    text: model.quote || model.raw
                    textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                    font.pixelSize: Theme.fontSizeSmall
                    color: item.highlighted ? Theme.secondaryHighlightColor : Theme.secondaryColor
                }
                Label {
                    width: parent.width
                    visible: model.note !== ""
                    text: model.note
                    textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                    font.pixelSize: Theme.fontSizeSmall
                    color: item.highlighted ? Theme.highlightColor : Theme.primaryColor
                }
            }
        }

        VerticalScrollDecorator {}
    }
}
