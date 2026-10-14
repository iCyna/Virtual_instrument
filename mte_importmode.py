import os
import time
import threading
import core
from pyaudiogaming.sound_pool import musical
from pyaudiogaming.sound_lib.instrument import MIDIStream

SAMPLE_RATE = 44100
NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
NOTE_BASE = {'c': 0, 'd': 2, 'e': 4, 'f': 5, 'g': 7, 'a': 9, 'b': 11}

DURATION_MAP = {
    "1": (4.0, "Whole"),
    "2": (2.0, "Half"),
    "3": (1.0, "Quarter"),
    "4": (0.5, "8th"),
    "5": (0.25, "16th"),
    "6": (0.125, "32nd"),
}

class LivePreviewSynth:
    """Live audio preview synth when typing or navigating notes in Import Mode"""
    def __init__(self, inst_type):
        self.inst_type = inst_type
        self.inst = None
        self.is_vst = False
        self.chan = 9 if "drum" in inst_type else 0
        self._init_engine()

    def _init_engine(self):
        inst_config = core.config["instruments"].get(self.inst_type)
        if not inst_config:
            return
        self.is_vst = (inst_config["active_engine"] == "vst" and bool(inst_config["vst_path"]) and os.path.exists(inst_config["vst_path"]))
        try:
            if self.is_vst:
                from pyaudiogaming.sound_pool import vst
                self.inst = vst()
                if self.inst.create_instrument(inst_config["vst_path"], frequency=SAMPLE_RATE):
                    if inst_config.get("vst_chunk"):
                        self.inst.set_chunk(inst_config["vst_chunk"])
                    self.inst.play()
            else:
                self.inst = musical()
                self.inst.open()
                sf2_path = inst_config.get("sf2_path", "")
                if sf2_path and os.path.exists(sf2_path):
                    loaded_font = self.inst.load_font(sf2_path)
                    self.inst.set_fonts(loaded_font)
                program_id = inst_config.get("sf2_id", 0)
                self.inst.send_event(self.chan, 2, int(program_id))
        except Exception as e:
            print(f"Preview synth error: {e}")

    def play_notes(self, midi_notes, dur_ms=300, velocity=100, pedal=False):
        if not self.inst or not midi_notes:
            return
        actual_dur = dur_ms * 2.0 if pedal else dur_ms

        def _worker():
            try:
                for n in midi_notes:
                    if n < 0: continue
                    param = n | (velocity << 8)
                    if self.is_vst: self.inst.send_midi(self.chan, 1, param)
                    else: self.inst.send_event(self.chan, 1, param)
                time.sleep(min(2.5, max(0.08, actual_dur / 1000.0)))
                for n in midi_notes:
                    if n < 0: continue
                    param = n | (0 << 8)
                    if self.is_vst: self.inst.send_midi(self.chan, 1, param)
                    else: self.inst.send_event(self.chan, 1, param)
            except Exception:
                pass

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def close(self):
        if self.inst:
            try:
                self.inst.close()
            except Exception:
                pass


class ImportModeState:
    """Independent Import Mode state for each Track"""
    def __init__(self, inst_type="piano"):
        self.inst_type = inst_type
        # Each item in items:
        # {'notes': [midi_int, ...], 'beats': 1.0, 'dur_name': 'Quarter', 'hand': 'R', 'pedal': False, 'triplet': False, 'dotted': False}
        # Empty 'notes' [] -> Rest
        self.items = []
        self.cursor = 0
        self.oct_right = 4
        self.oct_left = 3
        self.current_beats = 1.0
        self.current_dur_name = "Quarter"
        self.is_triplet = False
        self.is_dotted = False
        self.pedal = False
        self.chord_mode = False
        self.lock_writing = False
        self.sel_start = None
        self.sel_end = None


