import QtQuick 2.0
import Sailfish.Silica 1.0
import "../components"

// A note of the book, with the notes around it to scroll to (see
// ReaderPage.followLink and notes.py). The reader below stays as it was;
// listening goes on.
Page {
    id: page

    // The link's text, e.g. "12" or "*"; Python lets only such marks through.
    property string mark
    // StyledText from Python: only <i>, <b> and <br>, the rest escaped.
    property var paragraphs: []
    // The note itself; the paragraphs around it are its neighbours.
    property int first: 0
    property int last: 0
    property bool lightPage: true

    // A little greyer than the book's text; the neighbours paler still.
    readonly property color noteColor: lightPage ? Qt.rgba(0, 0, 0, 0.75) : Qt.rgba(1, 1, 1, 0.75)
    readonly property color neighbourColor: lightPage ? Qt.rgba(0, 0, 0, 0.45) : Qt.rgba(1, 1, 1, 0.45)
    // A little smaller than the book on the reader (see SettingsPage): notes
    // are set smaller, and it shows where one is.
    readonly property real textSize: Math.max(app.minFontSize, app.fontSize - 6) * app.textScale

    allowedOrientations: Orientation.Portrait
    palette.colorScheme: lightPage ? Theme.DarkOnLight : Theme.LightOnDark

    Rectangle {
        anchors.fill: parent
        color: page.lightPage ? "white" : "black"
    }

    SilicaListView {
        id: listView

        anchors.fill: parent
        model: page.paragraphs
        spacing: app.paragraphSpacing * app.lineHeight * page.textSize

        header: PageHeader {
            //: Title of the page showing a note of the book, e.g. "Note 12"
            title: qsTr("Note %1").arg(page.mark)
        }

        delegate: Label {
            x: Theme.horizontalPageMargin
            width: listView.width - 2 * x
            text: modelData
            // From Python, which lets nothing but <i>, <b> and <br> through.
            textFormat: Text.StyledText
            wrapMode: Text.Wrap
            // CSS counts line height in font sizes, Qt's proportional mode
            // in the font's own (larger) line height.
            lineHeightMode: Text.FixedHeight
            lineHeight: app.lineHeight * page.textSize
            font.family: app.fontFamily === "serif" ? "serif" : "sans-serif"
            font.pixelSize: page.textSize
            color: index >= page.first && index <= page.last ? page.noteColor : page.neighbourColor
        }

        footer: Item {
            width: listView.width
            height: Theme.paddingLarge
        }

        VerticalScrollDecorator { }

        Component.onCompleted: {
            if (page.first <= 0)
                return
            positionViewAtIndex(page.first, ListView.Beginning)
            // Some of the note before shows that there is more above.
            contentY = Math.max(contentY - 1.5 * app.lineHeight * page.textSize, originY)
        }
    }

    BackShade {
        owner: page
        visible: page.lightPage && page.backNavigation
    }
}
