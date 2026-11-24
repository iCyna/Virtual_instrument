import os
import re
import copy
import time
import threading
import core
from pyaudiogaming import menu
from pyaudiogaming.inputBox import kbt
from audio_instruments import musical

SAMPLE_RATE = 44100
NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
NOTE_BASE = {'c': 0, 'd': 2, 'e': 4, 'f': 5, 'g': 7, 'a': 9, 'b': 11}


def item_playback_events(item):
    """Keep written notes separate from their realized ornaments and ties."""
    pitches = item.get('notes', []) + item.get('lh_notes', [])
    original = item.get('notation_notes', [])
    shifts = {n - old for n, old in zip(pitches, original)}
    if ('playback_events' in item and len(pitches) == len(original)
            and len(shifts) <= 1):
        shift = next(iter(shifts), 0)
        original_beats = item.get('notation_beats', 0)
        scale = item['beats'] / original_beats if original_beats else 1
        return [dict(event, notes=[max(0, min(127, n + shift)) for n in event['notes']],
                     offset_ms=event['offset_ms'] * scale,
                     duration_ms=event['duration_ms'] * scale)
                for event in item['playback_events']]
    return [dict(notes=pitches, offset_ms=0,
                 duration_ms=item['preview_ms'], velocity=item.get('velocity', 90))] if pitches else []

DURATION_MAP = {
    "1": (4.0, "Whole"),
    "2": (2.0, "Half"),
    "3": (1.0, "Quarter"),
    "4": (0.5, "8th"),
    "5": (0.25, "16th"),
    "6": (0.125, "32nd"),
}

