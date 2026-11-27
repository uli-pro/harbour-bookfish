import QtQuick 2.0
import Sailfish.Silica 1.0

// The book folders chosen (LibraryPage). With none chosen the library looks
// in Documents, Music and every memory card. The places to add one from are
// attached: a swipe to the left.
Page {
    id: page

    // Rows are changed where they are, not the whole list replaced: a row
    // rebuilt while its removal counts down would be removed at once
    // (Silica).
    function sync() {
        var folders = app.chosenFolders
        for (var i = rows.count - 1; i >= 0; --i) {
            if (folders.indexOf(rows.get(i).path) < 0)
                rows.remove(i)
        }
        for (var j = 0; j < folders.length; ++j) {
            if (j >= rows.count || rows.get(j).path !== folders[j])
                rows.insert(j, { path: folders[j] })
        }
        // Left over if the setting changed its order.
        while (rows.count > folders.length)
            rows.remove(rows.count - 1)
    }

    // Called by AddFolderPage. Read when it is written: a removal may have
    // ended meanwhile.
    function add(path) {
        path = path.replace(/\/+$/, "") || "/"
        if (app.chosenFolders.indexOf(path) < 0)
            app.setChosenFolders(app.chosenFolders.concat([path]))
    }

    function remove(path) {
        app.setChosenFolders(app.chosenFolders.filter(function (folder) {
            return folder !== path
        }))
    }

    onStatusChanged: {
        if (status === PageStatus.Active && !pageStack.nextPage(page))
            pageStack.pushAttached(Qt.resolvedUrl("AddFolderPage.qml"), { foldersPage: page })
    }

    Component.onCompleted: sync()

    Connections {
        target: app
        onChosenFoldersChanged: page.sync()
    }

    SilicaListView {
        id: list

        anchors.fill: parent
        model: ListModel { id: rows }

        PullDownMenu {
            MenuItem {
                text: qsTr("Add folder")
                onClicked: pageStack.navigateForward()
            }
        }

        header: PageHeader {
            //: Title of the page listing the folders the library looks in
            title: qsTr("Book folders")
        }

        ViewPlaceholder {
            enabled: list.count === 0
            text: qsTr("Documents, Music and memory cards")
            hintText: qsTr("Bookfish looks for books in all of them. Swipe left to choose your own book folders instead.")
        }

        delegate: ListItem {
            id: item

            contentHeight: column.height + 2 * Theme.paddingMedium

            menu: ContextMenu {
                MenuItem {
                    //: Takes a folder off the list of book folders; nothing is deleted
                    text: qsTr("Remove")
                    onClicked: {
                        // Taken now: the row may be gone when it runs.
                        var path = model.path
                        item.remorseAction(qsTr("Removing"), function () {
                            page.remove(path)
                        })
                    }
                }
            }

            Column {
                id: column

                x: Theme.horizontalPageMargin
                y: Theme.paddingMedium
                width: parent.width - 2 * x

                Label {
                    width: parent.width
                    truncationMode: TruncationMode.Fade
                    color: item.highlighted ? Theme.highlightColor : Theme.primaryColor
                    text: model.path.split("/").pop() || "/"
                }
                Label {
                    width: parent.width
                    wrapMode: Text.WrapAnywhere
                    font.pixelSize: Theme.fontSizeExtraSmall
                    color: item.highlighted ? Theme.secondaryHighlightColor : Theme.secondaryColor
                    text: model.path
                }
            }
        }

        VerticalScrollDecorator { }
    }
}
