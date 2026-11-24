# -*- coding: utf-8 -*-
import core
import os
import sys
import time
from audio_instruments import musical, vst
import setting
import recorder

MIDI_EVENT_NOTE = 1

# White keys follow each row; black keys sit on the row above.
PIANO_KEYS = {
    # Left hand: white keys C3-B3; black keys on the row above.
    'z': 48, 'x': 50, 'c': 52, 'v': 53, 'b': 55, 'n': 57, 'm': 59,
    's': 49, 'd': 51, 'g': 54, 'h': 56, 'j': 58,
    'comma': 60, 'dot': 62, 'slash': 64,
    'l': 61, 'semicolon': 63,
    # Right hand: white keys C4-C5; black keys on the number row.
    'q': 60, 'w': 62, 'e': 64, 'r': 65, 't': 67, 'y': 69, 'u': 71, 'i': 72,
    'two': 61, 'three': 63, 'five': 66, 'six': 68, 'seven': 70,
    'o': 74, 'p': 76, '[': 77, ']': 79, 'backslash': 81,
    'nine': 73, 'zero': 75, 'minus': 78, 'equal': 80,
}
LEFT_HAND_KEYS = set('zxcvbnmsdghjl') | {'comma', 'dot', 'slash', 'semicolon'}

HELP = (
    "Piano: left hand Z X C V B N M comma period slash, C3 to E4; black keys S D G H J L semicolon. "
    "Right hand Q W E R T Y U I O P left bracket right bracket backslash, C4 to A5; "
    "black keys 2 3 5 6 7 9 0 minus equals. "
    "Hold left Shift for left-hand octave doubling; right Shift for right-hand doubling. "
    "Hold both for both hands. Tap left Ctrl to lower an octave, right Ctrl to raise an octave. "
    "Hold Space for sustain. Page Up/Down also shift octaves. F3 toggles octave doubling. "
    "Ctrl+number recalls an octave slot; Ctrl+Alt+number saves; Ctrl+Shift+number removes. "
    "Ctrl+O records backing; Ctrl+backslash plays backing; Tab records audio. F1 settings, F2 help."
)


class PianoEngine:
    """One live audio stream for keyboard, backing playback, and audio recording."""
    def __init__(self, config):
        vst_ok = getattr(core, 'vst_supported', lambda: True)()
        engine = config.get('active_engine', 'sf2') if vst_ok else 'sf2'
        self.engine = engine
        self.is_vst = engine in ('vst', 'vst3')
        if engine == 'vst3':
            from audio_instruments import vst3
            self.instrument = vst3()
        else:
            self.instrument = vst() if engine == 'vst' else musical()
        try:
            if engine == 'vst3':
                path = config.get('vst3_path', '')
                if not path or not os.path.exists(path):
                    raise RuntimeError('Select a piano VST3 plugin in F1, Piano Settings')
                if not self.instrument.create_instrument(path, frequency=44100):
                    raise RuntimeError('Could not load piano VST3; check the plugin path and architecture')
                if config.get('vst3_state'):
                    self.instrument.set_state(config['vst3_state'])
            elif engine == 'vst':
                path = config.get('vst_path', '')
                if not path or not os.path.isfile(path):
                    raise RuntimeError('Select a piano VST DLL in F1, Piano Settings')
                if not self.instrument.create_instrument(path, frequency=44100):
                    raise RuntimeError('Could not load piano VST; check the DLL and plugin architecture')
                if config.get('vst_chunk'):
                    self.instrument.set_chunk(config['vst_chunk'])
            else:
                self.instrument.create_empty_stream(channels=16)
                font = self.instrument.load_font(config['sf2_path'])
                self.instrument.set_fonts(font)
                self.instrument.send_event(chan=0, event=2, param=config.get('sf2_id', 0))
            self.instrument.play()
        except Exception:
            self.instrument.close()
            raise
        self.handle = self.instrument.handle
        self.voices = {}
        self.closed = False

    def send_event(self, chan, event, param):
        # Use one MIDI channel: VST pianos often only listen on channel 1.
        # Count overlapping live/backing voices so one release cannot cut another.
        if event == MIDI_EVENT_NOTE:
            note, velocity = param & 255, (param >> 8) & 255
            count = self.voices.get(note, 0)
            if velocity:
                self.voices[note] = count + 1
            elif count > 1:
                self.voices[note] = count - 1
                return
            else:
                self.voices.pop(note, None)
        if self.is_vst:
            return self.instrument.send_midi(0, event, param)
        return self.instrument.send_event(chan=0, event=event, param=param)

    def silence(self):
        self.send_event(0, 15, 0)
        for note in list(self.voices):
            self.voices[note] = 1
            self.send_event(0, MIDI_EVENT_NOTE, note)

    def close(self):
        if self.closed:
            return
        try:
            self.silence()
        finally:
            self.instrument.close()
            self.closed = True


