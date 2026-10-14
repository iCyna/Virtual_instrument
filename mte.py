import os
import sys
import time
import re
import threading

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import mido
    HAS_MIDO = True
except ImportError:
    HAS_MIDO = False

import core
from pyaudiogaming import menu
from pyaudiogaming.inputBox import kbt
from pyaudiogaming.sound_pool import playsingle
from pyaudiogaming.sound_lib.instrument import MIDIStream

SAMPLE_RATE = 44100
CHANNELS = 2
SAMPLE_WIDTH = 2
BYTES_PER_FRAME = CHANNELS * SAMPLE_WIDTH

font_load_lock = threading.Lock()

def ms_to_bytes(ms):
    return int((float(ms) * SAMPLE_RATE) / 1000.0) * BYTES_PER_FRAME

def bytes_to_ms(byte_count):
    return int(((byte_count // BYTES_PER_FRAME) * 1000.0) / SAMPLE_RATE)

def format_time(ms):
    secs = ms / 1000.0
    return f"{int(secs // 60):02d}:{secs % 60:05.2f}"

def get_clipboard_text():
    try:
        import pyperclip
        return pyperclip.paste()
    except ImportError:
        try:
            import tkinter as tk
            r = tk.Tk()
            r.withdraw()
            text = r.clipboard_get()
            r.update()
            r.destroy()
            return text
        except Exception:
            return ""

def set_clipboard_text(text):
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except ImportError:
        try:
            import tkinter as tk
            r = tk.Tk()
            r.withdraw()
            r.clipboard_clear()
            r.clipboard_append(text)
            r.update()
            r.destroy()
            return True
        except Exception:
            return False

def mix_pcm_buffers(base_data, overlay_data, offset_bytes=0, overlay_volume=1.0):
    if not overlay_data: return
    
    valid_len = len(overlay_data) - (len(overlay_data) % BYTES_PER_FRAME)
    if valid_len <= 0: return
    
    overlay_frozen = bytes(overlay_data[:valid_len])
    offset_bytes -= (offset_bytes % BYTES_PER_FRAME)

    req_len = max(len(base_data), offset_bytes + valid_len)
    if len(base_data) < req_len:
        base_data.extend(b"\x00" * (req_len - len(base_data)))

    if HAS_NUMPY:
        try:
            base_frozen = bytes(base_data[offset_bytes : offset_bytes + valid_len])
            base_view = np.frombuffer(base_frozen, dtype=np.int16)
            ov_view = np.frombuffer(overlay_frozen, dtype=np.int16)
            
            mixed = base_view.astype(np.int32) + (ov_view.astype(np.float32) * overlay_volume).astype(np.int32)
            np.clip(mixed, -32768, 32767, out=mixed)
            base_data[offset_bytes : offset_bytes + valid_len] = mixed.astype(np.int16).tobytes()
            return
        except Exception:
            pass

    import array
    base_arr = array.array('h', base_data[offset_bytes : offset_bytes + valid_len])
    ov_arr = array.array('h', overlay_frozen)
    for i in range(len(ov_arr)):
        val = base_arr[i] + int(ov_arr[i] * overlay_volume)
        base_arr[i] = max(-32768, min(32767, val))
    base_data[offset_bytes : offset_bytes + valid_len] = base_arr.tobytes()

def parse_single_note(note_str, inst_type):
    note_str = note_str.strip().upper()
    if "drum" in inst_type:
        return int(note_str) if note_str.isdigit() else -1
        
    match = re.match(r"([A-G][#B]?)(\d)", note_str)
    if match:
        note_name, octave = match.group(1), int(match.group(2))
        note_map = {
            'C': 0, 'C#': 1, 'DB': 1, 'D': 2, 'D#': 3, 'EB': 3, 
            'E': 4, 'F': 5, 'F#': 6, 'GB': 6, 'G': 7, 'G#': 8, 
            'AB': 8, 'A': 9, 'A#': 10, 'BB': 10, 'B': 11
        }
        return 12 + (octave * 12) + note_map.get(note_name, 0)
    return -1

def parse_sequence_to_events(seq_str, inst_type, bpm):
    beat_ms = int((60.0 / bpm) * 1000)
    events = []
    current_time = 0
    max_time = 0
    tokens = seq_str.strip().upper().split()
    if not tokens:
        return None, 0
    
    for token in tokens:
        start_offset_ms = None
        is_absolute_ms = False
        
        if '@' in token:
            token_parts = token.split('@')
            pitch_str = token_parts[0]
            rest_parts = token_parts[1].split('-')
            
            start_offset_ms = int(float(rest_parts[0])) 
            is_absolute_ms = True
            parts = [pitch_str] + rest_parts[1:]
        else:
            parts = token.split("-")
            pitch_str = parts[0]

        if is_absolute_ms:
            try: dur_ms = int(float(parts[1])) if len(parts) > 1 else 500
            except ValueError: dur_ms = 500
        else:
            try: dur_beats = float(parts[1]) if len(parts) > 1 else 1.0
            except ValueError: dur_beats = 1.0
            dur_ms = int(dur_beats * beat_ms)

        try: velocity = int(parts[2]) if len(parts) > 2 else 100
        except ValueError: velocity = 100
        velocity = max(0, min(127, velocity))

        if pitch_str == 'R':
            if start_offset_ms is not None:
                current_time = start_offset_ms + dur_ms
            else:
                current_time += dur_ms
            max_time = max(max_time, current_time)
            continue

        is_down_strum = pitch_str.startswith('~[')
        is_up_strum = pitch_str.startswith('^[')
        if is_down_strum or is_up_strum: 
            pitch_str = pitch_str[1:] 

        if pitch_str.startswith('[') and pitch_str.endswith(']'):
            midi_notes = [parse_single_note(n, inst_type) for n in pitch_str[1:-1].split(',')] 
        else:
            midi_notes = [parse_single_note(pitch_str, inst_type)]
            
        strum_delay = 20 if (is_down_strum or is_up_strum) else 0
        if is_up_strum: 
            midi_notes.reverse() 

        note_start_time = start_offset_ms if start_offset_ms is not None else current_time

        for i, n in enumerate(midi_notes):
            if n != -1:
                on_time = note_start_time + (i * strum_delay)
                off_time = max(on_time + 10, note_start_time + dur_ms)
                events.extend([
                    (on_time, 'on', n, velocity),
                    (off_time, 'off', n, 0)
                ])
                max_time = max(max_time, off_time)
        
        if start_offset_ms is None:
            current_time += dur_ms
        else:
            current_time = max_time

    if not events:
        return None, 0
        
    events.sort(key=lambda x: x[0])
    return events, max_time


class BackgroundMixerTask(threading.Thread):
    def __init__(self, app, track, offset_bytes, events, total_time_ms, inst_type):
        super().__init__()
        self.app = app
        self.track = track
        self.offset_bytes = offset_bytes
        self.events = events
        self.total_time_ms = total_time_ms
        self.inst_type = inst_type
        self.daemon = True

    def run(self):
        try:
            inst_config = core.config["instruments"].get(self.inst_type)
            if not inst_config:
                return

            is_vst = (inst_config["active_engine"] == "vst" and bool(inst_config["vst_path"]) and os.path.exists(inst_config["vst_path"]))
            chan = 9 if "drum" in self.inst_type else 0

            if is_vst:
                from pyaudiogaming.sound_pool import vst
                inst = vst()
                success = inst.create_instrument(inst_config["vst_path"], frequency=SAMPLE_RATE, flags=0x200000)
                if not success:
                    self.app.announce("Error: Cannot load VST. Ensure DLL is architecture compatible.")
                    return
                if inst_config.get("vst_chunk"):
                    inst.set_chunk(inst_config["vst_chunk"])
            else:
                from pyaudiogaming.sound_pool import musical
                inst = musical()
                inst.handle = MIDIStream(channels=16, decode=True)
                inst.freq = SAMPLE_RATE
                sf2_path = inst_config.get("sf2_path", "")
                if sf2_path and os.path.exists(sf2_path):
                    with font_load_lock:
                        loaded_font = inst.load_font(sf2_path)
                    inst.set_fonts(loaded_font)
                program_id = inst_config.get("sf2_id", 0)
                inst.send_event(chan, 2, int(program_id))

            event_idx = 0
            num_events = len(self.events)
            
            total_bytes = ms_to_bytes(self.total_time_ms)
            total_bytes -= (total_bytes % BYTES_PER_FRAME)
            
            current_bytes = 0
            CHUNK_BYTES = ms_to_bytes(100)
            
            while current_bytes < total_bytes:
                while event_idx < num_events:
                    ev_bytes = ms_to_bytes(self.events[event_idx][0])
                    if ev_bytes <= current_bytes:
                        ev = self.events[event_idx]
                        param = ev[2] | (ev[3] << 8) if ev[1] == "on" else ev[2] | (0 << 8)
                        if is_vst: inst.send_midi(chan, 1, param)
                        else: inst.send_event(chan, 1, param)
                        event_idx += 1
                    else:
                        break
                        
                req = min(CHUNK_BYTES, total_bytes - current_bytes)
                if event_idx < num_events:
                    next_ev_bytes = ms_to_bytes(self.events[event_idx][0])
                    if next_ev_bytes < current_bytes + req:
                        req = next_ev_bytes - current_bytes
                        
                if req > 0:
                    raw = inst.get_data(frame_size=req // 2, data_type="raw")
                    raw_len = len(raw) if raw is not None else 0
                    if raw_len > 0:
                        mix_pcm_buffers(self.track.pcm, raw, self.offset_bytes + current_bytes, 1.0)
                        current_bytes += raw_len
                    else:
                        current_bytes += req
                        
                if self.app.is_playing:
                    play_pos_ms = self.app.cursor_ms
                    if self.app.preview:
                        try: play_pos_ms = self.app.play_start_pos + self.app.preview.position
                        except Exception: pass
                        
                    render_pos_global_ms = bytes_to_ms(self.offset_bytes + current_bytes)
                    dist = play_pos_ms - render_pos_global_ms
                    
                    if dist > 0: time.sleep(0)
                    elif dist > -1500: time.sleep(0.002)
                    else: time.sleep(0.02)
                else:
                    time.sleep(0.015)
                    
            inst.close()
            try:
                from pyaudiogaming import buffer
                if inst.sound_token in buffer.hSound_poolbuffers:
                    del buffer.hSound_poolbuffers[inst.sound_token]
            except Exception:
                pass
            
        except Exception as e:
            print(f"Background render error: {e}")


class Track:
    def __init__(self, name="Track 1"):
        self.name = name
        self.pcm = bytearray()
        self.volume = 100
        self.pan = 0
        self.muted = False
        self.solo = False
        self.import_state = None

    def get_length_ms(self):
        return bytes_to_ms(len(self.pcm))


from mte_playermode import PlayerModeMixin

class MusicTrackerEditor(PlayerModeMixin):
    def __init__(self):
        self.w = core.getW()
        self.tracks = [Track("Track 1")]
        self.active_track_idx = 0
        self.cursor_ms = 0
        self.marker_start_ms = 0
        self.marker_end_ms = 0
        self.clipboard = bytearray()
        self.undo_stack, self.redo_stack = [], []
        
        self.bpm = 120
        self.time_sig = 4
        self.seek_modes = ["10 ms", "100 ms", "1 sec", "1 Beat", "1 Bar"]
        self.seek_mode_idx = 1
        
        self.preview = None
        self.is_playing = False
        self.play_clock = 0.0
        self.play_start_pos = 0
        self.play_is_solo = False

    @property
    def current_track(self):
        return self.tracks[self.active_track_idx]

    def announce(self, text):
        self.w.say(text)

    def open_instrument_studio(self):
        m = menu.menu()
        m.init(self.w, "Arranger & Instrument Studio")
        m.append("Advanced Step Sequencer (Notes/Chords)")
        m.append("Metronome Beat Generator")
        m.append("Extract MIDI to Sequence Text (.mid)")
        m.append("Launch Live MIDI Instruments")
        m.append("Back")
        m.open()

        while True:
            self.w.frameUpdate()
            sel = m.frameUpdate()
            if sel is None: continue
            if sel == -1 or sel == 4: break
            if sel == 0: self.open_step_sequencer(); break
            elif sel == 1: self.arrange_metronome(); break
            elif sel == 2: self.extract_midi_to_string(); break
            elif sel == 3: self.launch_live_midi_instruments(); break

    def open_step_sequencer(self):
        m = menu.menu()
        m.init(self.w, "Select Instrument")
        
        display_names = ["Piano", "Guitar", "Bass", "Strings", "Synth", "Flute", "Drums", "Electronic Drums"]
        for inst in display_names:
            m.append(inst)
        m.append("Back")
        m.open()
        
        while True:
            self.w.frameUpdate()
            sel = m.frameUpdate()
            if sel is None: continue
            if sel == -1 or sel == len(display_names): return
            
            inst_keys = ["piano", "guitar", "bass", "strings", "synth", "flute", "drum", "electronic drum"]
            self.choose_note_input_method(inst_keys[sel])
            break

    def choose_note_input_method(self, inst_type):
        m = menu.menu()
        m.init(self.w, f"{inst_type.title()} - Input Method")
        m.append("Manual Text Input (Normal)")
        m.append("Load from Text File (.txt)")
        m.append("Import Mode (Interactive Key Editor - Press P in MTE)")
        m.append("Back")
        m.open()

        while True:
            self.w.frameUpdate()
            sel = m.frameUpdate()
            if sel is None: continue
            if sel == -1 or sel == 3: break

            if sel == 0:
                self.run_step_sequencer(inst_type, from_file=False)
                break
            elif sel == 1:
                self.run_step_sequencer(inst_type, from_file=True)
                break
            elif sel == 2:
                from mte_importmode import ImportModeState
                if self.current_track.import_state is None:
                    self.current_track.import_state = ImportModeState(inst_type)
                else:
                    self.current_track.import_state.inst_type = inst_type
                self.announce(f"Import Mode set to {inst_type.title()} for {self.current_track.name}. Press P to open.")
                break

    def open_import_mode(self):
        from mte_importmode import ImportModeEditor, ImportModeState
        if self.current_track.import_state is None:
            self.current_track.import_state = ImportModeState("piano")
        self.stop_play()
        editor = ImportModeEditor(self, self.current_track)
        editor.run()

    def run_step_sequencer(self, inst_type, from_file=False):
        if from_file:
            filepath = kbt(None, "Load Sequence File", "Enter path or choose .txt file:", "", file_dialog=True)
            if not filepath or not os.path.exists(filepath):
                self.announce("File not found.")
                return
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    seq_str = f.read()
                self.announce(f"Loaded {os.path.basename(filepath)}")
            except Exception:
                self.announce("Error reading file.")
                return
        else:
            msg = "Type '*clip' to paste from clipboard.\n"
            msg += "Strumming: ~[C3,E3] (down), ^[C3,E3] (up)\n" if inst_type == "guitar" else ""
            msg += ("Syntax: Note-Beat-Velocity (e.g., Eb4-1-120 [E4,G4,C5]-0.5 R-1):" 
                    if "drum" not in inst_type else 
                    "Drum Syntax: Code-Beat-Velocity (e.g., 36-1-127 38-1-50 [36,42]-0.5):")
                   
            seq_str = kbt(None, f"{inst_type.title()} Sequencer", msg, "")
            if not seq_str: return

            if seq_str.strip().lower() == "*clip":
                clip_data = get_clipboard_text()
                if not clip_data:
                    self.announce("Clipboard is empty or inaccessible.")
                    return
                seq_str = clip_data
                self.announce("Loaded sequence from clipboard.")

        seq_str = seq_str.replace('\n', ' ').replace('\r', ' ')
        self.announce("Parsing sequence...")
        
        events, seq_time = parse_sequence_to_events(seq_str, inst_type, self.bpm)
        if not events:
            self.announce("No valid notes found.")
            return
            
        total_time_ms = seq_time + 500
        self.save_state()
        
        total_bytes = ms_to_bytes(total_time_ms)
        total_bytes -= (total_bytes % BYTES_PER_FRAME)
        if total_bytes <= 0: total_bytes = BYTES_PER_FRAME
        
        offset_bytes = ms_to_bytes(self.cursor_ms)
        req_len = offset_bytes + total_bytes
        if len(self.current_track.pcm) < req_len:
            self.current_track.pcm.extend(b"\x00" * (req_len - len(self.current_track.pcm)))
            
        task = BackgroundMixerTask(self, self.current_track, offset_bytes, events, total_time_ms, inst_type)
        task.start()
        
        self.announce("Sequence rendering in background. You can play or seek immediately.")
        self.cursor_ms = 0

    def arrange_metronome(self):
        bars_str = kbt(None, "Metronome Track", "Enter number of bars:", "4")
        if not bars_str or not bars_str.strip().isdigit(): return
        bars = int(bars_str.strip())
        beat_ms = int((60.0 / self.bpm) * 1000)

        events = []
        for bar in range(bars):
            for beat in range(self.time_sig):
                t = (bar * self.time_sig + beat) * beat_ms
                note = 76 if beat == 0 else 77
                events.extend([(t, 'on', note, 110), (t + 100, 'off', note, 0)])

        total_time_ms = bars * self.time_sig * beat_ms + 500

        self.save_state()
        self.announce("Generating metronome track...")
        
        metro = Track(f"Metronome {self.bpm}")
        total_bytes = ms_to_bytes(total_time_ms)
        total_bytes -= (total_bytes % BYTES_PER_FRAME)
        if total_bytes <= 0: total_bytes = BYTES_PER_FRAME
        metro.pcm = bytearray(total_bytes)
        
        self.tracks.append(metro)
        self.active_track_idx = len(self.tracks) - 1
        self.cursor_ms = 0
        
        task = BackgroundMixerTask(self, metro, 0, events, total_time_ms, "drum")
        task.start()
        
        self.announce(f"{metro.name} generated. Rendering in background.")

    def launch_live_midi_instruments(self):
        inst_list = [k for k in core.menus.keys() if k != "Music Tracker Editor"]
        m = menu.menu()
        m.init(self.w, "Live Instruments")
        for k in inst_list: m.append(k)
        m.append("Back")
        m.open()

        while True:
            self.w.frameUpdate()
            sel = m.frameUpdate()
            if sel is None: continue
            if sel == -1 or sel == len(inst_list): break
            self.announce(f"Opening {inst_list[sel]}")
            if hasattr(core.menus[inst_list[sel]], "run"): core.menus[inst_list[sel]].run()
            self.announce("Back to Tracker")
            break

    def extract_midi_to_string(self):
        if not HAS_MIDO:
            self.announce("Missing library. Please install: pip install mido")
            return
            
        filepath = kbt(None, "Select MIDI File", "Choose a .mid file:", "", file_dialog=True)
        if not filepath or not os.path.exists(filepath):
            return

        m = menu.menu()
        m.init(self.w, "Select Target Format")
        m.append("Pitched Instruments (Piano/Guitar/Bass/Strings/Synth...)")
        m.append("Drums / Electronic Drums")
        m.append("Cancel")
        m.open()
        
        inst_choice = None
        while True:
            self.w.frameUpdate()
            sel = m.frameUpdate()
            if sel is None: continue
            if sel == -1 or sel == 2: return
            inst_choice = "drum" if sel == 1 else "piano"
            break
            
        self.announce("Extracting MIDI. Tracking timing, pedal, and scaling timbre to Forte...")
        
        extraction_done = False
        extracted_seq_str = ""
        extraction_error = False
        shared_progress = 0  
      
        def extraction_worker():
            nonlocal extraction_done, extracted_seq_str, extraction_error, shared_progress
            try:
                mid = mido.MidiFile(filepath)
                notes = []
                
                active_notes = {i: {} for i in range(16)}
                pedal_held_notes = {i: [] for i in range(16)}
                current_vol = {i: 127 for i in range(16)}
                current_exp = {i: 127 for i in range(16)}
                pedal_down = {i: False for i in range(16)}
                soft_pedal_down = {i: False for i in range(16)}
                
                current_time_sec = 0.0
                total_length = mid.length if mid.length > 0 else 1.0
                
                for msg in mid:
                    current_time_sec += msg.time
                    percent = int((current_time_sec / total_length) * 100)
                    shared_progress = min(100, max(0, percent))
                    
                    if hasattr(msg, 'channel'):
                        ch = msg.channel
                        if msg.type == 'control_change':
                            if msg.control == 7: current_vol[ch] = msg.value
                            elif msg.control == 11: current_exp[ch] = msg.value
                            elif msg.control == 64:
                                if msg.value >= 64 and not pedal_down[ch]:
                                    pedal_down[ch] = True
                                elif msg.value < 64 and pedal_down[ch]:
                                    pedal_down[ch] = False
                                    for n_info in pedal_held_notes[ch]:
                                        notes.append({'start': n_info['start'], 'end': current_time_sec, 'note': n_info['note'], 'vel': n_info['vel']})
                                    pedal_held_notes[ch].clear()
                            elif msg.control == 67:
                                soft_pedal_down[ch] = msg.value >= 64
                        elif msg.type == 'note_on' and msg.velocity > 0:
                            if msg.note not in active_notes[ch]: active_notes[ch][msg.note] = []
                            soft_multiplier = 0.7 if soft_pedal_down[ch] else 1.0
                            baked_vel = msg.velocity * (current_vol[ch] / 127.0) * (current_exp[ch] / 127.0) * soft_multiplier
                            active_notes[ch][msg.note].append({'start': current_time_sec, 'vel': baked_vel, 'note': msg.note})
                        elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                            if msg.note in active_notes[ch] and len(active_notes[ch][msg.note]) > 0:
                                note_info = active_notes[ch][msg.note].pop(0)
                                if pedal_down[ch]: pedal_held_notes[ch].append(note_info)
                                else: notes.append({'start': note_info['start'], 'end': current_time_sec, 'note': note_info['note'], 'vel': note_info['vel']})
                                    
                for ch in range(16):
                    for n_info in pedal_held_notes[ch]:
                        notes.append({'start': n_info['start'], 'end': current_time_sec, 'note': n_info['note'], 'vel': n_info['vel']})
                    for note_list in active_notes[ch].values():
                        for n_info in note_list:
                            notes.append({'start': n_info['start'], 'end': current_time_sec, 'note': n_info['note'], 'vel': n_info['vel']})
                            
                notes.sort(key=lambda x: x['start'])
                NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
                def note_to_str(n, inst): return str(n) if "drum" in inst else f"{NAMES[n % 12]}{(n // 12) - 1}"
                    
                result = []
                max_v = max((n['vel'] for n in notes), default=1)
                vol_multiplier = 95.0 / max_v if max_v > 0 else 1.0
                    
                for n in notes:
                    start_ms = int(round(n['start'] * 1000))
                    dur_ms = max(10, int(round((n['end'] - n['start']) * 1000)))
                    note_str = note_to_str(n['note'], inst_choice)
                    final_vel = max(1, min(127, int(round(n['vel'] * vol_multiplier))))
                    result.append(f"{note_str}@{start_ms}-{dur_ms}-{final_vel}")
                    
                extracted_seq_str = " ".join(result)
                extraction_done = True
            except Exception as e:
                print(e)
                extraction_error = True
                extraction_done = True

        worker = threading.Thread(target=extraction_worker, daemon=True)
        worker.start()

        last_played_percent = -1
        while not extraction_done:
            self.w.frameUpdate()
            if shared_progress > last_played_percent:
                playsingle("collections/audio/progress.ogg", pitch=15 + (shared_progress * 5))
                last_played_percent = shared_progress
            time.sleep(0.01)
                   
        if extraction_error:
            self.announce("Error extracting MIDI")
            return

        seq_str = extracted_seq_str
        m2 = menu.menu()
        m2.init(self.w, "Extraction Complete")
        m2.append("Copy to Clipboard")
        m2.append("Export to collections/mte-mids")
        m2.append("Discard")
        m2.open()
        
        while True:
            self.w.frameUpdate()
            sel = m2.frameUpdate()
            if sel is None: continue
            if sel == -1 or sel == 2: break
            if sel == 0:
                success = set_clipboard_text(seq_str)
                self.announce("Copied to clipboard!" if success else "Failed to copy. Pyperclip missing.")
                break
            elif sel == 1:
                export_dir = "collections/mte-mids"
                os.makedirs(export_dir, exist_ok=True)
                base_name = os.path.basename(filepath)
                out_file = os.path.join(export_dir, os.path.splitext(base_name)[0] + ".txt")
                with open(out_file, "w", encoding="utf-8") as f: f.write(seq_str)
                self.announce(f"Exported to {out_file}")
                break

    def run(self):
        self.run_player_loop()

def run():
    app = MusicTrackerEditor()
    app.run()