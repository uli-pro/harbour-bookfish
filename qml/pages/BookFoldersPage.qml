import QtQuick 2.0
import Sailfish.Silica 1.0
import Sailfish.Pickers 1.0

// The book folders chosen (LibraryPage). With none chosen the library looks
// in Documents, Music and every memory card.
Page {
    id: page

    // Where the library looks without a choice (bridge.default_folders).
    property var defaultFolders: []

    // Rows are changed where they are, not the whole list replaced: a row
    // rebuilt while its removal counts down would be removed at once
    // (Silica). Folders are only added at the end, so the rows left are in
    // the order of the setting.
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
    }

    function add(path) {
        py.call("bookfish.bridge.book_folders", [app.chosenFolders, path], function (folders) {
            app.setChosenFolders(folders)
        })
    }

    function remove(path) {
        app.setChosenFolders(app.chosenFolders.filter(function (folder) {
            return folder !== path
        }))
    }

    // The folder picker starts in the folder chosen last, else on the last
    // memory card, else in Documents.
    function startPath() {
        var chosen = app.chosenFolders
        if (chosen.length > 0)
            return chosen[chosen.length - 1]
        return defaultFolders.length > 2 ? defaultFolders[defaultFolders.length - 1]
                                         : StandardPaths.documents
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
                onClicked: pageStack.push(folderPicker, { path: page.startPath() })
            }
        }

        header: PageHeader {
            //: Title of the page listing the folders the library looks in
            title: qsTr("Book folders")
        }

        ViewPlaceholder {
            enabled: list.count === 0
            text: qsTr("Documents, Music and memory cards")
            hintText: qsTr("Bookfish looks for books in all of them. Pull down to choose your own book folders instead.")
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
                    text: model.path.replace(/\/+$/, "").split("/").pop() || "/"
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

    Component {
        id: folderPicker

        FolderPickerDialog {
            title: qsTr("Add folder")
            onAccepted: page.add(selectedPath)
        }
    }
}
