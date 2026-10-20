import os
import re
import copy
import time
import threading
import core
from pyaudiogaming import menu
from pyaudiogaming.inputBox import kbt
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

# 14 Left-Hand Accompaniment & Articulation Styles (Alt + M)
LH_STYLES = [
    ("Non-Legato (Standard 85%)", "articulation", 0.85),
    ("Legato (Smooth Connected 105%)", "articulation", 1.05),
    ("Staccato (Short Crisp 35%)", "articulation", 0.35),
    ("Ballad Sustain (Root-5th-8ve Block)", [([0, 7, 12], 1.0, 1.3, 0.9)], 1.2),
    # 5 Asian Piano Styles
    ("Asian Pop Ballad (1-5-8-5 Arpeggio)", [([0], 0.25, 1.2, 0.95), ([7], 0.25, 1.2, 0.8), ([12], 0.25, 1.2, 0.85), ([7], 0.25, 1.2, 0.75)], 1.2),
    ("V-Pop / C-Pop Sentimental (1-5-8-10)", [([0], 0.25, 1.3, 0.95), ([7], 0.25, 1.3, 0.8), ([12], 0.25, 1.3, 0.85), ([16], 0.25, 1.3, 0.9)], 1.3),
    ("K-Drama OST (Warm 6/8 Arpeggio)", [([0], 0.33, 1.3, 0.9), ([7], 0.33, 1.3, 0.75), ([12, 16], 0.34, 1.3, 0.85)], 1.3),
    ("Anime / J-Pop 8-Beat (Driving Pop)", [([0, 12], 0.25, 0.8, 1.0), ([7], 0.25, 0.7, 0.75), ([0, 12], 0.25, 0.8, 0.9), ([7], 0.25, 0.7, 0.8)], 0.85),
    ("Asian Bolero / Rumba (Slow Syncopated)", [([0], 0.375, 1.1, 0.95), ([7, 12], 0.125, 0.8, 0.8), ([7, 12], 0.25, 0.9, 0.85), ([4, 7], 0.25, 0.9, 0.8)], 1.0),
    # 5 European / Western Piano Styles
    ("Classical Alberti Bass (Mozart 1-8-5-8)", [([0], 0.25, 0.9, 0.9), ([12], 0.25, 0.9, 0.75), ([7], 0.25, 0.9, 0.8), ([12], 0.25, 0.9, 0.75)], 0.9),
    ("European Waltz 3/4 (Oom-Pah-Pah)", [([0], 0.34, 0.9, 1.0), ([4, 7], 0.33, 0.5, 0.75), ([4, 7], 0.33, 0.5, 0.75)], 0.8),
    ("Romantic Nocturne (Chopin Wide Spread)", [([0], 0.2, 1.4, 0.95), ([7], 0.2, 1.4, 0.75), ([12], 0.2, 1.4, 0.8), ([16], 0.2, 1.4, 0.85), ([12], 0.2, 1.4, 0.75)], 1.4),
    ("European Bossa / Lounge (Syncopated)", [([0], 0.375, 1.0, 0.95), ([4, 7, 11], 0.25, 0.6, 0.8), ([7], 0.375, 1.0, 0.85)], 0.9),
    ("Euro Boogie / Swing (Walking Shuffle)", [([0, 7], 0.34, 0.7, 0.95), ([0, 9], 0.16, 0.6, 0.8), ([0, 7], 0.34, 0.7, 0.9), ([0, 9], 0.16, 0.6, 0.8)], 0.75),
]

CHORD_INTERVALS = {
    "": [0, 4, 7], "M": [0, 4, 7], "MAJ": [0, 4, 7], "MIN": [0, 3, 7],
    "DIM": [0, 3, 6], "AUG": [0, 4, 8], "SUS2": [0, 2, 7], "SUS4": [0, 5, 7],
    "7": [0, 4, 7, 10], "MAJ7": [0, 4, 7, 11], "M7": [0, 3, 7, 10],
    "MIN7": [0, 3, 7, 10], "6": [0, 4, 7, 9], "M6": [0, 3, 7, 9],
    "ADD9": [0, 4, 7, 14], "9": [0, 4, 7, 10, 14],
}


def parse_chord_symbol(symbol, octave=3):
    s = symbol.strip()
    if not s:
        return None, []
    m = re.match(r"^([A-Ga-g])([#bB]?)(.*)$", s)
    if not m:
        return None, []
    letter = m.group(1).upper()
    acc = m.group(2)
    qual = m.group(3).strip()

    semi = NOTE_BASE.get(letter.lower(), 0)
    if acc == '#': semi += 1
    elif acc in ('b', 'B'): semi -= 1

    root_midi = 12 + (octave * 12) + semi
    if qual == "m": intervals = [0, 3, 7]
    elif qual == "m7": intervals = [0, 3, 7, 10]
    else: intervals = CHORD_INTERVALS.get(qual.upper(), [0, 4, 7])

    notes = [max(0, min(127, root_midi + iv)) for iv in intervals]
    return root_midi, notes