# Left-Hand Accompaniment & Articulation Styles (Alt + M)
LH_STYLES = [
    ("Non-Legato (Standard 85%)", "articulation", 0.85),
    ("Legato (Smooth Connected 110%)", "articulation", 1.10),
    ("Staccato (Short Crisp 40%)", "articulation", 0.40),
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
    ("Staccatissimo (Very Short 20%)", "articulation", 0.20),
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
        self._note_lock = threading.Lock()
        self._active_notes = {}
        self._init_engine()

    def _init_engine(self):
        self.is_vst = core.vst_supported() and core.config['instruments'][self.inst_type].get('active_engine') in ('vst', 'vst3')
        try:
            self.inst = core.open_live_instrument(core.config, self.inst_type)
        except Exception as e:
            self.inst = None
            print(f"Preview synth error: {e}")
            window = core.getW()
            if window:
                window.say(f"Could not load {self.inst_type}: {e}")

    def play_notes(self, midi_notes, dur_ms=300, velocity=100, pedal=False, gate_ratio=1.0):
        if not self.inst or not midi_notes:
            return
        actual_dur = dur_ms * gate_ratio * (1.8 if pedal else 1.0)

        # Send complete chords before returning to the timeline scheduler.
        # An older note-off must not silence a newer/longer overlapping voice
        # of the same pitch (including unisons shared by the two clefs).
        notes = list(dict.fromkeys(n for n in midi_notes if 0 <= n <= 127))
        with self._note_lock:
            for n in notes:
                self._send_note(n, velocity)
                self._active_notes[n] = self._active_notes.get(n, 0) + 1

        def _worker():
            time.sleep(max(0.001, actual_dur / 1000.0))
            with self._note_lock:
                for n in notes:
                    remaining = self._active_notes.get(n, 0) - 1
                    if remaining > 0:
                        self._active_notes[n] = remaining
                    elif n in self._active_notes:
                        del self._active_notes[n]
                        self._send_note(n, 0)

        threading.Thread(target=_worker, daemon=True).start()

    def _send_note(self, note, velocity):
        param = int(note) | (int(velocity) << 8)
        if self.is_vst:
            self.inst.send_midi(self.chan, 1, param)
        else:
            self.inst.send_event(self.chan, 1, param)

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
        with self._note_lock:
            if self.inst:
                for n in self._active_notes:
                    self._send_note(n, 0)
                self._active_notes.clear()
                try:
                    self.inst.close()
                finally:
                    self.inst = None


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
        self.key_tonic = "C"
        self.key_mode = "Major"
        # One-shot adjustment for the next entered note.
        self.input_pitch_offset = 0
        self.clefs = ['treble', 'bass']
        self.active_clef = 'treble'
        self.active_lane = None


class ImportModeEditor:
    def __init__(self, app, track):
        self.app = app
        self.w = app.w
        self.track = track
        if not hasattr(self.track, "import_state") or self.track.import_state is None:
            self.track.import_state = ImportModeState("piano")
        self.st = self.track.import_state
        if not hasattr(self.st, 'clefs'): self.st.clefs = ['treble', 'bass']
        if not hasattr(self.st, 'active_clef'): self.st.active_clef = 'treble'
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

    def switch_clef(self, direction):
        self.st.active_lane = None
        self._vertical_context = None
        index = self.st.clefs.index(self.st.active_clef)
        self.st.active_clef = self.st.clefs[(index + direction) % len(self.st.clefs)]
        if any('notation_clef' in item for item in self.st.items):
            label = {'treble': 'Upper staff', 'bass': 'Lower staff', 'alto': 'Alto clef'}
        else:
            label = {'treble': 'Treble clef', 'alto': 'Alto clef', 'bass': 'Bass clef'}
        self.announce(label[self.st.active_clef])

    def add_clef(self):
        chooser = menu.menu()
        chooser.init(self.w, 'Select clef')
        options = [('treble', 'Treble clef'), ('alto', 'Alto clef'), ('bass', 'Bass clef')]
        for _, name in options:
            chooser.append(name)
        chooser.open()
        while True:
            self.w.frameUpdate()
            selected = chooser.frameUpdate()
            if selected is None: continue
            if selected == -1: return
            clef, name = options[selected]
            if clef not in self.st.clefs:
                self.st.clefs.append(clef)
            self.st.active_clef = clef
            self.st.active_lane = None
            self._vertical_context = None
            self.announce(name)
            return

    def clef_notes(self, item):
        # Older steps store the two hands without an explicit clef.
        if 'clef_notes' in item:
            return item['clef_notes'].get(self.st.active_clef, [])
        key = 'lh_notes' if self.st.active_clef == 'bass' else 'notes'
        assigned = item.get('clef', 'treble')
        return item.get(key, []) if key == 'lh_notes' or assigned == self.st.active_clef else []

    def navigate_clef(self, direction):
        from score_navigation import lane
        self._vertical_context = None
        if self.st.cursor == len(self.st.items) and (direction > 0 or not self.st.items):
            self.speak_current()
            return
        index = self.st.cursor + direction
        selected_lane = getattr(self.st, 'active_lane', None)
        while 0 <= index < len(self.st.items):
            candidate = self.st.items[index]
            in_lane = selected_lane is None or tuple(selected_lane) == lane(candidate)
            if in_lane and (self.clef_notes(candidate) or candidate.get('rest_clef') == self.st.active_clef):
                self.st.cursor = index
                self.speak_current()
                return
            index += direction
        if (0 <= self.st.cursor < len(self.st.items)
                and (self.clef_notes(self.st.items[self.st.cursor])
                     or self.st.items[self.st.cursor].get('rest_clef') == self.st.active_clef)):
            if direction > 0:
                self.st.cursor = len(self.st.items)
            self.speak_current()
        else:
            self.announce('No more notes in this clef')

    def navigate_vertical(self, direction):
        from score_navigation import vertical_notes, lane
        if not 0 <= self.st.cursor < len(self.st.items):
            self.announce('No note at the cursor')
            return
        current = self.st.items[self.st.cursor]
        if 'score_offset' not in current:
            self.switch_clef(direction)
            self.speak_current()
            return
        previous = getattr(self, '_vertical_context', None)
        anchor = previous[0] if previous and previous[1] == self.st.cursor else current['score_offset']
        rows = vertical_notes(self.st.items, anchor)
        if not rows:
            return
        if previous and previous[1] == self.st.cursor and previous[3] == rows:
            position = (previous[2] + direction) % len(rows)
        else:
            positions = [i for i, (index, _) in enumerate(rows) if index == self.st.cursor]
            position = (positions[0] if direction > 0 else positions[-1]) if positions else 0
        index, pitch = rows[position]
        item = self.st.items[index]
        self.st.cursor = index
        self.st.active_clef = item.get('clef', 'treble')
        self.st.active_lane = list(lane(item))
        self._vertical_context = (anchor, index, position, rows)
        name = 'Rest' if pitch is None else item.get('pitch_names', {}).get(pitch, self.midi_to_name(pitch))
        self.announce(f"{item.get('staff_name', self.st.active_clef)}, voice {item.get('voice_id', '1')}, "
                      f"{name}, {position + 1} of {len(rows)}")
        if pitch is not None:
            self.synth.play_notes([pitch], 350, velocity=item.get('velocity', self.st.velocity), gate_ratio=1.0)

    def read_chord_note(self, direction):
        """Inspect one pitch without moving or editing the score cursor."""
        if not 0 <= self.st.cursor < len(self.st.items):
            self.announce('No note at the cursor')
            return
        item = self.st.items[self.st.cursor]
        pitches = sorted(set(self.clef_notes(item)))
        if not pitches:
            self.announce('Rest, no chord notes')
            return
        context = (id(item), self.st.active_clef, tuple(pitches))
        if getattr(self, '_chord_context', None) != context:
            index = 0 if direction > 0 else len(pitches) - 1
        else:
            index = max(0, min(len(pitches) - 1, self._chord_note_index + direction))
        self._chord_context = context
        self._chord_note_index = index
        pitch = pitches[index]
        name = item.get('pitch_names', {}).get(pitch, self.midi_to_name(pitch))
        self.announce(f'{name}, note {index + 1} of {len(pitches)}')
        self.synth.play_notes([pitch], 350, velocity=item.get('velocity', self.st.velocity), gate_ratio=1.0)

    def delete_current(self):
        from score_navigation import lane

        if self.st.lock_writing:
            self.announce('Writing locked')
            return
        idx = self.st.cursor
        if idx == len(self.st.items):
            selected_lane = getattr(self.st, 'active_lane', None)
            for idx in range(len(self.st.items) - 1, -1, -1):
                candidate = self.st.items[idx]
                if (self.clef_notes(candidate)
                        and (selected_lane is None or tuple(selected_lane) == lane(candidate))):
                    break
            else:
                self.announce('No previous note in this clef or voice')
                return
        if not 0 <= idx < len(self.st.items):
            self.announce('No note at cursor')
            return
        item = self.st.items[idx]
        if not self.clef_notes(item):
            self.announce('No notes in this clef')
            return
        removed = dict(item, notes=list(self.clef_notes(item)), lh_notes=[])
        if 'clef_notes' in item:
            item['clef_notes'][self.st.active_clef] = []
        key = 'lh_notes' if self.st.active_clef == 'bass' else 'notes'
        item[key] = []
        item.setdefault('deleted_clefs', []).append(self.st.active_clef)
        item['rest_clef'] = self.st.active_clef
        item['chord_tag'] = None
        self.st.cursor = idx
        self._vertical_context = None
        self.st.sel_start = self.st.sel_end = None
        self.announce(f'Deleted {self.format_item_speech(removed)}')

    def insert_item(self, item):
        """Fill a deleted slot without shifting the following notes."""
        item.setdefault("velocity", self.st.velocity)
        idx = self.st.cursor
        if 0 <= idx < len(self.st.items):
            target = self.st.items[idx]
            if self.st.active_clef in target.get('deleted_clefs', []):
                notes = self.clef_notes(item)
                key = 'lh_notes' if self.st.active_clef == 'bass' else 'notes'
                target[key] = list(notes)
                if 'clef_notes' in target:
                    target['clef_notes'][self.st.active_clef] = list(notes)
                target['deleted_clefs'].remove(self.st.active_clef)
                if notes:
                    target.pop('rest_clef', None)
                self.st.cursor += 1
                return target
        self.st.items.insert(idx, item)
        self.st.cursor += 1
        return item

    def change_duration(self, duration=None, toggle=None):
        idx = self.st.cursor
        if not 0 <= idx < len(self.st.items):
            if duration:
                self.st.current_beats, self.st.current_dur_name = duration
            elif toggle == 'triplet':
                self.st.is_triplet = not self.st.is_triplet
            elif toggle == 'dotted':
                self.st.is_dotted = not self.st.is_dotted
            return
        if self.st.lock_writing:
            self.announce('Writing locked')
            return
        item = self.st.items[idx]
        if not self.clef_notes(item) and item.get('rest_clef') != self.st.active_clef:
            self.announce('No notes in this clef')
            return
        old_beats = item['beats']
        factor = (2 / 3 if item.get('triplet') else 1) * (1.5 if item.get('dotted') else 1)
        base = old_beats / factor if old_beats else 0.25
        if duration:
            base, item['dur_name'] = duration
        if toggle:
            item[toggle] = not item.get(toggle, False)
        item['beats'] = self.get_effective_beats(base, item.get('triplet', False), item.get('dotted', False))
        if 'preview_ms' in item and old_beats:
            item['preview_ms'] *= item['beats'] / old_beats
        if 'score_duration' in item:
            item['score_duration'] = item['beats']

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
        if idx < len(self.st.items) and 'score_position' in self.st.items[idx]:
            return self.st.items[idx]['score_position']
        if self.st.items and 'score_position' in self.st.items[-1]:
            last = self.st.items[-1]
            bar, beat = last['score_position']
            return bar, beat + last['beats']
        total_beats = sum(it['beats'] for it in self.st.items[:min(idx, len(self.st.items))])
        bar_num = int(total_beats // self.app.time_sig) + 1
        beat_in_bar = round((total_beats % self.app.time_sig) * getattr(self.app, "time_sig_denominator", 4) / 4 + 1, 2)
        if beat_in_bar == int(beat_in_bar):
            beat_in_bar = int(beat_in_bar)
        return bar_num, beat_in_bar

    def format_item_speech(self, item, idx=None):
        rh = item.get('notes', [])
        lh = item.get('lh_notes', [])
        
        parts = []
        if rh:
            parts.append(" ".join(item.get('pitch_names', {}).get(n, self.midi_to_name(n)) for n in rh))
        if lh:
            parts.append("LH " + " ".join(item.get('pitch_names', {}).get(n, self.midi_to_name(n)) for n in lh))
        if item.get('chord_tag'):
            parts.append(f"Chord {item['chord_tag']}")
        if not parts:
            parts.append("Rest")
            
        dur_str = item.get('dur_name', 'Quarter')
        if 'score_duration' in item:
            dur_str += f", {item['score_duration']:g} beats"
        if item.get('triplet'): dur_str += " triplet"
        if item.get('dotted'): dur_str += " dotted"
        if item.get('grace'): dur_str += ', grace note'
        if item.get('notation_marks'): dur_str += ', ' + ', '.join(item['notation_marks'])
        if 'lh_notes' in item and item.get('notation_clef'):
            dur_str += ', ' + ('lower staff' if item.get('clef') == 'bass' else 'upper staff')
        if item.get('notation_clef'):
            dur_str += ', ' + {'treble': 'Treble clef', 'bass': 'Bass clef', 'alto': 'Alto clef'}[item['notation_clef']]
        
        pos_str = ""
        if idx is not None:
            bar_n, beat_n = self.get_bar_beat_position(idx)
            pos_str = f", Bar {bar_n} Beat {beat_n}"

        pedal_str = ", Pedal" if item.get('pedal') else ""
        return f"{' + '.join(parts)}, {dur_str}{pedal_str}{pos_str}"

    def play_item_preview(self, item):
        if 'playback_events' in item:
            events = item_playback_events(item)
            if not self.is_playing_seq:
                self._preview_generation = getattr(self, '_preview_generation', 0) + 1
            generation = getattr(self, '_preview_generation', 0)

            def play_realized():
                started = time.monotonic()
                for event in sorted(events, key=lambda e: e['offset_ms']):
                    while (time.monotonic() - started) * 1000 < event['offset_ms']:
                        if generation != getattr(self, '_preview_generation', 0):
                            return
                        time.sleep(0.005)
                    if generation != getattr(self, '_preview_generation', 0):
                        return
                    self.synth.play_notes(event['notes'], event['duration_ms'],
                                          velocity=event['velocity'], gate_ratio=1.0)
            threading.Thread(target=play_realized, daemon=True).start()
            return
        beat_ms = (60.0 / self.app.bpm) * 1000.0
        dur_ms = item.get('preview_ms', int(item['beats'] * beat_ms))
        style_idx = item.get('style_idx', self.st.lh_style_idx)
        _, pattern_data, gate_ratio = LH_STYLES[style_idx]
        if 'preview_ms' in item:
            gate_ratio = 1.0

        # 1. Play Right-Hand Melody / Chords
        if item.get('notes'):
            self.synth.play_notes(item['notes'], dur_ms, velocity=item.get("velocity", self.st.velocity), pedal=item.get('pedal', False), gate_ratio=gate_ratio)

        # 2. Play Simultaneous Left-Hand Notes / Pattern
        lh = item.get('lh_notes', [])
        if lh:
            if pattern_data != "articulation" and "drum" not in self.st.inst_type:
                self.synth.play_style_pattern(lh[0], False, dur_ms, style_idx, pedal=item.get('pedal', False))
            else:
                self.synth.play_notes(lh, dur_ms, velocity=item.get("velocity", 90), pedal=item.get('pedal', False), gate_ratio=gate_ratio)

        # 3. Play Simultaneous Section Chord if assigned
        if item.get('chord_tag') and "drum" not in self.st.inst_type:
            root_m, c_notes = parse_chord_symbol(item['chord_tag'], self.st.oct_left)
            if root_m is not None:
                is_min = "m" in item['chord_tag'] and "maj" not in item['chord_tag'].lower()
                if pattern_data != "articulation":
                    self.synth.play_style_pattern(root_m, is_min, dur_ms, style_idx, pedal=True)
                else:
                    self.synth.play_notes(c_notes, dur_ms, velocity=item.get("velocity", 85), pedal=item.get('pedal', False), gate_ratio=gate_ratio)

    def speak_current(self):
        if self.st.cursor >= len(self.st.items):
            bar_n, beat_n = self.get_bar_beat_position(len(self.st.items))
            self.announce(f"Virtual rest, end of score, Bar {bar_n} Beat {beat_n}")
            return
        item = self.st.items[self.st.cursor]
        selected_notes = self.clef_notes(item)
        if not selected_notes and item.get('rest_clef') != self.st.active_clef:
            self.announce('No notes in this clef')
            return
        item = dict(item, notes=selected_notes, lh_notes=[])
        if item.get('notes'):
            self.st.last_preview_midi = item['notes'][-1]
        elif item.get('lh_notes'):
            self.st.last_preview_midi = item['lh_notes'][-1]
        self.play_item_preview(item)
        text = self.format_item_speech(item, self.st.cursor)
        if item.get('voice_id') is not None:
            text = f"{item.get('staff_name', self.st.active_clef)}, voice {item['voice_id']}. {text}"
        self.announce(text)

    def get_item_time_ms(self, idx):
        if idx < len(self.st.items) and 'start_ms' in self.st.items[idx]:
            return self.st.items[idx]['start_ms']
        if self.st.items and all('start_ms' in it for it in self.st.items):
            return max(it['start_ms'] + it['preview_ms'] for it in self.st.items)
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
        self._vertical_context = None
        selected_lane = getattr(self.st, 'active_lane', None)
        if selected_lane is not None:
            from score_navigation import lane
            candidates = [i for i, it in enumerate(self.st.items) if lane(it) == tuple(selected_lane)]
            if candidates:
                self.st.cursor = next((i for i in candidates
                                       if self.get_item_time_ms(i) >= target_ms - 5), candidates[-1])
                self.speak_current()
            return
        
        acc = 0.0
        new_idx = len(self.st.items) - 1
        for i, it in enumerate(self.st.items):
            onset = it.get('start_ms', acc)
            if onset >= target_ms - 5:
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
        if all('score_position' in it for it in self.st.items):
            from score_navigation import lane
            self._vertical_context = None
            selected_lane = getattr(self.st, 'active_lane', None)
            candidates = [i for i, it in enumerate(self.st.items)
                          if it['score_position'][0] >= target_bar
                          and (selected_lane is None or lane(it) == tuple(selected_lane))
                          and (self.clef_notes(it) or it.get('rest_clef') == self.st.active_clef)]
            if candidates:
                self.st.cursor = candidates[0]
                self.speak_current()
            else:
                self.announce('Bar not found in this staff')
            return
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
                'clef': self.st.active_clef,
                'notes': [] if self.st.active_clef == 'bass' else notes_list,
                'lh_notes': notes_list if self.st.active_clef == 'bass' else [],
                'beats': b_val,
                'dur_name': dur_label,
                'pedal': self.st.pedal,
                'triplet': False,
                'dotted': False,
                'style_idx': self.st.lh_style_idx,
                'chord_tag': None
            }
            self.insert_item(new_it)
            added += 1

        self.announce(f"Inserted {added} steps.")

    def adjust_pitch(self, semitones):
        """Adjust only the next note, without changing existing score notes."""
        self.st.input_pitch_offset = max(-127, min(127, self.st.input_pitch_offset + semitones))
        self.announce(f"Next note {self.st.input_pitch_offset:+d} semitones; then return to key")

    def input_note_pitch(self, letter, octave):
        tonic = getattr(self.st, 'key_tonic', 'C')
        mode = getattr(self.st, 'key_mode', 'Major')
        intervals = {'Major': [0, 2, 4, 5, 7, 9, 11],
                     'Minor': [0, 2, 3, 5, 7, 8, 10],
                     '7 (Mixolydian)': [0, 2, 4, 5, 7, 9, 10]}[mode]
        letters = 'cdefgab'
        degree = (letters.index(letter) - letters.index(tonic[0].lower())) % 7
        root = NOTE_BASE[tonic[0].lower()] + (1 if '#' in tonic else -1 if 'b' in tonic else 0)
        target = (root + intervals[degree]) % 12
        accidental = (target - NOTE_BASE[letter] + 6) % 12 - 6
        pitch = 12 + octave * 12 + NOTE_BASE[letter] + accidental + self.st.input_pitch_offset
        self.st.input_pitch_offset = 0
        return max(0, min(127, pitch))

    def open_key_menu(self):
        def choose(title, options):
            chooser = menu.menu()
            chooser.init(self.w, title)
            for option in options:
                chooser.append(option)
            chooser.open()
            while True:
                self.w.frameUpdate()
                selected = chooser.frameUpdate()
                if selected is None: continue
                return None if selected == -1 else options[selected]
        tonic = choose("Key tonic", ['C', 'C#', 'Db', 'D', 'Eb', 'E', 'F', 'F#', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B'])
        if tonic is None: return False
        mode = choose("Key type", ['Major', 'Minor', '7 (Mixolydian)'])
        if mode is None: return False
        self.st.key_tonic, self.st.key_mode = tonic, mode
        self.st.input_pitch_offset = 0
        self.announce(f"Key {tonic} {mode}")
        return True

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

    def open_rhythm_menu(self):
        signatures = [(2, 4), (3, 4), (4, 4), (6, 4), (2, 8), (3, 8), (6, 8)]
        chooser = menu.menu()
        chooser.init(self.w, "Time signature and tempo (quarter-note BPM)")
        for numerator, denominator in signatures:
            chooser.append(f"{numerator}/{denominator}")
        chooser.open()
        while True:
            self.w.frameUpdate()
            selected = chooser.frameUpdate()
            if selected is None: continue
            if selected == -1: return False
            numerator, denominator = signatures[selected]
            answer = kbt(None, "Tempo", "Quarter-note BPM (20 to 400):", str(self.app.bpm))
            if answer is None or not answer.strip(): return False
            try:
                bpm = float(answer)
                if not 20 <= bpm <= 400: raise ValueError
            except ValueError:
                self.announce("BPM must be a number from 20 to 400")
                continue
            if not self.open_key_menu(): return False
            self.app.bpm = bpm
            self.app.time_sig_numerator = numerator
            self.app.time_sig_denominator = denominator
            self.app.time_sig = numerator * 4 / denominator
            self.announce(f"Time signature {numerator}/{denominator}, {bpm:g} quarter-note BPM")
            return True

    def open_dynamics_menu(self):
        options = [('ppp', 16), ('pp', 33), ('p', 49), ('mp', 64),
                   ('mf', 80), ('f', 96), ('ff', 112), ('fff', 127)]
        chooser = menu.menu()
        chooser.init(self.w, "Dynamics")
        for name, velocity in options:
            chooser.append(f"{name}, velocity {velocity}")
        chooser.open()
        while True:
            self.w.frameUpdate()
            selected = chooser.frameUpdate()
            if selected is None: continue
            if selected == -1: return
            name, velocity = options[selected]
            self.st.velocity = velocity
            if not self.st.lock_writing:
                start = end = self.st.cursor
                if self.st.sel_start is not None and self.st.sel_end is not None:
                    start, end = sorted((self.st.sel_start, self.st.sel_end))
                for item in self.st.items[max(0, start):end + 1]:
                    item['velocity'] = velocity
                    for event in item.get('playback_events', []):
                        event['velocity'] = velocity
            self.announce(f"Dynamics {name}, velocity {velocity}")
            return

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
            target_idx = self.st.cursor
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
            if 'start_ms' in it:
                for event in item_playback_events(it):
                    for n_m in event['notes']:
                        onset = round(it['start_ms'] + event['offset_ms'])
                        tokens.append(f"{midi_str(n_m)}@{onset}-{round(event['duration_ms'])}-{event['velocity']}")
                continue
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
                        sub_vel = max(1, min(127, int(it.get("velocity", 90) * v_scale)))
                        for off in offsets:
                            n_m = max(0, min(127, root_m + off))
                            tokens.append(f"{midi_str(n_m)}@{start_t}-{actual_dur}-{sub_vel}")
                        sub_offset += sub_dur
                else:
                    actual_dur = max(25, int(step_dur_ms * gate_default * pedal_mult))
                    start_t = int(round(current_ms))
                    for n_m in lh_notes:
                        tokens.append(f"{midi_str(n_m)}@{start_t}-{actual_dur}-{it.get('velocity', 90)}")

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
                            sub_vel = max(1, min(127, int(it.get("velocity", 85) * v_scale)))
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
                            tokens.append(f"{midi_str(n_m)}@{start_t}-{actual_dur}-{it.get('velocity', 85)}")

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
        self._preview_generation = getattr(self, '_preview_generation', 0) + 1
        if self.is_playing_seq:
            self.is_playing_seq = False
            bar_n, beat_n = self.get_bar_beat_position(self.st.cursor)
            self.announce(f"Stopped at Bar {bar_n} Beat {beat_n}")
            return
        if not self.st.items:
            self.announce("Empty")
            return

        if self.st.cursor >= len(self.st.items):
            self.announce("End. Move to a note to play.")
            return
        beat_ms = (60.0 / self.app.bpm) * 1000.0
        timeline = []
        next_ms = 0
        for i, it in enumerate(self.st.items):
            onset = it.get('start_ms', next_ms)
            duration = it.get('preview_ms', it['beats'] * beat_ms)
            if 'playback_events' in it:
                duration = max([duration] + [e['offset_ms'] + e['duration_ms'] for e in item_playback_events(it)])
            timeline.append((i, onset, duration, dict(it)))
            next_ms = onset + duration
        origin_ms = timeline[self.st.cursor][1]
        # Include every clef at this time, plus the remaining portion of
        # notes already sounding when playback starts in the middle.
        scheduled = []
        for i, onset, duration, item in timeline:
            if onset + duration <= origin_ms and onset < origin_ms:
                continue
            if onset < origin_ms:
                duration -= origin_ms - onset
                item['preview_ms'] = duration
                if 'playback_events' in item:
                    elapsed = origin_ms - onset
                    item['playback_events'] = [dict(e, offset_ms=max(0, e['offset_ms'] - elapsed),
                        duration_ms=e['duration_ms'] - max(0, elapsed - e['offset_ms']))
                        for e in item_playback_events(item)
                        if e['offset_ms'] + e['duration_ms'] > elapsed]
                    item['notation_beats'] = item['beats']
                    item['notation_notes'] = item.get('notes', []) + item.get('lh_notes', [])
            scheduled.append((i, max(0, onset - origin_ms), duration, item))
        self.is_playing_seq = True
        self.announce("Playing")

        def _seq_player():
            started = time.monotonic()
            end_ms = 0
            for i, onset, dur_ms, it in scheduled:
                while self.is_playing_seq and (time.monotonic() - started) * 1000 < onset:
                    time.sleep(0.005)
                if not self.is_playing_seq:
                    break
                if timeline[i][1] >= origin_ms:
                    self.st.cursor = i
                self.play_item_preview(it)
                end_ms = max(end_ms, onset + dur_ms)
            while self.is_playing_seq and (time.monotonic() - started) * 1000 < end_ms:
                time.sleep(0.005)
            self.is_playing_seq = False

        threading.Thread(target=_seq_player, daemon=True).start()

    def run(self):
        self.announce(
            f"Import Mode: {self.track.name} ({self.st.inst_type.title()}). "
            f"Right octave {self.st.oct_right}, Left {self.st.oct_left}. "
            "Alt+Up/Down: read and play chord notes, voices and staves at this beat. "
            "Alt+K: add/select clef. Left/Right: notes in selected voice. "
            "Ctrl+Alt+Up/Down: read and play individual chord notes. "
            "Shift+Note attaches simultaneous Left Hand. Press H for Bar Chords, I for Quick Phrase."
        )

        self.speak_current()
        while True:
            self.w.frameUpdate()
            if self.w.keyPressed("exit"):
                self.is_playing_seq = False
                self._preview_generation = getattr(self, '_preview_generation', 0) + 1
                self.synth.close()
                self.announce("Exited Import Mode")
                break

            ctrl = self.w.keyPressing("lcontrol") or self.w.keyPressing("rcontrol")
            shift = self.w.keyPressing("lshift") or self.w.keyPressing("rshift")
            alt = self.w.keyPressing("lalt") or self.w.keyPressing("ralt")
            if ctrl and alt and (self.w.keyPressed('up') or self.w.keyPressed('down')):
                self.read_chord_note(1 if self.w.keyPressed('up') else -1)
                continue
            if alt and self.w.keyPressed('k'):
                self.add_clef()
                continue
            if alt and (self.w.keyPressed('up') or self.w.keyPressed('down')):
                self.navigate_vertical(-1 if self.w.keyPressed('up') else 1)
                continue

            # System & Editing shortcuts: Ctrl+S, Ctrl+A, Ctrl+Q, Ctrl+E, Ctrl+C, Ctrl+X, Ctrl+V, Ctrl+D
            if ctrl and self.w.keyPressed("s"): self.app.save_project(); continue
            if ctrl and self.w.keyPressed("r"): self.save_to_track(); continue
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
            if not ctrl and not alt and self.w.keyPressed("-"):
                self.st.sel_start = self.st.cursor
                bar_n, beat_n = self.get_bar_beat_position(self.st.cursor)
                self.announce(f"Start marker: Step {self.st.cursor + 1} (Bar {bar_n} Beat {beat_n})")
                continue
            if not ctrl and not alt and self.w.keyPressed("="):
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

            if alt and self.w.keyPressed("d") and not ctrl:
                self.open_dynamics_menu()
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
                target_idx = self.st.cursor
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

            # At the virtual rest, erase the preceding note for replacement.
            if self.w.keyPressed("backspace") or self.w.keyPressed("delete"):
                self.delete_current()
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

            # Duration edits apply to the cursor note; at End they configure input.
            for d_key, duration in DURATION_MAP.items():
                if self.w.keyPressed(d_key) and not ctrl and not shift:
                    self.change_duration(duration=duration)
                    self.announce(duration[1])
                    break

            if self.w.keyPressed("7") and not ctrl:
                self.change_duration(toggle='triplet')
                self.speak_current()
                continue

            if self.w.keyPressed("8") and not ctrl:
                self.change_duration(toggle='dotted')
                self.speak_current()
                continue

            # Key 0: Insert Rest
            if self.w.keyPressed("0") and not ctrl:
                if not self.st.lock_writing:
                    rest_item = {
                        'notes': [], 'lh_notes': [], 'rest_clef': self.st.active_clef,
                        'beats': self.get_effective_beats(),
                        'dur_name': self.st.current_dur_name,
                        'pedal': False, 'triplet': self.st.is_triplet, 'dotted': self.st.is_dotted,
                        'style_idx': self.st.lh_style_idx, 'chord_tag': None
                    }
                    self.insert_item(rest_item)
                    bar_n, beat_n = self.get_bar_beat_position(self.st.cursor - 1)
                    self.announce(f"Rest, {self.st.current_dur_name}, Bar {bar_n} Beat {beat_n}")
                else:
                    self.announce(f"Rest, {self.st.current_dur_name}")
                continue

            # Note input: C, D, E, F, G, A, B
            for n_char, semi in NOTE_BASE.items():
                if self.w.keyPressed(n_char) and not ctrl:
                    hand = 'L' if shift or self.st.active_clef == 'bass' else 'R'
                    octv = self.st.oct_left if hand == 'L' else self.st.oct_right

                    midi_val = self.input_note_pitch(n_char, octv)
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
                        if (hand == 'L' and self.st.shift_attaches_lh and self.st.items
                                and self.st.active_clef not in self.st.items[min(self.st.cursor, len(self.st.items) - 1)].get('deleted_clefs', [])):
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
                        elif ((self.st.chord_mode or alt) and self.st.items
                              and self.st.active_clef not in self.st.items[min(self.st.cursor, len(self.st.items) - 1)].get('deleted_clefs', [])
                              and self.st.items[min(self.st.cursor, len(self.st.items) - 1)].get('clef', 'treble') == self.st.active_clef):
                            target_idx = self.st.cursor - 1 if self.st.cursor >= len(self.st.items) else self.st.cursor
                            target = self.st.items[target_idx]
                            if midi_val not in target['notes']:
                                target['notes'].append(midi_val)
                                target['notes'].sort()
                            self.play_item_preview(target)
                            self.announce(self.format_item_speech(target, target_idx))
                        else:
                            new_item = {
                                'clef': self.st.active_clef,
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
                            new_item = self.insert_item(new_item)
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
                    self.navigate_clef(direction)
                continue

            # One-shot next-note adjustment; Shift changes by an octave.
            if self.w.keyPressed("up") or self.w.keyPressed("down"):
                direction = 1 if self.w.keyPressed("up") else -1
                semitone_step = 12 if shift else 1
                self.adjust_pitch(direction * semitone_step)
                continue
