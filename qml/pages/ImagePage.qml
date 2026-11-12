import QtQuick 2.0
import Sailfish.Silica 1.0
import "../components"

// A picture of the book, to look at closely (see ReaderPage.showPicture).
// At first it fits the screen; it is enlarged up to four times that.
Page {
    id: page

    property url source
    property color pageColor

    // Relative to fitting the screen, so turning the phone keeps it.
    property real zoom: 1
    readonly property real fitScale: image.implicitWidth > 0 && image.implicitHeight > 0
                                     ? Math.min(width / image.implicitWidth, height / image.implicitHeight)
                                     : 1
    readonly property bool zoomed: zoom > 1.01

    // Keeps the point at cx, cy of the screen where it is.
    function zoomTo(value, cx, cy) {
        if (image.status !== Image.Ready || image.width <= 0 || image.height <= 0)
            return
        // A pinch that ends barely above fitting the screen fits it.
        if (value < 1.01)
            value = 1
        var px = (flick.contentX + cx - image.x) / image.width
        var py = (flick.contentY + cy - image.y) / image.height
        zoom = Math.max(1, Math.min(4, value))
        flick.contentX = Math.max(0, Math.min(flick.contentWidth - flick.width,
                                              image.x + px * image.width - cx))
        flick.contentY = Math.max(0, Math.min(flick.contentHeight - flick.height,
                                              image.y + py * image.height - cy))
    }

    allowedOrientations: Orientation.All
    // Enlarged, a swipe moves the picture instead of leaving the page.
    backNavigation: !zoomed

    Rectangle {
        anchors.fill: parent
        color: page.pageColor
    }

    PinchArea {
        anchors.fill: parent
        enabled: image.status === Image.Ready

        onPinchUpdated: page.zoomTo(page.zoom * pinch.scale / pinch.previousScale,
                                    pinch.center.x, pinch.center.y)
        onPinchFinished: {
            if (!page.zoomed)
                page.zoomTo(1, pinch.center.x, pinch.center.y)
            flick.returnToBounds()
        }

        SilicaFlickable {
            id: flick

            anchors.fill: parent
            contentWidth: Math.max(width, image.width)
            contentHeight: Math.max(height, image.height)
            interactive: page.zoomed
            // A delayed press may keep the second finger from the PinchArea.
            pressDelay: 0

            Image {
                id: image

                x: (flick.contentWidth - width) / 2
                y: (flick.contentHeight - height) / 2
                width: implicitWidth * page.fitScale * page.zoom
                height: implicitHeight * page.fitScale * page.zoom
                source: page.source
                asynchronous: true
                smooth: true
            }

            MouseArea {
                width: flick.contentWidth
                height: flick.contentHeight
                onDoubleClicked: page.zoomTo(page.zoomed ? 1 : 2.5,
                                             mouse.x - flick.contentX, mouse.y - flick.contentY)
            }
        }
    }

    BackShade {
        owner: page
        enabled: page.pageColor.r > 0.5
        visible: enabled && page.backNavigation
    }

    BusyIndicator {
        anchors.centerIn: parent
        size: BusyIndicatorSize.Large
        running: image.status === Image.Loading
    }
}
