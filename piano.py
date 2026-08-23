# -*- coding: utf-8 -*-
import core
import time
from pyaudiogaming.sound_pool import musical, mixer
import setting
import recorder

MIDI_EVENT_NOTE = 1

# Ergonomic two-hand layout strictly using alphabet letters and standard home-row keys
PIANO_KEYS = {
    # --- Left hand (Lower Octave / Bass) ---
    # Naturals: a, s, d, f, g, v, b
    "a": 48,  # C3
    "s": 50,  # D3
    "d": 52,  # E3
    "f": 53,  # F3
    "g": 55,  # G3
    "v": 57,  # A3
    "b": 59,  # B3
    # Accidentals (Sharps): w, e, r, t, y
    "w": 49,  # C#3
    "e": 51,  # D#3
    "r": 54,  # F#3
    "t": 56,  # G#3
    "y": 58,  # A#3

    # --- Right hand (Upper Octave / Treble) ---
    # Naturals: h, j, k, l, semicolon, quote, m
    "h": 60,          # C4
    "j": 62,          # D4
    "k": 64,          # E4
    "l": 65,          # F4
    "semicolon": 67,  # G4
    "quote": 69,      # A4
    "m": 71,          # B4
    # Accidentals (Sharps): u, i, o, p
    "u": 61,  # C#4
    "i": 63,  # D#4
    "o": 66,  # F#4
    "p": 68   # G#4
}

# Number key words from one to zero
SLOT_KEY_NAMES = [
    "one", "two", "three", "four", "five",
    "six", "seven", "eight", "nine", "zero"
]

