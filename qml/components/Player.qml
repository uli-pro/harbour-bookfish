import QtQuick 2.0
import QtMultimedia 5.6

// Plays the clips of one chapter, one sentence after the other, and tells
// which sentence is spoken. The page hands over the next chapter when this
// one is finished.
//
// The audio file runs on from clip to clip; it is only sought when a clip
// does not follow the previous one. A timer is set to the end of the clip
// instead of polling the position.
//
// Sailfish may pause the audio itself: headphones out of reach, an alarm,
// a call (seen on the device). That counts as a pause, so the place is
// saved and nothing plays on unasked; only after an alarm or a call, when
// Sailfish plays on by itself, listening goes on.
Item {
    id: player

    // Folder of the unpacked book; clips name their audio file within it.
    property string root
    property real rate: 1.0
    property int chapter: -1
    // [{id, audio, begin, end}], times in ms, end null = to the end of the file
    property var clips: []
    property int index: -1
    // Times within the current clip at which marked(n) is sent, ascending.
    property var marks: []
    // What the user asked for; the audio itself stops briefly whenever a
    // file is loaded.
    property bool playing: false
    readonly property bool active: index >= 0
    // Guarded: clips and index change one after the other.
    readonly property string currentId: index >= 0 && index < clips.length ? clips[index].id : ""
    // For the sleep timer: fading out, and pausing once the chapter is
    // over, with the next one loaded.
    property real volume: 1
    property bool holdAtChapterEnd: false
    // Why playing last became false: "pause", "interrupted", "error", or
    // "held" at the end of a chapter.
    property string why: "pause"
    // Paused or stopped by Sailfish, not by us, and not taken up since;
    // busy: meanwhile the audio was taken by an alarm or a call.
    property bool interrupted: false
    property bool busy: false

    signal sentence(int chapter, int index)
    signal finished(int chapter)
    signal marked(int n)
    signal failed()
    // Paused at the end of a chapter, see holdAtChapterEnd.
    signal held()

    // ms, as GStreamer reports it for the file loaded; not above 0 while
    // not known.
    readonly property int fileDuration: audio.duration
    property string loadedPath: ""
    property int pendingSeek: -1
    property int nextMark: 0
    property real loadedRate: 1.0
    // The chapter is finished and the page has not yet handed over the next.
    property bool waiting: false
    // Set by next() at the end of a chapter: the rest of the clip is not
    // played, so the next chapter is sought even if it follows on.
    property bool skipping: false
    // A file is being loaded; the stop that comes with it is ours.
    property bool loading: false
    // The file loading has reported a status of its own; a stop before
    // that still belongs to the previous file.
    property bool loadSeen: false
    property bool stoppedOutside: false
    // Watchdog: the last position seen while playing, and for how many
    // seconds it has not moved.
    property int watchedPosition: -1
    property int stillSeconds: 0
    property int restarts: 0
    property int restartedAt: -1

    // In ms within the audio file, also while a seek waits for the file;
    // read when needed, the property binding of Audio is only updated once
    // a second.
    function currentPosition() {
        return pendingSeek >= 0 ? pendingSeek : audio.position
    }

    function fileUrl(path) {
        return "file://" + (root + "/" + path).split("/").map(encodeURIComponent).join("/")
    }

    // Seeks are dropped until the file reports seekable, and a playback rate
    // only takes effect when a file is loaded (measured on the device).
    function load(path, ms, reload) {
        // A rate changed while paused is taken up with the next load.
        reload = reload || loadedRate !== rate
        if (path === loadedPath && !reload && pendingSeek < 0 && audio.seekable) {
            audio.seek(ms)
        } else {
            pendingSeek = ms
            if (path !== loadedPath || reload) {
                loading = true
                loadSeen = false
                if (path === loadedPath) {
                    // The same file again (a new rate, the watchdog): only
                    // an empty source makes Qt load it afresh. This gives up
                    // the grant as below; it is rare, and the sound plays.
                    audio.source = ""
                    audio.playbackRate = rate
                    audio.source = fileUrl(path)
                } else {
                    // No empty source in between: that gives up Sailfish's
                    // audio grant, and the new one may get lost (Qt source),
                    // which leaves the player reporting Stalled or silent.
                    audio.source = fileUrl(path)
                    audio.playbackRate = rate
                }
                loadedPath = path
                loadedRate = rate
            }
        }
        if (playing)
            audio.play()
    }

    // paused: only to the place, playing on with resume().
    function start(chapterIndex, list, i, offset, paused) {
        chapter = chapterIndex
        clips = list
        // Before playing: the page notes where listening starts.
        index = i
        if (!paused)
            playing = true
        jump(i, offset || 0)
    }

    // Goes on with the next chapter where the last clip ended.
    function continueWith(chapterIndex, list) {
        var last = clips[clips.length - 1]
        var seek = skipping || !follows(last, list[0])
        waiting = false
        skipping = false
        chapter = chapterIndex
        clips = list
        index = 0
        resetMarks()
        if (holdAtChapterEnd) {
            // After the new chapter is set, so its first sentence is the
            // place saved; before loading, which would play.
            holdAtChapterEnd = false
            if (playing) {
                why = "held"
                alarm.stop()
                // First: the pause is reported at once, and must not look
                // like one by Sailfish.
                playing = false
                audio.pause()
            }
            // Also if interrupted meanwhile: not on by itself after.
            busy = false
            held()
        }
        if (seek)
            load(list[0].audio, list[0].begin)
        sentence(chapter, 0)
        arm()
    }

    function jump(i, offset, reload) {
        taken()
        waiting = false
        skipping = false
        index = i
        resetMarks()
        load(clips[i].audio, clips[i].begin + (offset || 0), reload)
        sentence(chapter, index)
        arm()
    }

    function pause() {
        taken()
        why = "pause"
        playing = false
        alarm.stop()
        audio.pause()
    }

    function resume() {
        if (index < 0)
            return
        if (stoppedOutside) {
            // Nothing is left of the file; the sentence from its start.
            playing = true
            jump(index, 0, true)
            return
        }
        taken()
        playing = true
        if (loadedRate !== rate)
            load(loadedPath, pendingSeek >= 0 ? pendingSeek : audio.position, true)
        audio.play()
        arm()
    }

    function stop() {
        taken()
        why = "pause"
        playing = false
        alarm.stop()
        audio.stop()
        // After a stop or an error the file is loaded afresh.
        loadedPath = ""
        index = -1
        clips = []
        chapter = -1
        pendingSeek = -1
        waiting = false
        skipping = false
        resetMarks()
    }

    // Back to the start of the sentence, or to the previous one right after
    // a sentence began, as in music players. Not across chapters.
    function previous() {
        if (index < 0)
            return
        var position = pendingSeek >= 0 ? pendingSeek : audio.position
        var early = position - clips[index].begin < 1500 * rate
        jump(early && index > 0 ? index - 1 : index)
    }

    function next() {
        if (index < 0)
            return
        if (index + 1 < clips.length) {
            jump(index + 1)
        } else if (!waiting) {
            alarm.stop()
            skipping = true
            waiting = true
            finished(chapter)
        }
    }

    function setMarks(list) {
        marks = list
        nextMark = 0
        arm()
    }

    function resetMarks() {
        marks = []
        nextMark = 0
    }

    // Storyteller leaves no gaps; small ones of other tools are played,
    // larger ones hold audio without text and are skipped.
    function follows(a, b) {
        return a.audio === b.audio && hasEnd(a)
                && b.begin >= a.end && b.begin - a.end <= 500
    }

    // Python's None may arrive as null or as undefined.
    function hasEnd(clip) {
        return typeof clip.end === "number"
    }

    function arm() {
        alarm.stop()
        if (!playing || index < 0 || pendingSeek >= 0 || waiting)
            return
        var target = nextMark < marks.length ? marks[nextMark]
                                             : hasEnd(clips[index]) ? clips[index].end : -1
        if (target < 0)
            return  // the end of the file ends the clip
        // At most a second: right after a seek the position may still be
        // the old one; check() sets the alarm again if it rings early.
        alarm.interval = Math.max(10, Math.min(1000, (target - audio.position) / audio.playbackRate))
        alarm.start()
    }

    function check() {
        var pos = audio.position
        if (nextMark < marks.length) {
            if (pos >= marks[nextMark] - 15)
                marked(nextMark++)
            arm()
        } else if (hasEnd(clips[index]) && pos >= clips[index].end - 15) {
            advance()
        } else {
            arm()
        }
    }

    function advance() {
        if (waiting)
            return  // also the end of the file may still report
        if (index + 1 >= clips.length) {
            alarm.stop()
            waiting = true
            finished(chapter)
            return
        }
        var previousClip = clips[index]
        index++
        resetMarks()
        if (!follows(previousClip, clips[index]))
            load(clips[index].audio, clips[index].begin)
        sentence(chapter, index)
        arm()
    }

    // A file loaded at the end of the previous one reports the stop of that
    // one only after play() was called, which drops the call (seen on the
    // device). Which of the two signals comes last may vary. Only while
    // loading: a file stopped by Sailfish must not start again.
    function retryPlay() {
        if (playing && loading && loadSeen && !waiting && audio.playbackState === Audio.StoppedState
                && readable(audio.status)) {
            console.log("Narration restarted after loading, status", audio.status)
            audio.play()
        }
    }

    // Stalled: playing without Sailfish's audio grant (Qt source).
    function readable(status) {
        return status === Audio.Loaded || status === Audio.Stalled
                || status === Audio.Buffering || status === Audio.Buffered
    }

    // The user (or the page) acts: an interruption is over.
    function taken() {
        restarts = 0
        restartedAt = -1
        interrupted = false
        busy = false
        stoppedOutside = false
        stopCheck.stop()
        busyWindow.stop()
    }

    function interrupt(stopped) {
        console.log("Narration", stopped ? "stopped" : "paused", "by the system, audio", audio.availability)
        why = "interrupted"
        interrupted = true
        stoppedOutside = stopped
        busy = audio.availability === Audio.Busy
        // An alarm or a call reports the audio busy right after pausing it
        // (seen on the device); later it would be another cause.
        busyWindow.restart()
        alarm.stop()
        playing = false
    }

    // Sound without being asked: after an alarm or a call Sailfish plays on
    // by itself, and so does listening. Anything else is paused again; it
    // could be the loudspeaker in a pocket.
    function playingByItself() {
        console.log("Narration played on by the system,", interrupted && busy ? "accepted" : "paused again")
        if (interrupted && busy) {
            taken()
            playing = true
            arm()
        } else {
            audio.pause()
        }
    }

    // The time left in the chapter in ms at the current rate, or -1 if a
    // clip has no end.
    function chapterLeft() {
        if (index < 0)
            return -1
        var position = pendingSeek >= 0 ? pendingSeek : audio.position
        var left = 0
        for (var i = index; i < clips.length; ++i) {
            if (!hasEnd(clips[i]))
                return -1
            left += i === index ? Math.max(0, clips[i].end - position) : clips[i].end - clips[i].begin
        }
        return left / rate
    }

    // While paused the new rate is taken up by resume().
    onRateChanged: {
        if (playing && index >= 0)
            load(loadedPath, pendingSeek >= 0 ? pendingSeek : audio.position, true)
    }

    Audio {
        id: audio

        volume: player.volume

        onSeekableChanged: {
            if (seekable && player.pendingSeek >= 0) {
                seek(player.pendingSeek)
                player.pendingSeek = -1
                player.arm()
            }
        }
        onStatusChanged: {
            if (player.loading)
                player.loadSeen = true
            if (status === Audio.EndOfMedia && player.playing && player.index >= 0
                    && player.pendingSeek < 0) {
                player.advance()
            } else {
                player.retryPlay()
            }
        }
        onPlaybackStateChanged: {
            switch (playbackState) {
            case Audio.PlayingState:
                if (player.loading)
                    settle.restart()
                if (!player.playing)
                    player.playingByItself()
                break
            case Audio.PausedState:
                // Our own pause clears playing first.
                if (player.playing)
                    player.interrupt(false)
                break
            default:
                // At the end of a file the stop may come before the status
                // EndOfMedia; that one moves on to the next clip or chapter.
                if (player.playing && !player.loading && !player.waiting) {
                    stopCheck.restart()
                } else {
                    player.retryPlay()
                    // In case no further signal comes to start it.
                    if (player.loading)
                        loadWatch.restart()
                }
            }
        }
        onAvailabilityChanged: {
            console.log("Audio availability", availability, "interrupted", player.interrupted)
            if (availability === Audio.Busy && player.interrupted && busyWindow.running)
                player.busy = true
        }
        onError: {
            console.warn("Audio error", error, errorString, source)
            player.why = "error"
            alarm.stop()
            // The page saves the sentence now, while index still holds it.
            player.playing = false
            player.failed()
            player.stop()
        }
    }

    Timer {
        id: busyWindow
        interval: 500
    }

    // The stop of the previous file may come after the new one plays (see
    // retryPlay), so loading is over once playing has lasted a while.
    Timer {
        id: settle
        interval: 1500
        onTriggered: {
            if (audio.playbackState === Audio.PlayingState)
                player.loading = false
        }
    }

    // Whatever the cause, the narration must not stand silent while it is
    // meant to play: if the position has not moved for three seconds, the
    // file is loaded afresh at that place, at most twice in a row.
    Timer {
        interval: 1000
        repeat: true
        running: player.playing && player.index >= 0 && !player.waiting
        onRunningChanged: {
            player.watchedPosition = -1
            player.stillSeconds = 0
            player.restarts = 0
            player.restartedAt = -1
        }
        onTriggered: {
            // Also a seek that never happens counts as standing still.
            var position = player.currentPosition()
            if (position !== player.watchedPosition) {
                // Moving again, and not just for a moment after a reload.
                if (position - player.restartedAt > 2000)
                    player.restarts = 0
                player.watchedPosition = position
                player.stillSeconds = 0
                return
            }
            // A load from a slow memory card gets more time.
            if (++player.stillSeconds < (player.pendingSeek >= 0 ? 10 : 3) || player.restarts > 2)
                return
            player.stillSeconds = 0
            if (player.restarts++ === 2) {
                console.warn("Narration stands still at", position, "in", player.loadedPath)
                return
            }
            console.log("Narration stood still at", position, "status", audio.status,
                        "state", audio.playbackState, "- loading afresh")
            player.restartedAt = position
            player.load(player.loadedPath, position, true)
        }
    }

    Timer {
        id: loadWatch
        interval: 1500
        onTriggered: player.retryPlay()
    }

    Timer {
        id: stopCheck
        interval: 500
        onTriggered: {
            if (player.playing && !player.loading && !player.waiting
                    && audio.playbackState === Audio.StoppedState && audio.status !== Audio.EndOfMedia)
                player.interrupt(true)
        }
    }

    Timer {
        id: alarm
        onTriggered: player.check()
    }
}
