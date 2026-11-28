import QtQuick 2.0
import Sailfish.Silica 1.0
import "../components"

// The text of the reading page; the sample above shows it as set. In
// landscape with two columns it stands beside the rest, as wide as a
// column of the book.
Page {
    id: page

    // Chosen here, stored when leaving.
    property bool serif: app.fontFamily === "serif"
    property bool justify: app.textAlign === "justify"
    property int columns: app.landscapeColumns
    readonly property bool sampleBeside: isLandscape && columns > 1

    // Store once when leaving: the book is laid out again only then.
    onStatusChanged: {
        if (status === PageStatus.Deactivating) {
            app.setFontSize(fontSlider.value)
            app.setFontFamily(serif ? "serif" : "sans")
            app.setTextAlign(justify ? "justify" : "left")
            app.setLineHeight(lineSlider.value)
            app.setParagraphSpacing(spacingSlider.value)
            app.setLandscapeColumns(columns)
        }
    }

    Loader {
        width: page.width / 2
        height: page.height
        active: page.sampleBeside
        sourceComponent: sampleComponent
    }

    SilicaFlickable {
        x: page.sampleBeside ? page.width / 2 : 0
        width: page.width - x
        height: page.height
        contentHeight: column.height

        Column {
            id: column
            width: parent.width

            PageHeader {
                //: Settings of the text: font, size, spacing
                title: qsTr("Text")
            }

            // At most a third of the screen: at large sizes it would push
            // the sliders away, even from under the finger dragging them.
            Loader {
                width: parent.width
                height: item ? Math.min(item.sampleHeight, Math.round(page.height / 3)) : 0
                active: !page.sampleBeside
                sourceComponent: sampleComponent
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

            ChoiceRow {
                //: How the lines of a paragraph end: ragged, or justified to both margins
                label: qsTr("Text alignment")
                //: Lines aligned to the left margin only, ending raggedly
                options: [qsTr("Left"),
                          //: Lines stretched to both margins, words hyphenated
                          qsTr("Justified")]
                picture: Component { AlignmentPicture { } }
                currentIndex: page.justify ? 1 : 0
                onChosen: page.justify = index === 1
            }

            ChoiceRow {
                //: How many columns of text the reading page has in landscape
                label: qsTr("Columns in landscape")
                //: One column of text in landscape
                options: [qsTr("One"),
                          //: Two columns of text in landscape
                          qsTr("Two")]
                picture: Component { ColumnsPicture { } }
                currentIndex: page.columns - 1
                onChosen: page.columns = index + 1
            }

            Item {
                width: parent.width
                height: Theme.paddingLarge
            }
        }
    }

    Component {
        id: sampleComponent

        // Two paragraphs as the book shows them: font, size, line and
        // paragraph spacing, or the indent that replaces the latter, and the
        // alignment (without the book's hyphenation).
        Rectangle {
            readonly property real sampleHeight: sample.height + 2 * Theme.paddingLarge

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
                        horizontalAlignment: page.justify ? Text.AlignJustify : Text.AlignLeft
                        color: app.lightPage ? "black" : "white"
                        // An em space stands for the indent of 1em.
                        text: (sample.indent ? "\u2003" : "") + modelData
                    }
                }
            }
        }
    }
}