def run():
    w = core.getW()

    # 1. Initialize Master Mixer
    master_mix = mixer()
    master_mix.create(frequency=44100, channels=2)

    # 2. Create MIDI Stream
    piano = musical()
    piano.create_empty_stream(channels=16)

    mfont = piano.load_font(core.config.get("piano musical toolkit", "piano.sf2"))
    piano.set_fonts(mfont)
    piano.play()

    # Add piano channel to mixer so both direct & mixer output coexist cleanly
    master_mix.add(piano)
    master_mix.play()

    if "piano pitch slot" not in core.config or not isinstance(core.config["piano pitch slot"], dict):
        core.config["piano pitch slot"] = {}

    active_notes = {}
    octave_shift = 0
    double_note_mode = False

    # Backing track recording & sequencer state
    is_recording_backing = False
    is_playing_backing = False
    backing_events = []
    record_start_time = 0.0
    playback_start_time = 0.0
    playback_idx = 0
    active_backing_notes = []

    def get_octave_number(shift):
        return 4 + (shift // 12)

    while 1:
        w.frameUpdate()
        
        # Pass piano.handle (or master_mix.handle) so recorder hooks directly to the native audio channel
        recorder.mainloop(piano.handle, w)

        if w.keyPressed("exit"):
            break

        if w.keyPressed("f1"):
            setting.run()

        current_time = time.time()

        # =====================================================================
        # 1. Backing Track Recording & Playback (Ctrl+O / Backslash)
        # =====================================================================
        ctrl_pressed = w.keyPressing("lcontrol") or w.keyPressing("rcontrol")
        if ctrl_pressed and w.keyPressed("o"):
            if not is_recording_backing:
                is_recording_backing = True
                backing_events = []
                record_start_time = current_time
                w.say("Recording backing track started")
            else:
                is_recording_backing = False
                total_duration = max(0.1, current_time - record_start_time)
                backing_events.append(("end", total_duration, 0))
                w.say("Recording backing track stopped")
            continue

        if w.keyPressed("backslash"):
            if not backing_events:
                w.say("No backing track recorded")
            else:
                is_playing_backing = not is_playing_backing
                if is_playing_backing:
                    playback_start_time = current_time
                    playback_idx = 0
                    active_backing_notes.clear()
                    w.say("Playing backing track")
                else:
                    for note in active_backing_notes:
                        piano.send_event(chan=1, event=MIDI_EVENT_NOTE, param=note | (0 << 8))
                    active_backing_notes.clear()
                    w.say("Stopped backing track")
            continue

        # =====================================================================
        # 2. Octave Adjustments (minus / equal)
        # =====================================================================
        if w.keyPressed("minus"):
            octave_shift -= 12
            w.say(f"Octave down, octave {get_octave_number(octave_shift)}")
        elif w.keyPressed("equal"):
            octave_shift += 12
            w.say(f"Octave up, octave {get_octave_number(octave_shift)}")

        # =====================================================================
        # 3. Toggle Double Note Mode (Single press Shift)
        # =====================================================================
        if w.keyPressed("lshift") or w.keyPressed("rshift"):
            double_note_mode = not double_note_mode
            w.say("Double note mode on" if double_note_mode else "Double note mode off")

        # =====================================================================
        # 4. Octave Slot Management (Alt/Shift + word keys)
        # =====================================================================
        alt_pressed = w.keyPressing("lalt") or w.keyPressing("ralt")
        shift_pressed = w.keyPressing("lshift") or w.keyPressing("rshift")

        for word_key in SLOT_KEY_NAMES:
            if w.keyPressed(word_key):
                if alt_pressed:
                    core.config["piano pitch slot"][word_key] = octave_shift
                    w.say(f"Slot {word_key} saved with octave {get_octave_number(octave_shift)}")
                elif shift_pressed:
                    if word_key in core.config["piano pitch slot"]:
                        del core.config["piano pitch slot"][word_key]
                        w.say(f"Slot {word_key} removed")
                    else:
                        w.say(f"Slot {word_key} is empty")
                else:
                    if word_key in core.config["piano pitch slot"]:
                        octave_shift = core.config["piano pitch slot"][word_key]
                        w.say(f"Switched to slot {word_key}, octave {get_octave_number(octave_shift)}")
                    else:
                        w.say(f"Slot {word_key} is empty")

        # Backing track loop processor
        if is_playing_backing and backing_events:
            total_loop_len = backing_events[-1][1] if backing_events[-1][0] == "end" else 5.0
            elapsed = (current_time - playback_start_time) % total_loop_len

            if playback_idx >= len(backing_events) - 1:
                playback_idx = 0
                playback_start_time = current_time
                elapsed = 0.0

            while playback_idx < len(backing_events) - 1:
                ev_type, ev_time, ev_note = backing_events[playback_idx]
                if ev_time <= elapsed:
                    if ev_type == "note_on":
                        piano.send_event(chan=1, event=MIDI_EVENT_NOTE, param=ev_note | (90 << 8))
                        if ev_note not in active_backing_notes:
                            active_backing_notes.append(ev_note)
                    elif ev_type == "note_off":
                        piano.send_event(chan=1, event=MIDI_EVENT_NOTE, param=ev_note | (0 << 8))
                        if ev_note in active_backing_notes:
                            active_backing_notes.remove(ev_note)
                    playback_idx += 1
                else:
                    break

        # =====================================================================
        # 5. Live Piano Keyboard Handler
        # =====================================================================
        for key, base_note in PIANO_KEYS.items():
            current_note = base_note + octave_shift
            upper_note = current_note + 12

            if w.keyPressing(key):
                if key not in active_notes:
                    notes_to_play = [current_note]
                    if double_note_mode:
                        notes_to_play.append(upper_note)

                    for n in notes_to_play:
                        piano.send_event(chan=0, event=MIDI_EVENT_NOTE, param=n | (100 << 8))
                        if is_recording_backing:
                            rel_time = current_time - record_start_time
                            backing_events.append(("note_on", rel_time, n))

                    active_notes[key] = notes_to_play

            elif key in active_notes:
                for n in active_notes[key]:
                    piano.send_event(chan=0, event=MIDI_EVENT_NOTE, param=n | (0 << 8))
                    if is_recording_backing:
                        rel_time = current_time - record_start_time
                        backing_events.append(("note_off", rel_time, n))
                del active_notes[key]

    piano.close()
    master_mix.close()