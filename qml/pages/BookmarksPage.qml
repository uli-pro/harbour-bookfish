import QtQuick 2.0
import Sailfish.Silica 1.0

// The bookmarks and notes of the book (ReaderPage), in the order of the
// book. A tap goes there; the place is marked like a search hit.
Page {
    id: page

    // The reading page: its bookmarks, chapter titles and actions.
    property Item reader

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

    Component.onCompleted: sync()

    Connections {
        target: reader
        onBookmarksChanged: page.sync()
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

                Label {
                    width: parent.width
                    text: reader ? reader.tocTitle(model.spine) : ""
                    truncationMode: TruncationMode.Fade
                    font.pixelSize: Theme.fontSizeExtraSmall
                    color: item.highlighted ? Theme.secondaryHighlightColor : Theme.secondaryColor
                }
                Label {
                    width: parent.width
                    text: model.quote || model.raw
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
