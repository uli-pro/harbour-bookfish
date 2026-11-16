import QtQuick 2.0
import Sailfish.Silica 1.0

// A setting with a few choices side by side, the one chosen framed and
// ticked: clearer than a switch, which leaves open what "off" means.
Item {
    id: choiceRow

    property alias label: labelText.text
    property var options: []
    // Optional: per choice {background, text}, shown in its own colours
    // (a sample); the one chosen is then marked by its frame alone.
    property var swatches: []
    // Optional: per choice the font family its name is written in.
    property var fonts: []
    property int currentIndex: 0
    // Choices per row; more wrap.
    property int columns: options.length
    // The last choice on a row of its own, for a long text.
    property bool wideLast: false
    // Below the choices, e.g. why they cannot be chosen now.
    property alias hint: hintText.text
    // Optional: a picture for each choice instead of its name, which then
    // shows below for the one chosen. The picture gets the properties
    // choice (index), chosen and highlighted.
    property Component picture: null

    signal chosen(int index)

    width: parent.width
    height: column.height + 2 * Theme.paddingMedium
    Column {
        id: column

        x: Theme.horizontalPageMargin
        y: Theme.paddingMedium
        width: parent.width - 2 * x
        spacing: Theme.paddingSmall

        Label {
            id: labelText

            width: parent.width
            truncationMode: TruncationMode.Fade
            // Not choosable now: dimmed, taps ignored; the hint is not.
            opacity: choiceRow.enabled ? 1 : Theme.opacityLow
        }

        Flow {
            id: row

            readonly property int columns: Math.max(1, choiceRow.columns)

            width: parent.width
            spacing: Theme.paddingMedium
            opacity: choiceRow.enabled ? 1 : Theme.opacityLow

            Repeater {
                model: choiceRow.options

                BackgroundItem {
                    id: option

                    readonly property bool current: index === choiceRow.currentIndex
                    readonly property var swatch: choiceRow.swatches.length > index ? choiceRow.swatches[index] : null

                    width: choiceRow.wideLast && index === choiceRow.options.length - 1
                           ? row.width : (row.width - (row.columns - 1) * row.spacing) / row.columns
                    height: choiceRow.picture ? Theme.itemSizeLarge : Theme.itemSizeSmall
                    onClicked: choiceRow.chosen(index)

                    // The frame of the one chosen, apart from it on the
                    // page's background: on a sample of nearly the same
                    // colour (white on Snow White, black on Inari Blue)
                    // it would hardly show.
                    Rectangle {
                        anchors.fill: parent
                        visible: option.current
                        radius: 2 * Theme.paddingSmall
                        color: "transparent"
                        border.width: Math.round(4 * Theme.pixelRatio)
                        border.color: Theme.highlightColor
                    }
                    Rectangle {
                        anchors.fill: parent
                        anchors.margins: Math.round(6 * Theme.pixelRatio)
                        radius: Theme.paddingSmall
                        color: option.swatch ? option.swatch.background
                                             : option.current ? Theme.rgba(Theme.highlightBackgroundColor,
                                                                           Theme.highlightBackgroundOpacity)
                                                              : "transparent"
                        // Pressed: the sample covers the highlight below.
                        opacity: option.swatch && option.highlighted ? 0.6 : 1
                        border.width: option.current ? 0 : Math.max(1, Math.round(Theme.pixelRatio))
                        border.color: Theme.rgba(Theme.primaryColor, Theme.opacityLow)
                    }
                    Loader {
                        id: pictureLoader

                        anchors.fill: parent
                        anchors.margins: Theme.paddingMedium
                        sourceComponent: choiceRow.picture

                        Binding {
                            target: pictureLoader.item
                            property: "choice"
                            value: index
                            when: pictureLoader.item !== null
                        }
                        Binding {
                            target: pictureLoader.item
                            property: "chosen"
                            value: option.current
                            when: pictureLoader.item !== null
                        }
                        Binding {
                            target: pictureLoader.item
                            property: "highlighted"
                            value: option.highlighted
                            when: pictureLoader.item !== null
                        }
                    }
                    Label {
                        visible: !choiceRow.picture
                        anchors.centerIn: parent
                        width: Math.min(implicitWidth, parent.width - 2 * Theme.paddingSmall)
                        truncationMode: TruncationMode.Fade
                        color: option.swatch ? option.swatch.text
                                             : option.current || option.highlighted ? Theme.highlightColor
                                                                                    : Theme.primaryColor
                        font.family: choiceRow.fonts.length > index ? choiceRow.fonts[index] : Theme.fontFamily
                        // The book's fonts look heavier than the theme's.
                        font.pixelSize: choiceRow.fonts.length > index ? Theme.fontSizeSmall : Theme.fontSizeMedium
                        // Marked also in words, whatever the colours.
                        text: (option.current ? "✓ " : "") + modelData
                    }
                }
            }
        }

        // With pictures: the name of the one chosen, marked in words too.
        Label {
            width: parent.width
            visible: choiceRow.picture !== null
            truncationMode: TruncationMode.Fade
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.highlightColor
            opacity: choiceRow.enabled ? 1 : Theme.opacityLow
            text: "✓ " + (choiceRow.options[choiceRow.currentIndex] || "")
        }

        Label {
            id: hintText

            width: parent.width
            visible: text !== ""
            wrapMode: Text.Wrap
            font.pixelSize: Theme.fontSizeExtraSmall
            color: Theme.secondaryColor
        }
    }
}
