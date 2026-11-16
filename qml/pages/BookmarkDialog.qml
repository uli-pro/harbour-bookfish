import QtQuick 2.0
import Sailfish.Silica 1.0

// The note of a bookmark (ReaderPage): the text of the place above, the note
// below with the keyboard. Save stores it; Cancel or going back leaves all
// as it was, and a new bookmark is not made.
Dialog {
    id: dialog

    property string quote
    property string chapterTitle
    property alias note: area.text
    // An existing bookmark can be deleted here; with a note, it is called
    // a note.
    property bool existing: false
    property bool hasNote: false
    property bool focused: false

    // After the delay to take it back.
    signal deleteRequested()

    onStatusChanged: {
        if (status === PageStatus.Active && !focused) {
            focused = true
            area.forceActiveFocus()
        }
    }

    SilicaFlickable {
        anchors.fill: parent
        contentHeight: column.height

        PullDownMenu {
            visible: dialog.existing

            MenuItem {
                text: dialog.hasNote ? qsTr("Delete note") : qsTr("Delete bookmark")
                onClicked: remorse.execute(dialog.hasNote ? qsTr("Deleting note") : qsTr("Deleting bookmark"),
                                           function () {
                    dialog.deleteRequested()
                    dialog.reject()
                })
            }
        }

        Column {
            id: column

            width: parent.width

            DialogHeader {
                //: Stores the note of a bookmark
                acceptText: qsTr("Save")
            }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                visible: text !== ""
                text: dialog.chapterTitle
                textFormat: Text.PlainText
                truncationMode: TruncationMode.Fade
                font.pixelSize: Theme.fontSizeExtraSmall
                color: Theme.secondaryHighlightColor
            }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                text: dialog.quote
                textFormat: Text.PlainText
                wrapMode: Text.Wrap
                maximumLineCount: 4
                elide: Text.ElideRight
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.secondaryColor
            }

            Item {
                width: 1
                height: Theme.paddingLarge
            }

            TextArea {
                id: area

                width: parent.width
                //: Field for the note of a bookmark
                placeholderText: qsTr("Note")
                label: placeholderText
            }
        }

        VerticalScrollDecorator {}
    }

    RemorsePopup {
        id: remorse
    }
}
