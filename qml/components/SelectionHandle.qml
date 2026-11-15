import QtQuick 2.0
import Sailfish.Silica 1.0

// One end of the text selected on the reading page (ReaderPage): Sailfish's
// own handle, hanging below the line, left of the start or right of the
// end. Dragging reports the point in the middle of that line that the
// finger leads, not the finger itself, so the finger does not cover the
// text. Fills its parent, so its coordinates are the parent's.
Item {
    id: handle

    // "start" or "end"; the ends may swap while one is dragged.
    property string role: "start"
    // The text's edge: x, and the top and bottom of its line.
    property real edgeX
    property real lineTop
    property real lineBottom
    property color color: Theme.highlightColor
    readonly property bool dragging: area.pressed

    signal moved(real x, real y)

    anchors.fill: parent

    Image {
        id: image

        x: handle.role === "start" ? handle.edgeX - width : handle.edgeX
        y: handle.lineBottom
        width: Theme.iconSizeSmallPlus
        height: width
        source: "image://theme/icon-m-textselection-" + handle.role + "?" + handle.color
    }

    MouseArea {
        id: area

        // Larger than the image, so it is easy to catch; it reaches up to
        // the line, not over the text before or after.
        width: Math.max(Theme.itemSizeSmall, image.width + 2 * Theme.paddingLarge)
        height: width
        x: image.x + (image.width - width) / 2
        y: image.y - Theme.paddingSmall
        // The pulley and the page's swipes must not take the drag.
        preventStealing: true

        property real offsetX
        property real offsetY

        function lead(mouse) {
            var p = mapToItem(handle, mouse.x, mouse.y)
            return Qt.point(p.x + offsetX, p.y + offsetY)
        }

        onPressed: {
            var p = mapToItem(handle, mouse.x, mouse.y)
            // Just inside the text's edge, in the middle of the line.
            offsetX = handle.edgeX + (handle.role === "start" ? 1 : -1) - p.x
            offsetY = (handle.lineTop + handle.lineBottom) / 2 - p.y
        }
        onPositionChanged: {
            var p = lead(mouse)
            handle.moved(p.x, p.y)
        }
    }
}