class LivePreviewSynth:
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

    def play_notes(self, midi_notes, dur_ms=300, velocity=100, pedal=False, gate_ratio=1.0):
        if not self.inst or not midi_notes:
            return
        actual_dur = dur_ms * gate_ratio * (1.8 if pedal else 1.0)

        def _worker():
            try:
                for n in midi_notes:
                    if n < 0: continue
                    param = n | (velocity << 8)
                    if self.is_vst: self.inst.send_midi(self.chan, 1, param)
                    else: self.inst.send_event(self.chan, 1, param)
                time.sleep(min(3.5, max(0.04, actual_dur / 1000.0)))
                for n in midi_notes:
                    if n < 0: continue
                    param = n | (0 << 8)
                    if self.is_vst: self.inst.send_midi(self.chan, 1, param)
                    else: self.inst.send_event(self.chan, 1, param)
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def play_style_pattern(self, root_midi, is_minor, total_dur_ms, style_idx, pedal=False):
        style_name, pattern_data, gate_default = LH_STYLES[style_idx]
        if pattern_data == "articulation":
            self.play_notes([root_midi], total_dur_ms, velocity=90, pedal=pedal, gate_ratio=gate_default)
            return

        def _pat_worker():
            for offsets, frac, gate, v_scale in pattern_data:
                step_ms = total_dur_ms * frac
                notes = []
                for off in offsets:
                    if off in (4, 16) and is_minor:
                        off -= 1
                    notes.append(max(0, min(127, root_midi + off)))
                self.play_notes(notes, step_ms, velocity=int(90 * v_scale), pedal=pedal, gate_ratio=gate)
                time.sleep(max(0.04, step_ms / 1000.0))

        threading.Thread(target=_pat_worker, daemon=True).start()

    def close(self):
        if self.inst:
            try:
                self.inst.close()
            except Exception:
                pass


class ImportModeState:
    """Independent Import Mode state for each Track - Supports Simultaneous Right & Left Hands"""
    def __init__(self, inst_type="piano"):
        self.inst_type = inst_type
        # Each item in items represents a rhythmic step on the timeline:
        # {
        #   'notes': [right_hand_midi, ...],
        #   'lh_notes': [left_hand_midi, ...], # Plays SIMULTANEOUSLY with right hand!
        #   'beats': 1.0,
        #   'dur_name': 'Quarter',
        #   'pedal': False,
        #   'triplet': False,
        #   'dotted': False,
        #   'style_idx': 0,
        #   'chord_tag': None
        # }
        self.items = []
        self.clipboard = []
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
        self.shift_attaches_lh = True  # Shift+Note attaches simultaneous LH bass/style to current step!
        self.lh_style_idx = 0
        self.last_preview_midi = 60
        self.sel_start = None
        self.sel_end = None
        self.velocity = 100
        self.slide_note_over_key_time = False
        # Semitone transpose applied to newly entered notes while no selection is active.
        self.input_pitch_offset = 0