# Number key words from one to zero
SLOT_KEY_NAMES = [
    "one", "two", "three", "four", "five",
    "six", "seven", "eight", "nine", "zero"
]

def stop_audio_recording(w):
    if core.recording:
        if core.recorder:
            core.recorder.close()
            core.recorder = None
        core.recording = False
        w.say("Stopped recording")


def run():
    w = core.getW()

    config = core.config['instruments']['piano']
    if getattr(core, 'vst_supported', lambda: True)() and not config.get('vst_path'):
        filename = '4Front Piano x64.dll' if sys.maxsize > 2**32 else '4Front Piano.dll'
        bundled = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'collections', 'plugins', filename)
        if os.path.isfile(bundled):
            config.update(active_engine='vst', vst_path=bundled)
            core.save()

    try:
        piano = PianoEngine(core.config['instruments']['piano'])
    except Exception as error:
        w.say(str(error))
        setting.open_instrument_settings('piano')
        try:
            piano = PianoEngine(core.config['instruments']['piano'])
        except Exception as error:
            w.say(str(error))
            return
    w.say("Piano " + ("VST3" if getattr(piano, 'engine', '') == 'vst3' else ("VST" if piano.is_vst else "SF2")) + ". F2 for keyboard help")

    if "piano pitch slot" not in core.config or not isinstance(core.config["piano pitch slot"], dict):
        core.config["piano pitch slot"] = {}

    active_notes = {}
    octave_shift = 0
    double_note_mode = False
    sustain = False
    control_down = {'lcontrol': False, 'rcontrol': False}
    control_tap = {'lcontrol': False, 'rcontrol': False}

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

    try:
        while 1:
            w.frameUpdate()

            # Apply a standalone Ctrl on release, leaving Ctrl shortcuts intact.
            shortcut_keys = set(PIANO_KEYS) | set(SLOT_KEY_NAMES) | {
                'f1', 'f2', 'f3', 'tab', 'space', 'page_up', 'page_down', 'exit'
            }
            shortcut = any(w.keyPressed(key) for key in shortcut_keys)
            shortcut = shortcut or any(w.keyPressing(key) for key in ('lalt', 'ralt', 'lshift', 'rshift'))
            controls = {key: bool(w.keyPressing(key)) for key in control_down}
            for key, delta in (('lcontrol', -12), ('rcontrol', 12)):
                if controls[key] and not control_down[key]:
                    control_tap[key] = True
                if shortcut or all(controls.values()):
                    control_tap[key] = False
                if control_down[key] and not controls[key] and control_tap[key]:
                    octave_shift = max(-48, min(48, octave_shift + delta))
                    w.say(f"Octave {'down' if delta < 0 else 'up'}, octave {get_octave_number(octave_shift)}")
                    control_tap[key] = False
            control_down = controls
        
            # Recorder expects a sound object exposing its native channel as .handle.
            recorder.mainloop(piano, w)

            if w.keyPressed("exit"):
                break

            if w.keyPressed("f2"):
                w.say(HELP)

            if w.keyPressed("f1"):
                piano.silence()
                active_backing_notes.clear()
                is_playing_backing = False
                if is_recording_backing:
                    is_recording_backing = False
                    duration = max(0.1, time.monotonic() - record_start_time)
                    backing_events.extend(('note_off', duration, note)
                                          for notes in active_notes.values() for note in notes)
                    backing_events.append(("end", duration, 0))
                active_notes.clear()
                stop_audio_recording(w)
                piano.close()
                setting.run()
                try:
                    piano = PianoEngine(core.config['instruments']['piano'])
                except Exception as error:
                    w.say(str(error))
                    return
                sustain = False
                continue

            current_time = time.monotonic()

            # =====================================================================
            # 1. Backing Track Recording & Playback (Ctrl+O / Ctrl+Backslash)
            # =====================================================================
            ctrl_pressed = w.keyPressing("lcontrol") or w.keyPressing("rcontrol")
            if ctrl_pressed and w.keyPressed("o"):
                if not is_recording_backing:
                    for note in active_backing_notes:
                        piano.send_event(1, MIDI_EVENT_NOTE, note)
                    active_backing_notes.clear()
                    is_playing_backing = False
                    is_recording_backing = True
                    backing_events = [('note_on', 0.0, note)
                                      for notes in active_notes.values() for note in notes]
                    record_start_time = current_time
                    w.say("Recording backing track started")
                else:
                    is_recording_backing = False
                    total_duration = max(0.1, current_time - record_start_time)
                    backing_events.extend(('note_off', total_duration, note)
                                          for notes in active_notes.values() for note in notes)
                    backing_events.append(("end", total_duration, 0))
                    w.say("Recording backing track stopped")
                continue

            if ctrl_pressed and w.keyPressed("backslash"):
                if is_recording_backing:
                    w.say("Stop backing recording with Ctrl+O first")
                elif not backing_events:
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
            # 2. Octave Adjustments (Page Down / Page Up)
            # =====================================================================
            if w.keyPressed("page_down"):
                octave_shift = max(-48, octave_shift - 12)
                w.say(f"Octave down, octave {get_octave_number(octave_shift)}")
            elif w.keyPressed("page_up"):
                octave_shift = min(48, octave_shift + 12)
                w.say(f"Octave up, octave {get_octave_number(octave_shift)}")

            # =====================================================================
            # 3. Octave doubling, away from slot modifiers
            # =====================================================================
            if w.keyPressed("f3"):
                double_note_mode = not double_note_mode
                w.say("Double note mode on" if double_note_mode else "Double note mode off")

            # =====================================================================
            # 4. Octave slots use Ctrl so number-row black keys stay playable.
            # =====================================================================
            alt_pressed = w.keyPressing("lalt") or w.keyPressing("ralt")
            shift_pressed = w.keyPressing("lshift") or w.keyPressing("rshift")

            for word_key in SLOT_KEY_NAMES:
                if ctrl_pressed and w.keyPressed(word_key):
                    if alt_pressed:
                        core.config["piano pitch slot"][word_key] = octave_shift
                        core.save()
                        w.say(f"Slot {word_key} saved with octave {get_octave_number(octave_shift)}")
                    elif shift_pressed:
                        if word_key in core.config["piano pitch slot"]:
                            del core.config["piano pitch slot"][word_key]
                            core.save()
                            w.say(f"Slot {word_key} removed")
                        else:
                            w.say(f"Slot {word_key} is empty")
                    else:
                        if word_key in core.config["piano pitch slot"]:
                            octave_shift = max(-48, min(48, core.config["piano pitch slot"][word_key]))
                            w.say(f"Switched to slot {word_key}, octave {get_octave_number(octave_shift)}")
                        else:
                            w.say(f"Slot {word_key} is empty")

            # Backing track loop processor
            if is_playing_backing and backing_events:
                total_loop_len = backing_events[-1][1] if backing_events[-1][0] == "end" else 5.0
                elapsed = current_time - playback_start_time

                if elapsed >= total_loop_len:
                    for note in active_backing_notes:
                        piano.send_event(1, MIDI_EVENT_NOTE, note)
                    active_backing_notes.clear()
                    playback_idx = 0
                    elapsed %= total_loop_len
                    playback_start_time = current_time - elapsed

                while playback_idx < len(backing_events) - 1:
                    ev_type, ev_time, ev_note = backing_events[playback_idx]
                    if ev_time <= elapsed:
                        if ev_type == "note_on":
                            piano.send_event(chan=1, event=MIDI_EVENT_NOTE, param=ev_note | (90 << 8))
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
            pedal_down = w.keyPressing("space")
            if pedal_down != sustain:
                sustain = pedal_down
                piano.send_event(0, 15, 127 if sustain else 0)

            for key, base_note in PIANO_KEYS.items():
                previous = active_notes.get(key, [])
                current_note = previous[0] if previous else base_note + octave_shift
                hand_shift = w.keyPressing('lshift' if key in LEFT_HAND_KEYS else 'rshift')
                if w.keyPressing(key) and not alt_pressed and (not ctrl_pressed or key in active_notes):
                    desired = [current_note]
                    if double_note_mode or hand_shift:
                        desired.append(current_note + 12)
                    desired = [n for n in desired if 0 <= n <= 127]
                    for n in previous:
                        if n not in desired:
                            piano.send_event(chan=0, event=MIDI_EVENT_NOTE, param=n)
                            if is_recording_backing:
                                backing_events.append(('note_off', current_time - record_start_time, n))
                    for n in desired:
                        if n not in previous:
                            piano.send_event(chan=0, event=MIDI_EVENT_NOTE, param=n | (100 << 8))
                            if is_recording_backing:
                                rel_time = current_time - record_start_time
                                backing_events.append(("note_on", rel_time, n))
                    active_notes[key] = desired

                elif key in active_notes:
                    for n in active_notes[key]:
                        piano.send_event(chan=0, event=MIDI_EVENT_NOTE, param=n | (0 << 8))
                        if is_recording_backing:
                            rel_time = current_time - record_start_time
                            backing_events.append(("note_off", rel_time, n))
                    del active_notes[key]

    finally:
        stop_audio_recording(w)
        piano.close()
