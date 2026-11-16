import QtQuick 2.0
import Sailfish.Silica 1.0

// The page flip view of the reading page (lernen/32): pictures of nine
// screen pages, the one in the middle the page chosen, four before and four
// after it in reading order; a bar over the whole book below. It fills the
// screen, so the reading page behind can load other chapters to draw them.
Rectangle {
    id: grid

    // [{chapter, page, url, label}] in reading order, null beyond the book;
    // url "" while the picture is not drawn yet.
    property var tiles: []
    // The bar's stops (see bridge.flip_stops) and the one of the page in
    // the middle; whether the pages are estimated and the highest one.
    property var stops: []
    property int current: -1
    property bool estimated: false
    property int total: 0
    // Shown until the stops are read.
    property string currentText
    // A screen page's height by its width.
    property real tileAspect: 1.5
    property color pageColor
    property color lineColor
    // Waiting for a chapter to be laid out.
    property bool busy: false
    readonly property int shown: slider.down ? Math.round(slider.sliderValue) : current
    // The width of a picture on the screen, in pixels: the pictures are
    // drawn that wide.
    readonly property real cellWidth: Math.floor(Math.min(
        (width - 2 * Theme.paddingMedium - 2 * gap) / 3,
        ((cells.height - 2 * gap) / 3 - labelHeight) / tileAspect))
    readonly property real cellHeight: Math.round(cellWidth * tileAspect)
    readonly property real gap: Theme.paddingSmall
    readonly property real labelHeight: Math.round(1.3 * Theme.fontSizeTiny)

    signal tileTapped(int index)
    signal swiped(int delta)
    // While the bar is dragged, and when it is let go.
    signal dragged(int index)
    signal chosen(int index)
    signal goToRequested()
    signal closeRequested()

    function stopText(i) {
        var stop = stops[i]
        if (!stop)
            return currentText
        if (!stop.label)
            //: Place in the page flip view before the first page of the printed book (cover, title)
            return qsTr("Beginning")
        if (estimated)
            //: Estimated page of the printed book in the page flip view, e.g. "Page ≈ 143 / 380"
            return qsTr("Page ≈ %1 / %2").arg(stop.label).arg(total)
        if (stop.counted && total > 0)
            //: Page of the printed book in the page flip view, e.g. "Page 143 / 380"
            return qsTr("Page %1 / %2").arg(stop.label).arg(total)
        //: Page of the printed book without a total (Roman, or several volumes), e.g. "Page vii"
        return qsTr("Page %1").arg(stop.label)
    }

    function titleOf(i) {
        var stop = stops[i]
        if (!stop)
            return ""
        //: Chapter without a title in the contents, e.g. "Chapter 12"
        return stop.title || qsTr("Chapter %1").arg(stop.spine + 1)
    }

    // The range first, then the value: a value beyond the old range would
    // be clamped.
    function sync() {
        slider.maximumValue = Math.max(1, stops.length - 1)
        if (!slider.down)
            slider.value = Math.max(0, current)
    }

    onStopsChanged: sync()
    onCurrentChanged: sync()
    Component.onCompleted: sync()

    color: pageColor

    // Nothing reaches the text below.
    MouseArea {
        anchors.fill: parent
    }

    // The page and its chapter; beside the page "Go to page…" and close.
    Item {
        id: header

        width: parent.width
        height: titleLabel.y + titleLabel.height + Theme.paddingSmall

        Label {
            id: pageLabel

            x: Theme.horizontalPageMargin
            y: Theme.paddingSmall
            width: goButton.x - x - Theme.paddingMedium
            font.pixelSize: Theme.fontSizeLarge
            color: palette.highlightColor
            truncationMode: TruncationMode.Fade
            text: grid.stopText(grid.shown)
        }

        Button {
            id: goButton

            anchors {
                right: closeButton.left
                verticalCenter: closeButton.verticalCenter
            }
            preferredWidth: Theme.buttonWidthExtraSmall
            // In the ambience's colour, as the page beside it; its
            // background follows faintly.
            color: palette.highlightColor
            enabled: grid.stops.length > 0
            //: Opens a field to type a page of the printed book to go to
            text: qsTr("Go to page…")
            onClicked: grid.goToRequested()
        }

        MouseArea {
            id: closeButton

            anchors.right: parent.right
            y: Math.max(0, pageLabel.y + (pageLabel.height - height) / 2)
            width: Theme.itemSizeSmall
            height: Theme.itemSizeSmall
            onClicked: grid.closeRequested()

            BarIcon {
                anchors.centerIn: parent
                width: Theme.iconSizeSmall
                height: width
                name: "icon-m-clear"
                color: closeButton.pressed ? palette.highlightColor : palette.primaryColor
            }
        }

        Label {
            id: titleLabel

            y: Math.max(pageLabel.y + pageLabel.height, closeButton.y + closeButton.height)
            x: Theme.horizontalPageMargin
            width: parent.width - 2 * x
            font.pixelSize: Theme.fontSizeSmall
            color: palette.secondaryHighlightColor
            truncationMode: TruncationMode.Fade
            // Text from the book, never markup.
            textFormat: Text.PlainText
            text: grid.titleOf(grid.shown)
        }
    }

    // The pictures. A tap opens the page, a swipe goes one page on or back.
    Item {
        id: cells

        anchors {
            top: header.bottom
            bottom: footer.top
            left: parent.left
            right: parent.right
        }

        Grid {
            id: cellGrid

            anchors.centerIn: parent
            columns: 3
            spacing: grid.gap

            Repeater {
                model: 9

                Item {
                    readonly property var tile: grid.tiles[index] || null

                    width: grid.cellWidth
                    height: grid.cellHeight + grid.labelHeight

                    Rectangle {
                        width: grid.cellWidth
                        height: grid.cellHeight
                        visible: tile !== null
                        color: tile && tile.url ? "transparent" : grid.lineColor
                        opacity: tile && tile.url ? 1 : 0.25
                        border.width: index === 4 ? Math.max(2, Math.round(3 * Theme.pixelRatio))
                                                  : Math.max(1, Math.round(Theme.pixelRatio))
                        border.color: index === 4 ? palette.highlightColor : grid.lineColor
                    }

                    Image {
                        x: index === 4 ? Math.max(2, Math.round(3 * Theme.pixelRatio)) : 1
                        y: x
                        width: grid.cellWidth - 2 * x
                        height: grid.cellHeight - 2 * x
                        visible: tile !== null && tile.url !== ""
                        source: tile ? tile.url : ""
                        // Data addresses, new ones all the time: not kept.
                        cache: false
                        fillMode: Image.PreserveAspectFit
                        smooth: true
                    }

                    Label {
                        y: grid.cellHeight
                        width: grid.cellWidth
                        height: grid.labelHeight
                        verticalAlignment: Text.AlignVCenter
                        horizontalAlignment: Text.AlignHCenter
                        visible: tile !== null
                        font.pixelSize: Theme.fontSizeTiny
                        color: index === 4 ? palette.highlightColor : palette.secondaryColor
                        text: tile ? tile.label : ""
                    }
                }
            }
        }

        BusyIndicator {
            anchors.centerIn: cellGrid
            size: BusyIndicatorSize.Medium
            running: grid.busy
        }

        MouseArea {
            property real startX
            property real startY

            anchors.fill: parent
            onPressed: {
                startX = mouse.x
                startY = mouse.y
            }
            onReleased: {
                var dx = mouse.x - startX
                var dy = mouse.y - startY
                if (Math.abs(dx) > width / 8 && Math.abs(dx) > Math.abs(dy)) {
                    // As on the page: a swipe to the left goes on.
                    grid.swiped(dx < 0 ? 1 : -1)
                    return
                }
                if (Math.abs(dx) >= Theme.startDragDistance || Math.abs(dy) >= Theme.startDragDistance)
                    return
                var point = mapToItem(cellGrid, mouse.x, mouse.y)
                var column = Math.floor(point.x / (grid.cellWidth + grid.gap))
                var row = Math.floor(point.y / (grid.cellHeight + grid.labelHeight + grid.gap))
                if (column >= 0 && column < 3 && row >= 0 && row < 3)
                    grid.tileTapped(3 * row + column)
            }
        }
    }

    Column {
        id: footer

        anchors.bottom: parent.bottom
        width: parent.width

        Slider {
            id: slider

            width: parent.width
            // Silica leaves an eighth of the screen on each side: the whole
            // width, for finer steps through the book.
            leftMargin: Theme.horizontalPageMargin
            rightMargin: Theme.horizontalPageMargin
            minimumValue: 0
            stepSize: 1
            enabled: grid.stops.length > 1
            onSliderValueChanged: {
                if (down)
                    grid.dragged(Math.round(sliderValue))
            }
            onDownChanged: {
                if (!down)
                    grid.chosen(Math.round(value))
            }
        }

        Item {
            width: 1
            height: Theme.paddingSmall
        }
    }
}