class ImportModeEditor:
    def __init__(self, app, track):
        self.app = app
        self.w = app.w
        self.track = track
        if not hasattr(self.track, "import_state") or self.track.import_state is None:
            self.track.import_state = ImportModeState("piano")
        self.st = self.track.import_state
        self.synth = LivePreviewSynth(self.st.inst_type)
        self.is_playing_seq = False

    def announce(self, text):
        self.app.announce(text)

    def get_effective_beats(self, base_beats=None, triplet=None, dotted=None):
        b = base_beats if base_beats is not None else self.st.current_beats
        tr = triplet if triplet is not None else self.st.is_triplet
        dt = dotted if dotted is not None else self.st.is_dotted
        if tr: b *= (2.0 / 3.0)
        if dt: b *= 1.5
        return b

    def midi_to_name(self, n):
        if "drum" in self.st.inst_type:
            return f"Drum {n}"
        return f"{NAMES[n % 12]}{(n // 12) - 1}"

    def format_item_speech(self, item):
        if not item['notes']:
            n_str = "Rest"
        else:
            n_str = " ".join(self.midi_to_name(n) for n in item['notes'])
        
        dur_str = item.get('dur_name', 'Quarter')
        if item.get('triplet'): dur_str += " triplet"
        if item.get('dotted'): dur_str += " dotted"
        
        extra = []
        if item['notes']:
            extra.append("Left" if item.get('hand') == 'L' else "Right")
        if item.get('pedal'):
            extra.append("Pedal")
            
        ext_str = f", {' '.join(extra)}" if extra else ""
        return f"{n_str}, {dur_str}{ext_str}"

    def speak_current(self):
        if not self.st.items:
            self.announce("Empty")
            return
        if self.st.cursor >= len(self.st.items):
            self.announce(f"End ({len(self.st.items)} notes)")
            return
        item = self.st.items[self.st.cursor]
        beat_ms = (60.0 / self.app.bpm) * 1000.0
        if item['notes']:
            self.synth.play_notes(item['notes'], int(item['beats'] * beat_ms), pedal=item.get('pedal', False))
        self.announce(self.format_item_speech(item))

    def get_item_time_ms(self, idx):
        beat_ms = (60.0 / self.app.bpm) * 1000.0
        t = 0.0
        for i in range(min(idx, len(self.st.items))):
            t += self.st.items[i]['beats'] * beat_ms
        return t

    def seek_by_beats(self, delta_beats):
        if not self.st.items:
            self.announce("Empty")
            return
        beat_ms = (60.0 / self.app.bpm) * 1000.0
        cur_ms = self.get_item_time_ms(self.st.cursor)
        target_ms = max(0.0, cur_ms + delta_beats * beat_ms)
        
        acc = 0.0
        new_idx = len(self.st.items) - 1
        for i, it in enumerate(self.st.items):
            if acc >= target_ms - 5:
                new_idx = i
                break
            acc += it['beats'] * beat_ms
        self.st.cursor = max(0, min(len(self.st.items) - 1, new_idx))
        self.speak_current()

    def seek_by_ms(self, delta_ms):
        beat_ms = (60.0 / self.app.bpm) * 1000.0
        self.seek_by_beats(delta_ms / beat_ms)

    def build_sequence_string(self):
        """Convert Import Mode items into MTE sequence syntax"""
        tokens = []
        for it in self.st.items:
            beats = round(it['beats'], 4)
            if not it['notes']:
                tokens.append(f"R-{beats}")
            else:
                vel = 95 if it.get('hand') == 'L' else 110
                if len(it['notes']) == 1:
                    n_name = str(it['notes'][0]) if "drum" in self.st.inst_type else f"{NAMES[it['notes'][0] % 12]}{(it['notes'][0] // 12) - 1}"
                    tokens.append(f"{n_name}-{beats}-{vel}")
                else:
                    names = [str(n) if "drum" in self.st.inst_type else f"{NAMES[n % 12]}{(n // 12) - 1}" for n in it['notes']]
                    tokens.append(f"[{','.join(names)}]-{beats}-{vel}")
        return " ".join(tokens)

    def save_to_track(self):
        if not self.st.items:
            self.announce("No notes to save.")
            return
        seq_str = self.build_sequence_string()
        from mte import parse_sequence_to_events, BackgroundMixerTask, ms_to_bytes, BYTES_PER_FRAME
        
        events, seq_time = parse_sequence_to_events(seq_str, self.st.inst_type, self.app.bpm)
        if not events:
            self.announce("Error converting notes.")
            return

        total_time_ms = seq_time + 500
        self.app.save_state()
        
        total_bytes = ms_to_bytes(total_time_ms)
        total_bytes -= (total_bytes % BYTES_PER_FRAME)
        if total_bytes <= 0: total_bytes = BYTES_PER_FRAME

        offset_bytes = ms_to_bytes(self.app.cursor_ms)
        req_len = offset_bytes + total_bytes
        if len(self.track.pcm) < req_len:
            self.track.pcm.extend(b"\x00" * (req_len - len(self.track.pcm)))

        task = BackgroundMixerTask(self.app, self.track, offset_bytes, events, total_time_ms, self.st.inst_type)
        task.start()
        self.announce(f"Saved {len(self.st.items)} steps to {self.track.name}.")

    def toggle_preview_play(self):
        if self.is_playing_seq:
            self.is_playing_seq = False
            self.announce("Stopped")
            return
        if not self.st.items:
            self.announce("Empty")
            return

        self.is_playing_seq = True
        start_idx = self.st.cursor if self.st.cursor < len(self.st.items) else 0
        beat_ms = (60.0 / self.app.bpm) * 1000.0
        self.announce("Playing")

        def _seq_player():
            for i in range(start_idx, len(self.st.items)):
                if not self.is_playing_seq:
                    break
                it = self.st.items[i]
                dur_ms = int(it['beats'] * beat_ms)
                if it['notes']:
                    self.synth.play_notes(it['notes'], dur_ms, pedal=it.get('pedal', False))
                
                slept = 0
                step = 20
                while slept < dur_ms and self.is_playing_seq:
                    time.sleep(step / 1000.0)
                    slept += step
            self.is_playing_seq = False

        threading.Thread(target=_seq_player, daemon=True).start()

    def run(self):
        self.announce(f"Import Mode: {self.track.name} ({self.st.inst_type.title()}). Right octave {self.st.oct_right}, Left {self.st.oct_left}.")

        while True:
            self.w.frameUpdate()
            if self.w.keyPressed("exit"):
                self.is_playing_seq = False
                self.synth.close()
                break

            ctrl = self.w.keyPressing("lcontrol") or self.w.keyPressing("rcontrol")
            shift = self.w.keyPressing("lshift") or self.w.keyPressing("rshift")
            alt = self.w.keyPressing("lalt") or self.w.keyPressing("ralt")

            # System shortcuts: Ctrl+S, Ctrl+A, Ctrl+Q, Ctrl+E
            if ctrl and self.w.keyPressed("s"):
                self.save_to_track()
                continue
            if ctrl and self.w.keyPressed("a"):
                if self.st.items:
                    self.st.sel_start = 0
                    self.st.sel_end = len(self.st.items) - 1
                    self.announce(f"Selected all {len(self.st.items)} notes")
                else:
                    self.announce("Empty")
                continue
            if ctrl and self.w.keyPressed("q"):
                self.st.sel_start = self.st.cursor
                self.announce(f"Start marker: step {self.st.cursor + 1}")
                continue
            if ctrl and self.w.keyPressed("e"):
                self.st.sel_end = self.st.cursor
                self.announce(f"End marker: step {self.st.cursor + 1}")
                continue

            # Toggle Lock Writing (L)
            if self.w.keyPressed("l") and not ctrl:
                self.st.lock_writing = not self.st.lock_writing
                self.announce("Lock writing On" if self.st.lock_writing else "Lock writing Off")
                continue

            # Toggle Pedal (M)
            if self.w.keyPressed("m") and not ctrl:
                self.st.pedal = not self.st.pedal
                if 0 <= self.st.cursor < len(self.st.items) and not self.st.lock_writing:
                    self.st.items[self.st.cursor]['pedal'] = self.st.pedal
                self.announce("Pedal On" if self.st.pedal else "Pedal Off")
                continue

            # Toggle Chord / Double-note Mode (N)
            if self.w.keyPressed("n") and not ctrl:
                self.st.chord_mode = not self.st.chord_mode
                self.announce("Chord mode On" if self.st.chord_mode else "Chord mode Off")
                continue

            # Space: Preview playback
            if self.w.keyPressed("space"):
                self.toggle_preview_play()
                continue

            # Backspace: Delete previous note or selection
            if self.w.keyPressed("backspace"):
                if self.st.lock_writing:
                    self.announce("Writing locked")
                    continue
                if self.st.sel_start is not None and self.st.sel_end is not None:
                    s, e = min(self.st.sel_start, self.st.sel_end), max(self.st.sel_start, self.st.sel_end)
                    del self.st.items[s:e+1]
                    self.st.cursor = min(s, len(self.st.items))
                    self.st.sel_start = self.st.sel_end = None
                    self.announce("Deleted selection")
                elif self.st.items and self.st.cursor > 0:
                    removed = self.st.items.pop(self.st.cursor - 1)
                    self.st.cursor -= 1
                    self.announce(f"Deleted {self.format_item_speech(removed)}")
                elif self.st.items and self.st.cursor == 0:
                    removed = self.st.items.pop(0)
                    self.announce(f"Deleted {self.format_item_speech(removed)}")
                else:
                    self.announce("Empty")
                continue

            # Duration keys: 1-6, 7 (Triplet), 8 (Dotted), 0 (Rest)
            for d_key, (b_val, b_name) in DURATION_MAP.items():
                if self.w.keyPressed(d_key) and not ctrl and not shift:
                    self.st.current_beats = b_val
                    self.st.current_dur_name = b_name
                    eff = self.get_effective_beats()
                    if 0 <= self.st.cursor < len(self.st.items) and not self.st.lock_writing:
                        self.st.items[self.st.cursor]['beats'] = eff
                        self.st.items[self.st.cursor]['dur_name'] = b_name
                    self.announce(b_name)
                    break

            if self.w.keyPressed("7") and not ctrl:
                self.st.is_triplet = not self.st.is_triplet
                if 0 <= self.st.cursor < len(self.st.items) and not self.st.lock_writing:
                    self.st.items[self.st.cursor]['triplet'] = self.st.is_triplet
                    base_b = DURATION_MAP.get(next((k for k, v in DURATION_MAP.items() if v[1] == self.st.items[self.st.cursor]['dur_name']), "3"))[0]
                    self.st.items[self.st.cursor]['beats'] = self.get_effective_beats(
                        base_b,
                        self.st.is_triplet,
                        self.st.items[self.st.cursor].get('dotted', False)
                    )
                self.announce("Triplet On" if self.st.is_triplet else "Triplet Off")
                continue

            if self.w.keyPressed("8") and not ctrl:
                self.st.is_dotted = not self.st.is_dotted
                if 0 <= self.st.cursor < len(self.st.items) and not self.st.lock_writing:
                    self.st.items[self.st.cursor]['dotted'] = self.st.is_dotted
                    base_b = DURATION_MAP.get(next((k for k, v in DURATION_MAP.items() if v[1] == self.st.items[self.st.cursor]['dur_name']), "3"))[0]
                    self.st.items[self.st.cursor]['beats'] = self.get_effective_beats(
                        base_b,
                        self.st.items[self.st.cursor].get('triplet', False),
                        self.st.is_dotted
                    )
                self.announce("Dotted On" if self.st.is_dotted else "Dotted Off")
                continue

            # Key 0: Insert Rest
            if self.w.keyPressed("0") and not ctrl:
                if not self.st.lock_writing:
                    rest_item = {
                        'notes': [],
                        'beats': self.get_effective_beats(),
                        'dur_name': self.st.current_dur_name,
                        'hand': 'R',
                        'pedal': False,
                        'triplet': self.st.is_triplet,
                        'dotted': self.st.is_dotted
                    }
                    self.st.items.insert(self.st.cursor, rest_item)
                    self.st.cursor += 1
                self.announce(f"Rest, {self.st.current_dur_name}")
                continue

            # Sharp (=) and Flat (-) on current note
            if self.w.keyPressed("equals") or self.w.keyPressed("minus"):
                if 0 <= self.st.cursor < len(self.st.items) and self.st.items[self.st.cursor]['notes']:
                    delta_semi = 1 if self.w.keyPressed("equals") else -1
                    it = self.st.items[self.st.cursor]
                    it['notes'][-1] = max(0, min(127, it['notes'][-1] + delta_semi))
                    self.speak_current()
                continue

            # Note input: C, D, E, F, G, A, B
            for n_char, semi in NOTE_BASE.items():
                if self.w.keyPressed(n_char) and not ctrl:
                    hand = 'L' if shift else 'R'
                    octv = self.st.oct_left if shift else self.st.oct_right
                    midi_val = 12 + (octv * 12) + semi
                    midi_val = max(0, min(127, midi_val))

                    beat_ms = (60.0 / self.app.bpm) * 1000.0
                    eff_beats = self.get_effective_beats()

                    if self.st.lock_writing:
                        self.synth.play_notes([midi_val], int(eff_beats * beat_ms), pedal=self.st.pedal)
                        self.announce(f"{self.midi_to_name(midi_val)}")
                    else:
                        if (self.st.chord_mode or alt) and self.st.items and self.st.cursor > 0:
                            target_idx = self.st.cursor - 1 if self.st.cursor == len(self.st.items) else self.st.cursor
                            target = self.st.items[target_idx]
                            if midi_val not in target['notes']:
                                target['notes'].append(midi_val)
                                target['notes'].sort()
                            self.synth.play_notes(target['notes'], int(target['beats'] * beat_ms), pedal=target.get('pedal', False))
                            self.announce(self.format_item_speech(target))
                        else:
                            new_item = {
                                'notes': [midi_val],
                                'beats': eff_beats,
                                'dur_name': self.st.current_dur_name,
                                'hand': hand,
                                'pedal': self.st.pedal,
                                'triplet': self.st.is_triplet,
                                'dotted': self.st.is_dotted
                            }
                            self.st.items.insert(self.st.cursor, new_item)
                            self.st.cursor += 1
                            self.synth.play_notes([midi_val], int(eff_beats * beat_ms), pedal=self.st.pedal)
                            self.announce(self.format_item_speech(new_item))
                    break

            # Left / Right Navigation
            if self.w.keyPressed("left") or self.w.keyPressed("right"):
                direction = -1 if self.w.keyPressed("left") else 1
                if alt:
                    # Alt + Left/Right: Seek 5 seconds
                    self.seek_by_ms(direction * 5000.0)
                elif ctrl:
                    # Ctrl + Left/Right: Seek by section (4 bars)
                    self.seek_by_beats(direction * (self.app.time_sig * 4))
                elif shift:
                    # Shift + Left/Right: Seek by bar
                    self.seek_by_beats(direction * self.app.time_sig)
                else:
                    # Normal Left/Right: Step through notes
                    if not self.st.items:
                        self.announce("Empty")
                    else:
                        self.st.cursor = max(0, min(len(self.st.items), self.st.cursor + direction))
                        self.speak_current()
                continue

            # Up / Down: Adjust Octave
            if self.w.keyPressed("up") or self.w.keyPressed("down"):
                is_up = self.w.keyPressed("up")
                
                if shift:
                    new_oct = 8 if is_up else 1
                else:
                    new_oct = min(8, self.st.oct_right + 1) if is_up else max(1, self.st.oct_right - 1)

                if 0 <= self.st.cursor < len(self.st.items) and self.st.items[self.st.cursor]['notes'] and not self.st.lock_writing:
                    it = self.st.items[self.st.cursor]
                    if shift:
                        target_oct = 8 if is_up else 1
                        it['notes'] = [12 + (target_oct * 12) + (n % 12) for n in it['notes']]
                    else:
                        step_semi = 12 if is_up else -12
                        it['notes'] = [max(0, min(127, n + step_semi)) for n in it['notes']]
                    
                    cur_oct = (it['notes'][0] // 12) - 1
                    if it.get('hand') == 'L': self.st.oct_left = cur_oct
                    else: self.st.oct_right = cur_oct
                    self.speak_current()
                else:
                    self.st.oct_right = new_oct
                    self.st.oct_left = max(1, new_oct - 1)
                    self.announce(f"Octave Right {self.st.oct_right}, Left {self.st.oct_left}")
                continue