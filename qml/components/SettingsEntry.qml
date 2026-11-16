import QtQuick 2.0
import Sailfish.Silica 1.0

// An entry of the settings that opens a page of them, showing what is set
// there in a second line.
BackgroundItem {
    id: entry

    property alias title: titleLabel.text
    property alias summary: summaryLabel.text

    width: parent.width
    height: column.height + 2 * Theme.paddingMedium

    Column {
        id: column

        x: Theme.horizontalPageMargin
        width: parent.width - 2 * x
        anchors.verticalCenter: parent.verticalCenter

        Label {
            id: titleLabel

            width: parent.width
            truncationMode: TruncationMode.Fade
            color: entry.highlighted ? Theme.highlightColor : Theme.primaryColor
            // Not available now: dimmed; the second line says why.
            opacity: entry.enabled ? 1 : Theme.opacityLow
        }
        Label {
            id: summaryLabel

            width: parent.width
            truncationMode: TruncationMode.Fade
            font.pixelSize: Theme.fontSizeExtraSmall
            color: entry.highlighted ? Theme.secondaryHighlightColor : Theme.secondaryColor
        }
    }
}
