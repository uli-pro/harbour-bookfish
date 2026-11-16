import QtQuick 2.0
import Sailfish.Silica 1.0

// A page in landscape with one or two columns of text, drawn for the
// setting "Columns in landscape" (ChoiceRow).
Item {
    id: picture

    // 0: one column, 1: two.
    property int choice: 0
    property bool chosen: false
    property bool highlighted: false

    readonly property color color: chosen || highlighted ? Theme.highlightColor : Theme.primaryColor
    readonly property real line: Math.max(1, Math.round(2 * Theme.pixelRatio))

    Rectangle {
        id: screen

        anchors.centerIn: parent
        // 2 : 1 as large as fits.
        width: Math.min(parent.width, 2 * parent.height)
        height: width / 2
        radius: height / 8
        color: "transparent"
        border.width: picture.line
        border.color: picture.color

        Row {
            anchors.centerIn: parent
            spacing: screen.width / 10

            Repeater {
                model: picture.choice + 1

                Column {
                    spacing: 2 * picture.line

                    Repeater {
                        model: 4

                        Rectangle {
                            width: (picture.choice > 0 ? 0.35 : 0.75) * screen.width * (index === 3 ? 0.6 : 1)
                            height: picture.line
                            color: picture.color
                            opacity: 0.6
                        }
                    }
                }
            }
        }
    }
}
