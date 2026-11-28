import QtQuick 2.0
import Sailfish.Silica 1.0

// A paragraph with ragged or justified lines, drawn for the setting
// "Text alignment" (ChoiceRow).
Item {
    id: picture

    // 0: left, 1: justified.
    property int choice: 0
    property bool chosen: false
    property bool highlighted: false

    readonly property color color: chosen || highlighted ? Theme.highlightColor : Theme.primaryColor
    readonly property real line: Math.max(1, Math.round(2 * Theme.pixelRatio))
    // Ragged line ends; the last line is short either way.
    readonly property var ragged: [0.9, 0.7, 1, 0.8, 0.5]

    Column {
        id: lines

        anchors.centerIn: parent
        width: Math.min(parent.width, 2 * parent.height) * 0.6
        spacing: 2 * picture.line

        Repeater {
            model: picture.ragged.length

            Rectangle {
                width: lines.width * (picture.choice > 0 && index < picture.ragged.length - 1
                                      ? 1 : picture.ragged[index])
                height: picture.line
                color: picture.color
                opacity: 0.6
            }
        }
    }
}
