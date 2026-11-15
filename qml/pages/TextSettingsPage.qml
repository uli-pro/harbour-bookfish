import QtQuick 2.0
import Sailfish.Silica 1.0
import "../components"

// The text of the reading page; the sample above shows it as set.
Page {
    id: page

    // Chosen here, stored when leaving.
    property bool serif: app.fontFamily === "serif"

    // Store once when leaving: the book is laid out again only then.
    onStatusChanged: {
        if (status === PageStatus.Deactivating) {
            app.setFontSize(fontSlider.value)
            app.setFontFamily(serif ? "serif" : "sans")
            app.setLineHeight(lineSlider.value)
            app.setParagraphSpacing(spacingSlider.value)
        }
    }

    SilicaFlickable {
        anchors.fill: parent
        contentHeight: column.height

        Column {
            id: column
            width: parent.width

            PageHeader {
                //: Settings of the text: font, size, spacing
                title: qsTr("Text")
            }

            // Two paragraphs as the book shows them: font, size, line and
            // paragraph spacing, or the indent that replaces the latter.
            // At most a third of the screen: at large sizes it would push
            // the sliders away, even from under the finger dragging them.
            Rectangle {
                width: parent.width
                height: Math.min(sample.height + 2 * Theme.paddingLarge, Math.round(page.height / 3))
                clip: true
                color: app.lightPage ? "white" : "black"

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
                            font.family: page.serif ? "serif" : "sans-serif"
                            font.pixelSize: sample.size
                            color: app.lightPage ? "black" : "white"
                            // An em space stands for the indent of 1em.
                            text: (sample.indent ? "\u2003" : "") + modelData
                        }
                    }
                }
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

            ChoiceRow {
                label: qsTr("Font")
                // Each name in its font.
                options: [qsTr("Sans serif"), qsTr("Serif")]
                fonts: ["sans-serif", "serif"]
                currentIndex: page.serif ? 1 : 0
                onChosen: page.serif = index === 1
            }

            Item {
                width: parent.width
                height: Theme.paddingLarge
            }
        }
    }
}
