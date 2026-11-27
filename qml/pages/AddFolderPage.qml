import QtQuick 2.0
import Sailfish.Silica 1.0
import Sailfish.Pickers 1.0

// The places a book folder can be chosen in, attached to BookFoldersPage.
// The folder picker of Sailfish OS only goes down from where it starts, and
// the phone's folders and the memory cards are apart; so first the place.
// Only Documents, Music and the cards: Bookfish may read nothing else.
Page {
    id: page

    property Item foldersPage
    // {path, name, detail, icon} of each place.
    property var places: []

    function update() {
        py.call("bookfish.bridge.default_folders", [StandardPaths.documents, StandardPaths.music],
                function (folders) {
            var cards = folders.filter(function (folder) {
                return folder !== StandardPaths.documents && folder !== StandardPaths.music
            })
            var list = [
                { path: StandardPaths.documents, name: qsTr("Documents"), detail: "",
                  icon: "image://theme/icon-m-document" },
                { path: StandardPaths.music, name: qsTr("Music"), detail: "",
                  icon: "image://theme/icon-m-music" }
            ]
            cards.forEach(function (card) {
                // Several cards are told apart by the name of their folder.
                list.push({ path: card, name: qsTr("Memory card"),
                            detail: cards.length > 1 ? card.split("/").pop() : "",
                            icon: "image://theme/icon-m-sd-card" })
            })
            places = list
        })
    }

    // A card may have been put in or taken out meanwhile.
    onStatusChanged: {
        if (status === PageStatus.Activating)
            update()
    }

    SilicaListView {
        anchors.fill: parent
        model: page.places

        header: PageHeader {
            title: qsTr("Add folder")
            description: qsTr("Choose where the folder is")
        }

        delegate: ListItem {
            id: item

            contentHeight: Theme.itemSizeMedium
            onClicked: pageStack.push(folderPicker, {
                path: modelData.path,
                // Back to the list of book folders, the new one in it.
                acceptDestination: page.foldersPage,
                acceptDestinationAction: PageStackAction.Pop
            })

            Icon {
                id: icon

                x: Theme.horizontalPageMargin
                anchors.verticalCenter: parent.verticalCenter
                source: modelData.icon
                highlighted: item.highlighted
            }

            Column {
                anchors {
                    left: icon.right
                    leftMargin: Theme.paddingLarge
                    right: parent.right
                    rightMargin: Theme.horizontalPageMargin
                    verticalCenter: parent.verticalCenter
                }

                Label {
                    width: parent.width
                    truncationMode: TruncationMode.Fade
                    color: item.highlighted ? Theme.highlightColor : Theme.primaryColor
                    text: modelData.name
                }
                Label {
                    width: parent.width
                    visible: text !== ""
                    truncationMode: TruncationMode.Fade
                    font.pixelSize: Theme.fontSizeExtraSmall
                    color: item.highlighted ? Theme.secondaryHighlightColor : Theme.secondaryColor
                    text: modelData.detail
                }
            }
        }

        VerticalScrollDecorator { }
    }

    Component {
        id: folderPicker

        FolderPickerDialog {
            //: Title of the folder picker: tap to go into a folder, accept to choose the one shown
            title: qsTr("Book folder")
            onAccepted: page.foldersPage.add(selectedPath)
        }
    }
}
