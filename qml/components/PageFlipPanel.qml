import QtQuick 2.0
import Sailfish.Silica 1.0

// The page flip view of the reading page (lernen/32): a bar over the whole
// book below the text. Dragging shows where it leads; letting go goes
// there, and the page behind is the preview. It never changes the text's
// area, so the chapter is not laid out again.
Rectangle {
    id: panel

    // The bar's stops (see bridge.flip_stops), empty until they are read;
    // the one of the page shown; whether the pages are estimated, and the
    // highest page (0: none).
    property var stops: []
    property int current: -1
    property bool estimated: false
    property int total: 0
    // The page in the corner, shown until the stops are read.
    property string currentText
    // "Back to page 120"; "" hides the button.
    property string backText
    property color pageColor
    property color lineColor
    // The stop let go at, shown until the page behind has gone there.
    property int pending: -1
    readonly property int shown: slider.down ? Math.round(slider.sliderValue)
                                             : pending >= 0 ? pending : current

    signal chosen(int index)
    signal backRequested()
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
    onCurrentChanged: {
        pending = -1
        sync()
    }
    Component.onCompleted: sync()

    height: column.height + 2 * Theme.paddingMedium
    color: pageColor

    // Taps beside the controls must not reach the text below.
    MouseArea {
        anchors.fill: parent
    }

    Rectangle {
        width: parent.width
        height: Math.max(1, Math.round(Theme.pixelRatio))
        color: panel.lineColor
    }

    // Should the page not report a new place (a jump to where it is).
    Timer {
        id: pendingTimer
        interval: 3000
        onTriggered: {
            panel.pending = -1
            panel.sync()
        }
    }

    Column {
        id: column

        y: Theme.paddingMedium
        width: parent.width

        Item {
            width: parent.width
            height: Math.max(pageLabel.height + titleLabel.height, closeButton.height)

            Label {
                id: pageLabel

                x: Theme.horizontalPageMargin
                width: closeButton.x - x
                font.pixelSize: Theme.fontSizeLarge
                color: palette.highlightColor
                truncationMode: TruncationMode.Fade
                text: panel.stopText(panel.shown)
            }

            Label {
                id: titleLabel

                anchors.top: pageLabel.bottom
                x: Theme.horizontalPageMargin
                width: closeButton.x - x
                font.pixelSize: Theme.fontSizeSmall
                color: palette.secondaryHighlightColor
                truncationMode: TruncationMode.Fade
                // Text from the book, never markup.
                textFormat: Text.PlainText
                text: panel.titleOf(panel.shown)
            }

            MouseArea {
                id: closeButton

                anchors.right: parent.right
                width: Theme.itemSizeSmall + Theme.horizontalPageMargin
                height: Theme.itemSizeSmall
                onClicked: panel.closeRequested()

                BarIcon {
                    anchors.centerIn: parent
                    anchors.horizontalCenterOffset: -Theme.horizontalPageMargin / 2
                    width: Theme.iconSizeSmall
                    height: width
                    name: "icon-m-clear"
                    color: closeButton.pressed ? palette.highlightColor : palette.primaryColor
                }
            }
        }

        Slider {
            id: slider

            width: parent.width
            minimumValue: 0
            stepSize: 1
            enabled: panel.stops.length > 1
            onDownChanged: {
                if (down)
                    return
                var i = Math.round(value)
                if (i === panel.current || i >= panel.stops.length) {
                    panel.sync()
                    return
                }
                panel.pending = i
                pendingTimer.restart()
                panel.chosen(i)
            }
        }

        Row {
            x: Theme.horizontalPageMargin
            spacing: Theme.paddingMedium

            Button {
                visible: panel.backText !== ""
                preferredWidth: Theme.buttonWidthExtraSmall
                text: panel.backText
                onClicked: panel.backRequested()
            }
            Button {
                preferredWidth: Theme.buttonWidthExtraSmall
                enabled: panel.stops.length > 0
                //: Opens a field to type a page of the printed book to go to
                text: qsTr("Go to page…")
                onClicked: panel.goToRequested()
            }
        }
    }
}
