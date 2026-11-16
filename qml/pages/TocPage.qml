import QtQuick 2.0
import Sailfish.Silica 1.0

Page {
    id: page

    // [{title, level, spine, fragment}]; in an audiobook also start, the
    // time in the book in ms, shown beside the title.
    property var toc: []
    property int currentChapter: -1
    // The unpacked book: its printed pages are shown beside the titles
    // (bridge.page_labels). "" for an audiobook.
    property string bookRoot
    property var pageLabels: []
    property bool pagesEstimated: false
    property int pagesSerial: -1

    Component.onCompleted: {
        if (bookRoot === "")
            return
        pagesSerial = ++app.searchSerial
        py.call("bookfish.bridge.page_labels", [bookRoot, toc.map(function (entry) {
            return { spine: entry.spine, fragment: entry.fragment || "" }
        }), pagesSerial])
    }

    Connections {
        target: app
        onPagesFound: {
            if (serial !== page.pagesSerial)
                return
            if (result.error) {
                console.warn("Cannot read the pages", result.error, result.detail)
                return
            }
            page.pagesEstimated = result.estimated
            page.pageLabels = result.labels
        }
    }

    signal selected(int chapter, string fragment)

    // "1:02:03", or "2:03" below an hour.
    function clock(ms) {
        var s = Math.floor(ms / 1000)
        var h = Math.floor(s / 3600)
        var m = Math.floor(s / 60) % 60
        s = s % 60
        return (h > 0 ? h + ":" + (m < 10 ? "0" : "") : "") + m + ":" + (s < 10 ? "0" : "") + s
    }

    SilicaListView {
        id: listView

        anchors.fill: parent
        model: toc

        // The current chapter in the middle; an audiobook may have hundreds.
        Component.onCompleted: {
            for (var i = 0; i < toc.length; ++i) {
                if (toc[i].spine === page.currentChapter) {
                    positionViewAtIndex(i, ListView.Center)
                    break
                }
            }
        }

        header: PageHeader {
            title: qsTr("Contents")
        }

        delegate: ListItem {
            // Headings without a link, or links to files outside the
            // reading order, cannot be opened.
            enabled: modelData.spine >= 0

            Label {
                x: Theme.horizontalPageMargin + Math.min(modelData.level, 4) * Theme.paddingLarge
                width: parent.width - x - Theme.horizontalPageMargin
                       - (timeLabel.visible ? timeLabel.width + Theme.paddingMedium : 0)
                anchors.verticalCenter: parent.verticalCenter
                text: modelData.title
                // Text from the book, never markup.
                textFormat: Text.PlainText
                truncationMode: TruncationMode.Fade
                color: !parent.enabled ? Theme.secondaryColor
                     : (highlighted || modelData.spine === page.currentChapter)
                       ? Theme.highlightColor : Theme.primaryColor
            }

            Label {
                id: timeLabel

                readonly property string pageText: page.pageLabels[index] || ""

                visible: modelData.start !== undefined || pageText !== ""
                anchors {
                    right: parent.right
                    rightMargin: Theme.horizontalPageMargin
                    verticalCenter: parent.verticalCenter
                }
                text: modelData.start !== undefined ? page.clock(modelData.start)
                      : pageText === "" ? ""
                      : page.pagesEstimated
                        //: Estimated page of the printed book beside an entry of the contents, e.g. "≈143"
                        ? qsTr("≈%1").arg(pageText) : pageText
                font.pixelSize: Theme.fontSizeSmall
                color: highlighted ? Theme.secondaryHighlightColor : Theme.secondaryColor
            }

            onClicked: {
                page.selected(modelData.spine, modelData.fragment)
                pageStack.pop()
            }
        }

        ViewPlaceholder {
            enabled: listView.count === 0
            text: qsTr("No table of contents")
        }

        VerticalScrollDecorator { }
    }
}
