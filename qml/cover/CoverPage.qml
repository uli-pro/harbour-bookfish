import QtQuick 2.0
import Sailfish.Silica 1.0

// The open book's cover, or its title and authors if it has none that
// can be shown; the app's name while the library is shown.
CoverBackground {
    id: cover

    readonly property var book: app.reader ? app.reader.book : null
    readonly property bool hasAudio: app.reader !== null && app.reader.hasAudio

    Image {
        id: image

        anchors.fill: parent
        source: app.reader ? app.reader.coverUrl : ""
        // Qt 5.6 decodes to fit inside sourceSize; cropped, a square cover
        // would be enlarged and blurred.
        sourceSize.width: Math.max(width, height)
        sourceSize.height: Math.max(width, height)
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        visible: status === Image.Ready
    }

    // Behind the play button: on a light cover it would hardly show.
    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width
        height: Theme.itemSizeLarge
        visible: image.visible && cover.hasAudio
        gradient: Gradient {
            GradientStop { position: 0; color: "transparent" }
            GradientStop { position: 1; color: Qt.rgba(0, 0, 0, 0.7) }
        }
    }

    Column {
        x: Theme.paddingLarge
        width: parent.width - 2 * x
        anchors.verticalCenter: parent.verticalCenter
        // Above the play button, if there is one.
        anchors.verticalCenterOffset: cover.hasAudio ? -Theme.paddingLarge : 0
        spacing: Theme.paddingSmall
        // Not while the cover loads: the title would flash.
        visible: cover.book !== null && (image.status === Image.Null || image.status === Image.Error)

        Label {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            maximumLineCount: 4
            truncationMode: TruncationMode.Elide
            font.pixelSize: Theme.fontSizeMedium
            textFormat: Text.PlainText
            // A book without a title: the app's name.
            text: cover.book && cover.book.title ? cover.book.title : qsTr("Bookfish")
        }

        Label {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            maximumLineCount: 2
            truncationMode: TruncationMode.Elide
            font.pixelSize: Theme.fontSizeExtraSmall
            color: Theme.secondaryColor
            textFormat: Text.PlainText
            text: cover.book && cover.book.authors ? cover.book.authors.join("; ") : ""
        }
    }

    Label {
        anchors.centerIn: parent
        visible: cover.book === null
        //: Application name, usually not translated
        text: qsTr("Bookfish")
    }

    CoverActionList {
        enabled: cover.hasAudio

        CoverAction {
            iconSource: app.reader && app.reader.playing ? "image://theme/icon-cover-pause"
                                                          : "image://theme/icon-cover-play"
            onTriggered: app.reader.togglePlay()
        }
    }
}
