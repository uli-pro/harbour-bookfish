import QtQuick 2.0
import Sailfish.Silica 1.0
import "../components"

// Playback speed and sleep timer: the speed and timer buttons open this
// page, and so do the settings, so it is always the same place. The timer
// only works while a book is being listened to; otherwise it is dimmed.
Page {
    id: page

    // The reading or audiobook page that plays, with its timer.
    readonly property var reader: app.reader
    readonly property bool timerOn: !!reader && reader.timerAvailable
    readonly property var timer: timerOn ? reader.playbackTimer : null
    // Minutes left in the chapter at the speed set here, -1 if not known.
    // Kept apart from the time, which changes all along: the choices are
    // built again only when the minutes change.
    property int chapterMinutes: -1

    function updateChapterMinutes() {
        var left = timerOn ? reader.chapterTimeLeft() : -1
        // chapterTimeLeft() counts at the speed in use, not the one on
        // the slider, which takes effect when leaving.
        var minutes = left > 0 ? Math.max(1, Math.ceil(left * app.playbackRate / rateSlider.value / 60000)) : -1
        if (minutes !== chapterMinutes)
            chapterMinutes = minutes
    }

    // 0 = off, -1 = end of chapter
    readonly property var choices: [0, 15, 30, 45, 60, 90, -1]

    function chosenIndex() {
        if (!timer || timer.mode === "off")
            return 0
        if (timer.mode === "chapter")
            return choices.length - 1
        return choices.indexOf(timer.minutes)
    }

    function label(choice) {
        if (choice === 0)
            //: Sleep timer turned off
            return qsTr("Off")
        if (choice > 0)
            //: Sleep timer, e.g. "15 min"
            return qsTr("%1 min").arg(choice)
        if (chapterMinutes < 0)
            //: Sleep timer ends listening when the chapter is over
            return qsTr("End of chapter")
        //: Sleep timer at the end of the chapter, with the minutes left, e.g. "End of chapter (3 min)"
        return qsTr("End of chapter (%1 min)").arg(chapterMinutes)
    }

    Component.onCompleted: updateChapterMinutes()

    Timer {
        interval: 1000
        repeat: true
        running: page.status === PageStatus.Active
        onTriggered: page.updateChapterMinutes()
    }

    // Store once when leaving: the audio file is reloaded only then.
    onStatusChanged: {
        if (status === PageStatus.Deactivating)
            app.setPlaybackRate(rateSlider.value)
    }

    SilicaFlickable {
        anchors.fill: parent
        contentHeight: column.height

        Column {
            id: column
            width: parent.width

            PageHeader {
                //: Title of the page for the playback speed and the sleep timer
                title: qsTr("Playback and timer")
            }

            Slider {
                id: rateSlider
                width: parent.width
                minimumValue: app.minPlaybackRate
                maximumValue: app.maxPlaybackRate
                stepSize: 0.05
                value: app.playbackRate
                // The value in the label below, not in the large figure
                // above the slider, which takes much room.
                //: Playback speed with its value, e.g. "Playback speed 1.25×"
                label: qsTr("Playback speed %1×").arg(value.toLocaleString(Qt.locale(), "f", 2))
            }

            ChoiceRow {
                enabled: page.timerOn
                columns: 3
                // "End of chapter (12 min)" needs a whole row.
                wideLast: true
                label: page.timer && page.timer.mode === "minutes"
                       //: Title of the sleep timer while it runs, with the time left, e.g. "Sleep timer · 23 min left"
                       ? qsTr("Sleep timer · %1 min left").arg(Math.ceil(page.timer.remaining / 60000))
                       //: Title of the choices when listening ends
                       : qsTr("Sleep timer")
                options: page.choices.map(function (choice) { return page.label(choice) })
                currentIndex: page.chosenIndex()
                //: Why the sleep timer is dimmed
                hint: page.timerOn ? "" : qsTr("Only while a book is playing")
                onChosen: {
                    var choice = page.choices[index]
                    if (choice === 0)
                        page.timer.cancel()
                    else if (choice > 0)
                        page.timer.setMinutes(choice)
                    else
                        page.timer.setChapterEnd()
                }
            }
        }

        VerticalScrollDecorator { }
    }
}
