import QtQuick 2.0
import Sailfish.Silica 1.0

// A button of the reader's low bars: a small icon or a short text, as tall
// as the bar and wide, so it is easy to hit although the bar is low. The
// icon sits above the middle, away from the rounded bottom edge of the
// screen; the button still takes taps down to the edge. IconButton has a
// fixed size taller than the bar.
BackgroundItem {
    id: button

    property string iconName
    property alias text: label.text
    property color textColor: palette.primaryColor
    readonly property real iconSize: Theme.iconSizeSmallPlus

    // Only used where the button is as wide as its content.
    implicitWidth: (iconName !== "" ? iconSize : label.implicitWidth) + 2 * Theme.paddingLarge
    height: parent.height
    opacity: enabled ? 1 : Theme.opacityLow

    // The part above the edge, where icon and text are centred.
    Item {
        id: face

        width: parent.width
        height: parent.height - Theme.paddingMedium
    }

    Image {
        anchors.centerIn: face
        visible: button.iconName !== ""
        width: button.iconSize
        height: button.iconSize
        sourceSize: Qt.size(width, height)
        source: button.iconName !== ""
                ? "image://theme/" + button.iconName + "?"
                  + (button.highlighted ? palette.highlightColor : palette.primaryColor)
                : ""
    }

    Label {
        id: label

        anchors.centerIn: face
        visible: text !== ""
        color: button.highlighted ? palette.highlightColor : button.textColor
        font.pixelSize: Theme.fontSizeSmall
    }
}
