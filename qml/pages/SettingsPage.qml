import QtQuick 2.0
import Sailfish.Silica 1.0

Page {
    // Until chosen the reading page follows the ambience.
    readonly property bool lightPage: app.pageColors === "light"
                                      || (app.pageColors === "" && Theme.colorScheme === Theme.DarkOnLight)

    // Store once when leaving: the book is laid out again, or the audio file
    // reloaded, only then.
    onStatusChanged: {
        if (status === PageStatus.Deactivating) {
            app.setFontSize(fontSlider.value)
            app.setPlaybackRate(rateSlider.value)
            app.setFontFamily(fontBox.currentIndex === 1 ? "serif" : "sans")
            app.setLineHeight(lineSlider.value)
            app.setParagraphSpacing(spacingSlider.value)
            // Kept unset, following the ambience, until a choice differs.
            if ((pageBox.currentIndex === 0) !== lightPage)
                app.setPageColors(pageBox.currentIndex === 0 ? "light" : "dark")
            // Likewise unset, following the screen, until a choice differs.
            if ((controlsBox.currentIndex === 1) !== app.controlsAtBottom)
                app.setControls(controlsBox.currentIndex === 1 ? "bottom" : "top")
        }
    }

    SilicaFlickable {
        anchors.fill: parent
        contentHeight: column.height

        Column {
            id: column
            width: parent.width

            PageHeader {
                title: qsTr("Settings")
            }

            Slider {
                id: rateSlider
                width: parent.width
                minimumValue: app.minPlaybackRate
                maximumValue: app.maxPlaybackRate
                stepSize: 0.05
                value: app.playbackRate
                // The value in the label below, not in the large figure
                // above the slider, which takes much room (as below).
                //: Playback speed with its value, e.g. "Speed 1.25×"
                label: qsTr("Speed %1×").arg(value.toLocaleString(Qt.locale(), "f", 2))
            }

            Slider {
                id: fontSlider
                width: parent.width
                minimumValue: app.minFontSize
                maximumValue: app.maxFontSize
                stepSize: 2
                value: app.fontSize
                //: Text size in pixels on the screen, with its value, e.g. "Text size 36"
                label: qsTr("Text size %1").arg(value)
            }

            Slider {
                id: lineSlider
                width: parent.width
                minimumValue: app.minLineHeight
                maximumValue: app.maxLineHeight
                stepSize: 0.05
                value: app.lineHeight
                //: Line spacing with its value, e.g. "Line spacing 1.30"
                label: qsTr("Line spacing %1").arg(value.toLocaleString(Qt.locale(), "f", 2))
            }

            Slider {
                id: spacingSlider
                width: parent.width
                minimumValue: app.minParagraphSpacing
                maximumValue: app.maxParagraphSpacing
                stepSize: 0.1
                value: app.paragraphSpacing
                label: value > 0
                       //: Space between paragraphs, counted in lines of text, with its value, e.g. "Paragraph spacing 0.5 lines"
                       ? qsTr("Paragraph spacing %1 lines").arg(value.toLocaleString(Qt.locale(), "f", 1))
                       //: No space between paragraphs: the first lines are indented instead
                       : qsTr("Paragraph spacing: indent")
            }

            ComboBox {
                id: fontBox
                width: parent.width
                label: qsTr("Font")
                currentIndex: app.fontFamily === "serif" ? 1 : 0
                menu: ContextMenu {
                    MenuItem { text: qsTr("Sans serif") }
                    MenuItem { text: qsTr("Serif") }
                }
            }

            ComboBox {
                id: controlsBox
                width: parent.width
                //: Where the reading page shows its buttons
                label: qsTr("Controls")
                currentIndex: app.controlsAtBottom ? 1 : 0
                menu: ContextMenu {
                    //: Buttons above the text, beside the notch if there is one
                    MenuItem { text: qsTr("Top") }
                    //: Buttons below the text
                    MenuItem { text: qsTr("Bottom") }
                }
            }

            ComboBox {
                id: pageBox
                width: parent.width
                //: Colours of the reading page
                label: qsTr("Page")
                currentIndex: lightPage ? 0 : 1
                menu: ContextMenu {
                    //: Black text on white
                    MenuItem { text: qsTr("Light") }
                    //: White text on black
                    MenuItem { text: qsTr("Dark") }
                }
            }

            // Two paragraphs as the book shows them: font, size, line and
            // paragraph spacing, or the indent that replaces the latter.
            Rectangle {
                width: parent.width
                height: sample.height + 2 * Theme.paddingLarge
                color: pageBox.currentIndex === 0 ? "white" : "black"

                Column {
                    id: sample

                    // As large as the reader sees it in the book.
                    readonly property real size: fontSlider.value * app.textScale
                    readonly property bool indent: spacingSlider.value === 0

                    x: Theme.horizontalPageMargin
                    y: Theme.paddingLarge
                    width: parent.width - 2 * x
                    spacing: spacingSlider.value * lineSlider.value * size

                    Repeater {
                        model: [
                            //: Sample text showing the chosen text settings, first paragraph
                            qsTr("High above the city, on a tall column, stood the statue of the Happy Prince."),
                            //: Sample text showing the chosen text settings, second paragraph
                            qsTr("He was gilded all over with thin leaves of fine gold, for eyes he had two bright sapphires, and a large red ruby glowed on his sword-hilt.")
                        ]

                        Label {
                            width: sample.width
                            wrapMode: Text.Wrap
                            // CSS counts line height in font sizes, Qt's proportional
                            // mode in the font's own (larger) line height.
                            lineHeightMode: Text.FixedHeight
                            lineHeight: lineSlider.value * sample.size
                            font.family: fontBox.currentIndex === 1 ? "serif" : "sans-serif"
                            font.pixelSize: sample.size
                            color: pageBox.currentIndex === 0 ? "black" : "white"
                            // An em space stands for the indent of 1em.
                            text: (sample.indent ? "\u2003" : "") + modelData
                        }
                    }
                }
            }
        }
    }
}
