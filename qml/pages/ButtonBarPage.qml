import QtQuick 2.0
import Sailfish.Silica 1.0
import "../components"

// The reading page's bar of buttons.
Page {
    id: page

    // Chosen here, stored when leaving.
    property bool atBottom: app.controlsAtBottom

    // Store once when leaving: the book is laid out again only then.
    onStatusChanged: {
        if (status === PageStatus.Deactivating) {
            app.setControlsScale(controlsSlider.value)
            // Unset, following the screen, until a choice differs.
            if (atBottom !== app.controlsAtBottom)
                app.setControls(atBottom ? "bottom" : "top")
        }
    }

    SilicaFlickable {
        anchors.fill: parent
        contentHeight: column.height

        Column {
            id: column
            width: parent.width

            PageHeader {
                //: Settings of the reading page's bar of buttons
                title: qsTr("Button bar")
            }

            Slider {
                id: controlsSlider
                width: parent.width
                minimumValue: app.minControlsScale
                maximumValue: app.maxControlsScale
                stepSize: 0.1
                value: app.controlsScale
                //: Size of the reading page's bar of buttons, with its value, e.g. "Button bar size 130 %"
                label: qsTr("Button bar size %1 %").arg(Math.round(value * 100))
            }

            ChoiceRow {
                //: Where the reading page shows its bar of buttons
                label: qsTr("Button bar position")
                //: Bar of buttons above the text, beside the notch if there is one
                options: [qsTr("Top"),
                          //: Bar of buttons below the text
                          qsTr("Bottom")]
                currentIndex: page.atBottom ? 1 : 0
                onChosen: page.atBottom = index === 1
            }
        }
    }
}