class ImportModeEditor:
    def __init__(self, app, track):
        self.app = app
        self.w = app.w
        self.track = track
        if not hasattr(self.track, "import_state") or self.track.import_state is None:
            self.track.import_state = ImportModeState("piano")
        self.st = self.track.import_state
        # Ensure backward compatibility if old state exists
        if not hasattr(self.st, "clipboard"): self.st.clipboard = []
        if not hasattr(self.st, "shift_attaches_lh"): self.st.shift_attaches_lh = True
        if not hasattr(self.st, "input_pitch_offset"): self.st.input_pitch_offset = 0
        if not hasattr(self.st, "velocity"): self.st.velocity = 100
        if not hasattr(self.st, "slide_note_over_key_time"): self.st.slide_note_over_key_time = False
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

    def get_bar_beat_position(self, idx):
        """Calculate Bar and Beat number (1-indexed) for any step index"""
        total_beats = sum(it['beats'] for it in self.st.items[:min(idx, len(self.st.items))])
        bar_num = int(total_beats // self.app.time_sig) + 1
        beat_in_bar = round((total_beats % self.app.time_sig) + 1, 2)
        if beat_in_bar == int(beat_in_bar):
            beat_in_bar = int(beat_in_bar)
        return bar_num, beat_in_bar

    def format_item_speech(self, item, idx=None):
        rh = item.get('notes', [])
        lh = item.get('lh_notes', [])
        
        parts = []
        if rh:
            parts.append(" ".join(self.midi_to_name(n) for n in rh))
        if lh:
            parts.append("LH " + " ".join(self.midi_to_name(n) for n in lh))
        if item.get('chord_tag'):
            parts.append(f"Chord {item['chord_tag']}")
        if not parts:
            parts.append("Rest")
            
        dur_str = item.get('dur_name', 'Quarter')
        if item.get('triplet'): dur_str += " triplet"
        if item.get('dotted'): dur_str += " dotted"
        
        pos_str = ""
        if idx is not None:
            bar_n, beat_n = self.get_bar_beat_position(idx)
            pos_str = f", Bar {bar_n} Beat {beat_n}"

        pedal_str = ", Pedal" if item.get('pedal') else ""
        return f"{' + '.join(parts)}, {dur_str}{pedal_str}{pos_str}"

    def play_item_preview(self, item):
        beat_ms = (60.0 / self.app.bpm) * 1000.0
        dur_ms = int(item['beats'] * beat_ms)
        style_idx = item.get('style_idx', self.st.lh_style_idx)
        _, pattern_data, gate_ratio = LH_STYLES[style_idx]

        # 1. Play Right-Hand Melody / Chords
        if item.get('notes'):
            self.synth.play_notes(item['notes'], dur_ms, velocity=getattr(self.st, "velocity", 100), pedal=item.get('pedal', False), gate_ratio=gate_ratio)

        # 2. Play Simultaneous Left-Hand Notes / Pattern
        lh = item.get('lh_notes', [])
        if lh:
            if pattern_data != "articulation" and "drum" not in self.st.inst_type:
                self.synth.play_style_pattern(lh[0], False, dur_ms, style_idx, pedal=item.get('pedal', False))
            else:
                self.synth.play_notes(lh, dur_ms, velocity=90, pedal=item.get('pedal', False), gate_ratio=gate_ratio)

        # 3. Play Simultaneous Section Chord if assigned
        if item.get('chord_tag') and "drum" not in self.st.inst_type:
            root_m, c_notes = parse_chord_symbol(item['chord_tag'], self.st.oct_left)
            if root_m is not None:
                is_min = "m" in item['chord_tag'] and "maj" not in item['chord_tag'].lower()
                if pattern_data != "articulation":
                    self.synth.play_style_pattern(root_m, is_min, dur_ms, style_idx, pedal=True)
                else:
                    self.synth.play_notes(c_notes, dur_ms, velocity=85, pedal=item.get('pedal', False), gate_ratio=gate_ratio)

    def speak_current(self):
        if not self.st.items:
            self.announce("Empty")
            return
        if self.st.cursor >= len(self.st.items):
            bar_n, beat_n = self.get_bar_beat_position(len(self.st.items))
            self.announce(f"End ({len(self.st.items)} steps, Bar {bar_n} Beat {beat_n})")
            return
        item = self.st.items[self.st.cursor]
        if item.get('notes'):
            self.st.last_preview_midi = item['notes'][-1]
        elif item.get('lh_notes'):
            self.st.last_preview_midi = item['lh_notes'][-1]
        self.play_item_preview(item)
        self.announce(self.format_item_speech(item, self.st.cursor))

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

    def go_to_bar(self):
        """Press G: Jump directly to any Bar number in a full song"""
        if not self.st.items:
            self.announce("Empty")
            return
        total_bars, _ = self.get_bar_beat_position(len(self.st.items))
        ans = kbt(None, "Go to Bar", f"Enter bar number (1 to {total_bars}):", "1")
        if not ans or not ans.strip().isdigit():
            return
        target_bar = max(1, int(ans.strip()))
        target_beats = (target_bar - 1) * self.app.time_sig
        
        acc_beats = 0.0
        chosen_idx = len(self.st.items) - 1
        for i, it in enumerate(self.st.items):
            if acc_beats >= target_beats - 0.05:
                chosen_idx = i
                break
            acc_beats += it['beats']
        self.st.cursor = chosen_idx
        self.speak_current()

    def quick_text_insert(self):
        """Press I: Quickly type or paste a phrase of notes (e.g., C4-1 D4-0.5 E4-0.5 F4-2) into Import Mode"""
        ans = kbt(
            None,
            "Quick Phrase Insert",
            "Enter notes (e.g., C4-1 D4-0.5 E4-0.5 [C4,E4,G4]-2 R-1):",
            ""
        )
        if not ans or not ans.strip():
            return
        from mte import parse_single_note
        tokens = ans.strip().split()
        added = 0
        for tok in tokens:
            parts = tok.split("-")
            p_str = parts[0].strip().upper()
            try:
                b_val = float(parts[1]) if len(parts) > 1 else self.st.current_beats
            except ValueError:
                b_val = self.st.current_beats

            dur_label = f"{b_val}b"
            for _, (db, dn) in DURATION_MAP.items():
                if abs(db - b_val) < 0.02:
                    dur_label = dn
                    break

            notes_list = []
            if p_str != "R":
                if p_str.startswith("[") and p_str.endswith("]"):
                    notes_list = [parse_single_note(x, self.st.inst_type) for x in p_str[1:-1].split(",")]
                    notes_list = [n for n in notes_list if n != -1]
                else:
                    n_val = parse_single_note(p_str, self.st.inst_type)
                    if n_val != -1:
                        notes_list = [n_val]

            new_it = {
                'notes': notes_list,
                'lh_notes': [],
                'beats': b_val,
                'dur_name': dur_label,
                'pedal': self.st.pedal,
                'triplet': False,
                'dotted': False,
                'style_idx': self.st.lh_style_idx,
                'chord_tag': None
            }
            self.st.items.insert(self.st.cursor, new_it)
            self.st.cursor += 1
            added += 1

        self.announce(f"Inserted {added} steps.")

    def toggle_pitch_target(self):
        """Ctrl+Space: toggle between editing the cursor note and future-note pitch setup."""
        if self.st.sel_start is not None and self.st.sel_end is not None:
            self.st.sel_start = self.st.sel_end = None
            self.announce(
                f"Selection cleared. New notes transpose: {self.st.input_pitch_offset:+d} semitones"
            )
            return

        if not self.st.items or self.st.cursor >= len(self.st.items):
            self.announce("No note at cursor. Arrows will set pitch for new notes.")
            return

        self.st.sel_start = self.st.sel_end = self.st.cursor
        item = self.st.items[self.st.cursor]
        notes = item.get("notes", []) + item.get("lh_notes", [])
        if notes:
            self.st.last_preview_midi = notes[-1]
        self.announce(f"Selected step {self.st.cursor + 1} for pitch editing")

    def adjust_pitch(self, semitones):
        """Arrows transpose the selected steps, or set the transpose for future notes."""
        if self.st.lock_writing:
            self.announce("Writing locked")
            return

        has_selection = self.st.sel_start is not None and self.st.sel_end is not None
        if not has_selection:
            self.st.input_pitch_offset = max(-127, min(127, self.st.input_pitch_offset + semitones))
            self.announce(
                f"New-note pitch offset {self.st.input_pitch_offset:+d} semitones "
                f"({self.st.input_pitch_offset / 12:+.1f} octaves)"
            )
            return

        start = max(0, min(self.st.sel_start, self.st.sel_end))
        end = min(len(self.st.items) - 1, max(self.st.sel_start, self.st.sel_end))
        changed = 0
        for idx in range(start, end + 1):
            item = self.st.items[idx]
            for key in ("notes", "lh_notes"):
                if key in item:
                    old_notes = item.get(key, [])
                    item[key] = [max(0, min(127, n + semitones)) for n in old_notes]
                    changed += len(old_notes)
        if changed:
            item = self.st.items[min(max(self.st.cursor, start), end)]
            notes = item.get("notes", []) or item.get("lh_notes", [])
            if notes:
                self.st.last_preview_midi = notes[-1]
            self.play_item_preview(item)
            self.announce(
                f"Transposed steps {start + 1}-{end + 1} by {semitones:+d} semitones"
            )
        else:
            self.announce("Selected steps contain no pitched notes")

    def copy_selection(self):
        if not self.st.items:
            self.announce("Empty")
            return
        if self.st.sel_start is not None and self.st.sel_end is not None:
            s, e = min(self.st.sel_start, self.st.sel_end), max(self.st.sel_start, self.st.sel_end)
            self.st.clipboard = copy.deepcopy(self.st.items[s:e+1])
        else:
            target = self.st.cursor - 1 if self.st.cursor >= len(self.st.items) else self.st.cursor
            self.st.clipboard = [copy.deepcopy(self.st.items[target])]
        self.announce(f"Copied {len(self.st.clipboard)} steps")

    def cut_selection(self):
        if self.st.lock_writing or not self.st.items:
            return
        if self.st.sel_start is not None and self.st.sel_end is not None:
            s, e = min(self.st.sel_start, self.st.sel_end), max(self.st.sel_start, self.st.sel_end)
            self.st.clipboard = copy.deepcopy(self.st.items[s:e+1])
            del self.st.items[s:e+1]
            self.st.cursor = min(s, len(self.st.items))
            self.st.sel_start = self.st.sel_end = None
            self.announce(f"Cut {len(self.st.clipboard)} steps")

    def paste_clipboard(self):
        if self.st.lock_writing:
            self.announce("Writing locked")
            return
        if not self.st.clipboard:
            self.announce("Clipboard empty")
            return
        for it in self.st.clipboard:
            self.st.items.insert(self.st.cursor, copy.deepcopy(it))
            self.st.cursor += 1
        bar_n, beat_n = self.get_bar_beat_position(self.st.cursor)
        self.announce(f"Pasted {len(self.st.clipboard)} steps. Now at Bar {bar_n} Beat {beat_n}")

    def duplicate_selection(self):
        """Ctrl + D: Instantly duplicate selected section or current bar/phrase"""
        if self.st.lock_writing or not self.st.items:
            return
        self.copy_selection()
        self.paste_clipboard()

    def open_left_hand_style_menu(self):
        m = menu.menu()
        m.init(self.w, "Left-Hand Styles & Articulations (Alt+M)")
        for idx, (s_name, _, _) in enumerate(LH_STYLES):
            prefix = "[Active] " if idx == self.st.lh_style_idx else ""
            m.append(f"{prefix}{s_name}")
        m.append("Close")
        m.open()

        while True:
            self.w.frameUpdate()
            sel = m.frameUpdate()
            if sel is None: continue
            if sel == -1 or sel == len(LH_STYLES): break
            self.st.lh_style_idx = sel
            chosen_name = LH_STYLES[sel][0]
            target_idx = self.st.cursor - 1 if self.st.cursor >= len(self.st.items) else self.st.cursor
            if 0 <= target_idx < len(self.st.items) and not self.st.lock_writing:
                self.st.items[target_idx]['style_idx'] = sel
            self.announce(f"Style set to {chosen_name}")
            break

    def open_section_chord_editor(self):
        if not self.st.items:
            self.announce("Add melody notes first before assigning section chords.")
            return

        if self.st.sel_start is not None and self.st.sel_end is not None:
            s_idx = min(self.st.sel_start, self.st.sel_end)
            e_idx = max(self.st.sel_start, self.st.sel_end)
        else:
            s_idx = 0
            e_idx = len(self.st.items) - 1

        s_bar, _ = self.get_bar_beat_position(s_idx)
        e_bar, _ = self.get_bar_beat_position(e_idx + 1)

        prompt = (
            f"Assign chords from Bar {s_bar} to Bar {e_bar} (Steps {s_idx + 1}-{e_idx + 1}).\n"
            "Enter 1 chord per bar (e.g., C G Am Em F C Dm G7):"
        )
        ans = kbt(None, "Song / Section Chord Progression", prompt, "C G Am F")
        if not ans or not ans.strip():
            return

        chords = [c.strip() for c in ans.strip().split() if c.strip()]
        if not chords:
            return

        beat_acc = self.app.time_sig  # Trigger immediately on first step
        chord_idx = 0
        applied_count = 0
        for i in range(s_idx, min(e_idx + 1, len(self.st.items))):
            it = self.st.items[i]
            if beat_acc >= self.app.time_sig - 0.05:
                it['chord_tag'] = chords[chord_idx % len(chords)]
                it['style_idx'] = self.st.lh_style_idx
                chord_idx += 1
                applied_count += 1
                beat_acc = 0.0
            else:
                it['chord_tag'] = None
            beat_acc += it['beats']

        self.announce(f"Applied {applied_count} bar chords ({' '.join(chords)}) with {LH_STYLES[self.st.lh_style_idx][0]}.")

    def build_sequence_string(self):
        """Render full song timeline: simultaneous Right Hand + Left Hand + Bar Chords"""
        beat_ms = (60.0 / self.app.bpm) * 1000.0
        current_ms = 0.0
        tokens = []

        def midi_str(m_val):
            return str(m_val) if "drum" in self.st.inst_type else f"{NAMES[m_val % 12]}{(m_val // 12) - 1}"

        for it in self.st.items:
            step_dur_ms = it['beats'] * beat_ms
            style_idx = it.get('style_idx', self.st.lh_style_idx)
            _, pattern_data, gate_default = LH_STYLES[style_idx]
            pedal_mult = 1.6 if it.get('pedal') else 1.0

            # 1. Right-Hand Melody / Chords
            rh_notes = it.get('notes', [])
            if rh_notes:
                actual_dur = max(25, int(step_dur_ms * gate_default * pedal_mult))
                start_t = int(round(current_ms))
                for n_m in rh_notes:
                    vel = max(1, min(127, int(it.get("velocity", getattr(self.st, "velocity", 100)))))
                    tokens.append(f"{midi_str(n_m)}@{start_t}-{actual_dur}-{vel}")

            # 2. Simultaneous Left-Hand Notes / Accompaniment attached to this step
            lh_notes = it.get('lh_notes', [])
            if lh_notes:
                if pattern_data != "articulation" and "drum" not in self.st.inst_type:
                    root_m = lh_notes[0]
                    sub_offset = 0.0
                    # Span pattern over a full bar or step duration
                    pat_span_ms = max(step_dur_ms, self.app.time_sig * beat_ms) if len(lh_notes) == 1 else step_dur_ms
                    for offsets, frac, gate, v_scale in pattern_data:
                        sub_dur = pat_span_ms * frac
                        actual_dur = max(25, int(sub_dur * gate * pedal_mult))
                        start_t = int(round(current_ms + sub_offset))
                        sub_vel = max(1, min(127, int(90 * v_scale)))
                        for off in offsets:
                            n_m = max(0, min(127, root_m + off))
                            tokens.append(f"{midi_str(n_m)}@{start_t}-{actual_dur}-{sub_vel}")
                        sub_offset += sub_dur
                else:
                    actual_dur = max(25, int(step_dur_ms * gate_default * pedal_mult))
                    start_t = int(round(current_ms))
                    for n_m in lh_notes:
                        tokens.append(f"{midi_str(n_m)}@{start_t}-{actual_dur}-90")

            # 3. Simultaneous Bar / Section Chord Progression
            if it.get('chord_tag') and "drum" not in self.st.inst_type:
                root_m, c_notes = parse_chord_symbol(it['chord_tag'], self.st.oct_left)
                if root_m is not None:
                    is_min = "m" in it['chord_tag'] and "maj" not in it['chord_tag'].lower()
                    bar_dur_ms = self.app.time_sig * beat_ms
                    if pattern_data != "articulation":
                        sub_offset = 0.0
                        for offsets, frac, gate, v_scale in pattern_data:
                            sub_dur = bar_dur_ms * frac
                            actual_dur = max(25, int(sub_dur * gate * 1.3))
                            start_t = int(round(current_ms + sub_offset))
                            sub_vel = max(1, min(127, int(85 * v_scale)))
                            for off in offsets:
                                if off in (4, 16) and is_min:
                                    off -= 1
                                n_m = max(0, min(127, root_m + off))
                                tokens.append(f"{midi_str(n_m)}@{start_t}-{actual_dur}-{sub_vel}")
                            sub_offset += sub_dur
                    else:
                        actual_dur = max(25, int(bar_dur_ms * gate_default * 1.2))
                        start_t = int(round(current_ms))
                        for n_m in c_notes:
                            tokens.append(f"{midi_str(n_m)}@{start_t}-{actual_dur}-85")

            current_ms += step_dur_ms

        if not tokens and self.st.items:
            return f"R-{round(sum(x['beats'] for x in self.st.items), 2)}"
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

        # Replace track PCM from cursor_ms so re-saving updates cleanly
        offset_bytes = ms_to_bytes(self.app.cursor_ms)
        del self.track.pcm[offset_bytes:]
        self.track.pcm.extend(b"\x00" * total_bytes)

        task = BackgroundMixerTask(self.app, self.track, offset_bytes, events, total_time_ms, self.st.inst_type)
        task.start()
        total_bars, _ = self.get_bar_beat_position(len(self.st.items))
        self.announce(f"Saved {len(self.st.items)} steps ({total_bars} bars) to {self.track.name}.")

    def toggle_preview_play(self):
        if self.is_playing_seq:
            self.is_playing_seq = False
            bar_n, beat_n = self.get_bar_beat_position(self.st.cursor)
            self.announce(f"Stopped at Bar {bar_n} Beat {beat_n}")
            return
        if not self.st.items:
            self.announce("Empty")
            return

        self.is_playing_seq = True
        # Space always plays the complete imported song from its beginning.
        start_idx = 0
        self.st.cursor = 0
        beat_ms = (60.0 / self.app.bpm) * 1000.0
        self.announce("Playing")

        def _seq_player():
            for i in range(start_idx, len(self.st.items)):
                if not self.is_playing_seq:
                    break
                self.st.cursor = i
                it = self.st.items[i]
                dur_ms = int(it['beats'] * beat_ms)
                self.play_item_preview(it)
                
                slept = 0
                step = 20
                while slept < dur_ms and self.is_playing_seq:
                    time.sleep(step / 1000.0)
                    slept += step
            self.is_playing_seq = False

        threading.Thread(target=_seq_player, daemon=True).start()

    def run(self):
        self.announce(
            f"Import Mode: {self.track.name} ({self.st.inst_type.title()}). "
            f"Right octave {self.st.oct_right}, Left {self.st.oct_left}. "
            "Shift+Note attaches simultaneous Left Hand. Press H for Bar Chords, I for Quick Phrase."
        )

        while True:
            self.w.frameUpdate()
            if self.w.keyPressed("exit"):
                self.is_playing_seq = False
                self.synth.close()
                self.announce("Exited Import Mode")
                break

            ctrl = self.w.keyPressing("lcontrol") or self.w.keyPressing("rcontrol")
            shift = self.w.keyPressing("lshift") or self.w.keyPressing("rshift")
            alt = self.w.keyPressing("lalt") or self.w.keyPressing("ralt")

            # Ctrl+Space toggles pitch-edit selection versus future-note pitch setup.
            if ctrl and self.w.keyPressed("space"):
                self.toggle_pitch_target()
                continue

            # System & Editing shortcuts: Ctrl+S, Ctrl+A, Ctrl+Q, Ctrl+E, Ctrl+C, Ctrl+X, Ctrl+V, Ctrl+D
            if ctrl and self.w.keyPressed("s"): self.save_to_track(); continue
            if ctrl and self.w.keyPressed("c"): self.copy_selection(); continue
            if ctrl and self.w.keyPressed("x"): self.cut_selection(); continue
            if ctrl and self.w.keyPressed("v"): self.paste_clipboard(); continue
            if ctrl and self.w.keyPressed("d"): self.duplicate_selection(); continue
            if ctrl and self.w.keyPressed("a"):
                if self.st.items:
                    self.st.sel_start, self.st.sel_end = 0, len(self.st.items) - 1
                    self.announce(f"Selected all {len(self.st.items)} steps")
                else:
                    self.announce("Empty")
                continue
            if ctrl and self.w.keyPressed("q"):
                self.st.sel_start = self.st.cursor
                bar_n, beat_n = self.get_bar_beat_position(self.st.cursor)
                self.announce(f"Start marker: Step {self.st.cursor + 1} (Bar {bar_n} Beat {beat_n})")
                continue
            if ctrl and self.w.keyPressed("e"):
                self.st.sel_end = self.st.cursor
                bar_n, beat_n = self.get_bar_beat_position(self.st.cursor)
                self.announce(f"End marker: Step {self.st.cursor + 1} (Bar {bar_n} Beat {beat_n})")
                continue

            # Tab: Toggle Shift+Note behavior (Simultaneous LH attach vs Standalone LH step)
            if self.w.keyPressed("tab") and not ctrl:
                self.st.shift_attaches_lh = not self.st.shift_attaches_lh
                mode_msg = "Simultaneous Left-Hand Attach" if self.st.shift_attaches_lh else "Standalone Left-Hand Step"
                self.announce(f"Shift+Note mode: {mode_msg}")
                continue

            # Home / End navigation
            if self.w.keyPressed("home"):
                self.st.cursor = 0
                self.speak_current()
                continue
            if self.w.keyPressed("end"):
                self.st.cursor = len(self.st.items)
                self.speak_current()
                continue

            # G: Go to Bar
            if self.w.keyPressed("g") and ctrl:
                self.go_to_bar()
                continue

            # I: Quick Phrase Text Insert
            if self.w.keyPressed("i") and not ctrl:
                self.quick_text_insert()
                continue

            # Alt + M: Left-Hand Accompaniment & Articulation Styles
            if alt and self.w.keyPressed("m"):
                self.open_left_hand_style_menu()
                continue

            # H: Song / Section Chord Progression Editor
            if self.w.keyPressed("h"):
                self.open_section_chord_editor()
                continue

            # Toggle Lock Writing (L)
            if self.w.keyPressed("l") and not ctrl and not alt:
                self.st.lock_writing = not self.st.lock_writing
                self.announce("Lock writing On (Free Preview)" if self.st.lock_writing else "Lock writing Off")
                continue

            # Toggle Pedal (M without Alt)
            if self.w.keyPressed("m") and not ctrl and not alt:
                self.st.pedal = not self.st.pedal
                target_idx = self.st.cursor - 1 if self.st.cursor >= len(self.st.items) else self.st.cursor
                if 0 <= target_idx < len(self.st.items) and not self.st.lock_writing:
                    self.st.items[target_idx]['pedal'] = self.st.pedal
                self.announce("Pedal On" if self.st.pedal else "Pedal Off")
                continue

            # Toggle Chord / Double-note Mode (N)
            if self.w.keyPressed("n") and not ctrl and not alt:
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

            # S toggles slide/hold-length mode.
            if self.w.keyPressed("s") and not ctrl and not alt:
                self.st.slide_note_over_key_time = not self.st.slide_note_over_key_time
                self.announce("Slide note over key time On" if self.st.slide_note_over_key_time else "Slide note over key time Off; using selected duration")
                continue

            # Brackets change velocity, not pitch accidentals.
            if self.w.keyPressed("[") or self.w.keyPressed("]"):
                delta_v = -5 if self.w.keyPressed("[") else 5
                self.st.velocity = max(1, min(127, getattr(self.st, "velocity", 100) + delta_v))
                self.announce(f"Velocity {self.st.velocity}")
                continue

            # Duration keys: 1-6, 7 (Triplet), 8 (Dotted), 0 (Rest)
            for d_key, (b_val, b_name) in DURATION_MAP.items():
                if self.w.keyPressed(d_key) and not ctrl and not shift:
                    self.st.current_beats = b_val
                    self.st.current_dur_name = b_name
                    eff = self.get_effective_beats()
                    target_idx = self.st.cursor - 1 if self.st.cursor >= len(self.st.items) else self.st.cursor
                    if 0 <= target_idx < len(self.st.items) and not self.st.lock_writing:
                        self.st.items[target_idx]['beats'] = eff
                        self.st.items[target_idx]['dur_name'] = b_name
                    self.announce(b_name)
                    break

            if self.w.keyPressed("7") and not ctrl:
                self.st.is_triplet = not self.st.is_triplet
                target_idx = self.st.cursor - 1 if self.st.cursor >= len(self.st.items) else self.st.cursor
                if 0 <= target_idx < len(self.st.items) and not self.st.lock_writing:
                    self.st.items[target_idx]['triplet'] = self.st.is_triplet
                    base_b = DURATION_MAP.get(next((k for k, v in DURATION_MAP.items() if v[1] == self.st.items[target_idx]['dur_name']), "3"))[0]
                    self.st.items[target_idx]['beats'] = self.get_effective_beats(base_b, self.st.is_triplet, self.st.items[target_idx].get('dotted', False))
                self.announce("Triplet On" if self.st.is_triplet else "Triplet Off")
                continue

            if self.w.keyPressed("8") and not ctrl:
                self.st.is_dotted = not self.st.is_dotted
                target_idx = self.st.cursor - 1 if self.st.cursor >= len(self.st.items) else self.st.cursor
                if 0 <= target_idx < len(self.st.items) and not self.st.lock_writing:
                    self.st.items[target_idx]['dotted'] = self.st.is_dotted
                    base_b = DURATION_MAP.get(next((k for k, v in DURATION_MAP.items() if v[1] == self.st.items[target_idx]['dur_name']), "3"))[0]
                    self.st.items[target_idx]['beats'] = self.get_effective_beats(base_b, self.st.items[target_idx].get('triplet', False), self.st.is_dotted)
                self.announce("Dotted On" if self.st.is_dotted else "Dotted Off")
                continue

            # Key 0: Insert Rest
            if self.w.keyPressed("0") and not ctrl:
                if not self.st.lock_writing:
                    rest_item = {
                        'notes': [], 'lh_notes': [],
                        'beats': self.get_effective_beats(),
                        'dur_name': self.st.current_dur_name,
                        'pedal': False, 'triplet': self.st.is_triplet, 'dotted': self.st.is_dotted,
                        'style_idx': self.st.lh_style_idx, 'chord_tag': None
                    }
                    self.st.items.insert(self.st.cursor, rest_item)
                    self.st.cursor += 1
                    bar_n, beat_n = self.get_bar_beat_position(self.st.cursor - 1)
                    self.announce(f"Rest, {self.st.current_dur_name}, Bar {bar_n} Beat {beat_n}")
                else:
                    self.announce(f"Rest, {self.st.current_dur_name}")
                continue

            # Note input: C, D, E, F, G, A, B
            for n_char, semi in NOTE_BASE.items():
                if self.w.keyPressed(n_char) and not ctrl:
                    hand = 'L' if shift else 'R'
                    octv = self.st.oct_left if shift else self.st.oct_right

                    # Pitch arrows set this offset when no note/region is selected.
                    # It persists for subsequent input until changed again.
                    midi_val = max(
                        0,
                        min(127, 12 + (octv * 12) + semi + self.st.input_pitch_offset)
                    )
                    self.st.last_preview_midi = midi_val

                    beat_ms = (60.0 / self.app.bpm) * 1000.0
                    eff_beats = self.get_effective_beats()
                    dur_ms = int(eff_beats * beat_ms)
                    _, pattern_data, gate_r = LH_STYLES[self.st.lh_style_idx]

                    if self.st.lock_writing:
                        if hand == 'L' and pattern_data != "articulation":
                            self.synth.play_style_pattern(midi_val, False, dur_ms, self.st.lh_style_idx, pedal=self.st.pedal)
                        else:
                            self.synth.play_notes([midi_val], dur_ms, pedal=self.st.pedal, gate_ratio=gate_r)
                        self.announce(f"{self.midi_to_name(midi_val)}, {self.st.current_dur_name}, {'Left' if hand == 'L' else 'Right'}")
                    else:
                        # Simultaneous Left-Hand attachment when pressing Shift+Note!
                        if hand == 'L' and self.st.shift_attaches_lh and self.st.items:
                            target_idx = self.st.cursor - 1 if self.st.cursor >= len(self.st.items) else self.st.cursor
                            target = self.st.items[target_idx]
                            if 'lh_notes' not in target:
                                target['lh_notes'] = []
                            if self.st.chord_mode or alt:
                                if midi_val not in target['lh_notes']:
                                    target['lh_notes'].append(midi_val)
                                    target['lh_notes'].sort()
                            else:
                                target['lh_notes'] = [midi_val]
                            target['style_idx'] = self.st.lh_style_idx
                            self.play_item_preview(target)
                            self.announce(self.format_item_speech(target, target_idx))
                        elif (self.st.chord_mode or alt) and self.st.items and self.st.cursor > 0:
                            target_idx = self.st.cursor - 1 if self.st.cursor >= len(self.st.items) else self.st.cursor
                            target = self.st.items[target_idx]
                            if midi_val not in target['notes']:
                                target['notes'].append(midi_val)
                                target['notes'].sort()
                            self.play_item_preview(target)
                            self.announce(self.format_item_speech(target, target_idx))
                        else:
                            new_item = {
                                'notes': [] if hand == 'L' else [midi_val],
                                'lh_notes': [midi_val] if hand == 'L' else [],
                                'beats': eff_beats,
                                'dur_name': self.st.current_dur_name,
                                'pedal': self.st.pedal,
                                'triplet': self.st.is_triplet,
                                'dotted': self.st.is_dotted,
                                'style_idx': self.st.lh_style_idx,
                                'chord_tag': None
                            }
                            self.st.items.insert(self.st.cursor, new_item)
                            self.st.cursor += 1
                            self.play_item_preview(new_item)
                            self.announce(self.format_item_speech(new_item, self.st.cursor - 1))
                    break

            # Left / Right Navigation
            if self.w.keyPressed("left") or self.w.keyPressed("right"):
                direction = -1 if self.w.keyPressed("left") else 1
                if alt:
                    self.seek_by_ms(direction * 5000.0)
                elif ctrl:
                    self.seek_by_beats(direction * (self.app.time_sig * 4))
                elif shift:
                    self.seek_by_beats(direction * self.app.time_sig)
                else:
                    if not self.st.items:
                        self.announce("Empty")
                    else:
                        self.st.cursor = max(0, min(len(self.st.items), self.st.cursor + direction))
                        self.speak_current()
                continue

            # Up / Down: semitone pitch change; Shift+Up/Down: octave (12 semitones).
            # With a selection, transpose all notes in that selected range.
            # Without a selection, set the persistent pitch offset for newly entered notes.
            if self.w.keyPressed("up") or self.w.keyPressed("down"):
                direction = 1 if self.w.keyPressed("up") else -1
                semitone_step = 12 if shift else 1
                self.adjust_pitch(direction * semitone_step)
                continue
