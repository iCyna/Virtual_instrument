# -*- coding: utf-8 -*-
"""
Music Tracker Editor (MTE)
Integrated Audio Tracker, Sequencer & Arranger for instrument-virtual gaming toolkit
Interface Language: English
"""

import os
import sys
import struct
import json
import time
import math
import random
import tempfile
import re
import threading
import winsound

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
from pyaudiogaming.sound_pool import sound, musical
from pyaudiogaming import sound_pool
from pyaudiogaming.sound_lib.instrument import MIDIStream

# Audio PCM Standards: 44.1 kHz, 16-bit Little-Endian Stereo
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
        except Exception as e:
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
    # Mọi nhạc cụ có chữ "drum" đều được đối xử như bộ gõ (nhập số thay vì nốt nhạc)
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

# =============================================================================
# LAZY RENDERING TASK
# =============================================================================
class BackgroundMixerTask(threading.Thread):
    def __init__(self, app, track, offset_bytes, events, total_time_ms, inst_type, sf2_path):
        super().__init__()
        self.app = app
        self.track = track
        self.offset_bytes = offset_bytes
        self.events = events
        self.total_time_ms = total_time_ms
        self.inst_type = inst_type
        self.sf2_path = sf2_path
        self.daemon = True 

    def run(self):
        try:
            inst = musical()
            inst.handle = MIDIStream(channels=16, decode=True)
            inst.freq = SAMPLE_RATE
            
            if self.sf2_path and os.path.exists(self.sf2_path):
                with font_load_lock:
                    loaded_font = inst.load_font(self.sf2_path)
                inst.set_fonts(loaded_font)
            
            # Gán bộ gõ vào Channel 9
            chan = 9 if "drum" in self.inst_type else 0
            
            # Khớp quy ước đặt tên để kéo chuẩn xác ID từ core.config
            id_key = f"{self.inst_type} tools" if self.inst_type in ["guitar", "bass"] else self.inst_type
            program_id = core.config.get(id_key, 0)
            
            # Gửi lệnh đổi tiếng (Dù là trống ở kênh 9 vẫn gửi để hỗ trợ chuyển kit nếu cần)
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
                        inst.send_event(chan, 1, param)
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
                        except: pass
                        
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
            except Exception: pass
            
        except Exception as e:
            print(f"Background render error: {e}")

# =============================================================================
# Live Playback Thread
# =============================================================================
class PlaybackThread(threading.Thread):
    def __init__(self, app, all_tracks=True):
        super().__init__()
        self.app = app
        self.all_tracks = all_tracks
        self.daemon = True
        self.active = True

    def run(self):
        try:
            chunk_ms = 100
            chunk_bytes = ms_to_bytes(chunk_ms)
            
            start_byte = ms_to_bytes(self.app.cursor_ms)
            current_byte = start_byte
            
            max_len_bytes = max([len(t.pcm) for t in self.app.tracks], default=0) if self.all_tracks else len(self.app.current_track.pcm)
            
            if start_byte >= max_len_bytes:
                self.app.is_playing = False
                return
                
            self.app.preview = sound()
            self.app.preview.stream("", draw=True)
            self.app.preview.play()
            
            while self.app.is_playing and self.active and current_byte < max_len_bytes:
                mixed_chunk = bytearray(b'\x00' * chunk_bytes)
                has_solo = any(t.solo for t in self.app.tracks)
                
                tracks = self.app.tracks if self.all_tracks else [self.app.current_track]
                
                for t in tracks:
                    if self.all_tracks:
                        if has_solo and not t.solo: continue
                        if not has_solo and t.muted: continue
                        
                    t_len = len(t.pcm)
                    if current_byte < t_len:
                        end_byte = min(current_byte + chunk_bytes, t_len)
                        overlay = t.pcm[current_byte:end_byte]
                        mix_pcm_buffers(mixed_chunk, overlay, 0, t.volume / 100.0)
                        
                if not self.app.is_playing or not self.active: break
                self.app.preview.push(bytes(mixed_chunk))
                current_byte += chunk_bytes
                
                while self.app.is_playing and self.active:
                    try:
                        pos_ms = self.app.preview.position
                    except Exception: pos_ms = 0
                    
                    pushed_ms = bytes_to_ms(current_byte - start_byte)
                    if pushed_ms - pos_ms > 400: 
                        time.sleep(0.02)
                    else:
                        break
                        
            while self.app.is_playing and self.active:
                try: pos_ms = self.app.preview.position
                except Exception: pos_ms = 0
                
                pushed_ms = bytes_to_ms(current_byte - start_byte)
                if pos_ms >= pushed_ms - 50:
                    break
                time.sleep(0.05)
                
            if self.app.is_playing and self.active:
                self.app.is_playing = False
                self.app.cursor_ms = bytes_to_ms(max_len_bytes)
                self.app.announce("Track ended")
                
        except Exception as e:
            print(f"Playback error: {e}")
            self.app.is_playing = False

class Track:
    def __init__(self, name="Track 1"):
        self.name = name
        self.pcm = bytearray()
        self.volume = 100
        self.pan = 0
        self.muted = False
        self.solo = False

    def get_length_ms(self):
        return bytes_to_ms(len(self.pcm))

class MusicTrackerEditor:
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
    def current_track(self): return self.tracks[self.active_track_idx]

    def announce(self, text): self.w.say(text)

    def reset_playback(self):
        self.is_playing = False
        if hasattr(self, 'playback_thread'):
            self.playback_thread.active = False
        if self.preview:
            try:
                self.preview.stop()
                self.preview.close()
                from pyaudiogaming import buffer
                if self.preview.sound_token in buffer.hSound_poolbuffers:
                    del buffer.hSound_poolbuffers[self.preview.sound_token]
            except Exception: pass
            self.preview = None

    def save_state(self):
        self.reset_playback()
        if len(self.undo_stack) > 15: self.undo_stack.pop(0)
        state = {"active_idx": self.active_track_idx, "cursor": self.cursor_ms, "tracks": []}
        for t in self.tracks:
            nt = Track(t.name)
            nt.pcm = bytearray(t.pcm)
            nt.volume, nt.pan, nt.muted, nt.solo = t.volume, t.pan, t.muted, t.solo
            state["tracks"].append(nt)
        self.undo_stack.append(state)
        self.redo_stack.clear()

    def restore_state(self, state):
        self.active_track_idx, self.cursor_ms = state["active_idx"], state["cursor"]
        self.tracks = []
        for t in state["tracks"]:
            nt = Track(t.name)
            nt.pcm = bytearray(t.pcm)
            nt.volume, nt.pan, nt.muted, nt.solo = t.volume, t.pan, t.muted, t.solo
            self.tracks.append(nt)

    def _swap_state(self, pop_stack, push_stack, msg):
        self.reset_playback()
        if not pop_stack:
            self.announce(f"Nothing to {msg.split()[0].lower()}")
            return
        c_state = {"active_idx": self.active_track_idx, "cursor": self.cursor_ms, "tracks": []}
        for t in self.tracks:
            nt = Track(t.name)
            nt.pcm = bytearray(t.pcm)
            nt.volume, nt.pan, nt.muted, nt.solo = t.volume, t.pan, t.muted, t.solo
            c_state["tracks"].append(nt)
        push_stack.append(c_state)
        self.restore_state(pop_stack.pop())
        self.announce(msg)

    def trigger_undo(self): self._swap_state(self.undo_stack, self.redo_stack, "Undo successful")
    def trigger_redo(self): self._swap_state(self.redo_stack, self.undo_stack, "Redo successful")

    def render_mixdown(self, solo_current=False):
        if solo_current: return bytearray(self.current_track.pcm)
        max_len = max([len(t.pcm) for t in self.tracks], default=0)
        if max_len == 0: return bytearray()
        mixed = bytearray(b"\x00" * max_len)
        has_solo = any(t.solo for t in self.tracks)
        for t in self.tracks:
            if (has_solo and not t.solo) or (not has_solo and t.muted): continue
            mix_pcm_buffers(mixed, t.pcm, offset_bytes=0, overlay_volume=t.volume / 100.0)
        return mixed

    def get_max_length(self, solo_current=False):
        return self.current_track.get_length_ms() if solo_current else max([t.get_length_ms() for t in self.tracks], default=0)

    def toggle_play(self, all_tracks=True):
        if self.is_playing:
            self.stop_play()
            return
            
        self.reset_playback()
        max_len = self.get_max_length(solo_current=not all_tracks)
        if max_len == 0:
            self.announce("Empty track")
            return
            
        if self.cursor_ms >= max_len:
            self.cursor_ms = 0
            
        self.is_playing = True
        self.play_is_solo = not all_tracks
        self.play_start_pos = self.cursor_ms
        
        self.playback_thread = PlaybackThread(self, all_tracks)
        self.playback_thread.start()
        
        self.announce("Playing" if all_tracks else f"Solo {self.current_track.name}")

    def stop_play(self):
        if self.is_playing:
            if self.preview:
                try: elapsed_ms = self.preview.position
                except Exception: elapsed_ms = 0
                self.cursor_ms = min(self.get_max_length(self.play_is_solo), self.play_start_pos + elapsed_ms)
                
        self.is_playing = False
        if hasattr(self, 'playback_thread'):
            self.playback_thread.active = False
        self.reset_playback()
        self.announce("Stopped")

    def add_new_track(self):
        self.save_state()
        new_track = Track(f"Track {len(self.tracks) + 1}")
        self.tracks.append(new_track)
        self.active_track_idx = len(self.tracks) - 1
        self.cursor_ms = 0
        self.announce(f"{new_track.name} created. Cursor reset to 0.")

    def delete_track(self):
        if len(self.tracks) <= 1:
            self.announce("Cannot delete the last track.")
            return
        self.save_state()
        name = self.current_track.name
        del self.tracks[self.active_track_idx]
        self.active_track_idx = min(self.active_track_idx, len(self.tracks) - 1)
        self.cursor_ms = 0
        self.announce(f"Deleted {name}. Current: {self.current_track.name}")

    def switch_track(self, delta):
        if not self.tracks: return
        self.active_track_idx = (self.active_track_idx + delta) % len(self.tracks)
        t = self.current_track
        state = ", Muted" if t.muted else (", Solo" if t.solo else "")
        self.announce(f"{t.name}, {t.get_length_ms()} ms{state}")

    def get_selection(self):
        s, e = min(self.marker_start_ms, self.marker_end_ms), max(self.marker_start_ms, self.marker_end_ms)
        return s, e if s != e else self.current_track.get_length_ms()

    def copy_selection(self):
        s, e = self.get_selection()
        sb, eb = ms_to_bytes(s), ms_to_bytes(e)
        if sb >= len(self.current_track.pcm):
            self.announce("Empty selection")
            return
        self.clipboard = bytearray(self.current_track.pcm[sb:eb])
        self.announce(f"Copied {bytes_to_ms(len(self.clipboard))} ms")

    def cut_selection(self):
        s, e = self.get_selection()
        sb, eb = ms_to_bytes(s), ms_to_bytes(e)
        if sb >= len(self.current_track.pcm):
            self.announce("Empty selection")
            return
        self.save_state()
        self.clipboard = bytearray(self.current_track.pcm[sb:eb])
        del self.current_track.pcm[sb:eb]
        self.cursor_ms = s
        self.announce(f"Cut {bytes_to_ms(len(self.clipboard))} ms")

    def paste_clipboard(self):
        if not self.clipboard:
            self.announce("Clipboard empty")
            return
        self.save_state()
        cb = ms_to_bytes(self.cursor_ms)
        if cb > len(self.current_track.pcm):
            self.current_track.pcm.extend(b"\x00" * (cb - len(self.current_track.pcm)))
        self.current_track.pcm[cb:cb] = self.clipboard
        self.cursor_ms = 0
        self.announce("Pasted. Cursor reset to 0.")

    def mix_clipboard(self):
        if not self.clipboard:
            self.announce("Clipboard empty")
            return
        self.save_state()
        cb = ms_to_bytes(self.cursor_ms)
        mix_pcm_buffers(self.current_track.pcm, self.clipboard, offset_bytes=cb)
        self.cursor_ms = 0
        self.announce("Mixed. Cursor reset to 0.")

    def insert_silence(self):
        ans = kbt(None, "Insert Silence", "Silence duration in ms:", "100")
        if not ans: return
        try: dur = int(ans.strip())
        except ValueError: return
        if dur <= 0: return
        
        self.save_state()
        silence = b"\x00" * ms_to_bytes(dur)
        cb = ms_to_bytes(self.cursor_ms)
        if cb > len(self.current_track.pcm):
            self.current_track.pcm.extend(b"\x00" * (cb - len(self.current_track.pcm)))
        self.current_track.pcm[cb:cb] = silence
        self.cursor_ms = 0
        self.announce(f"Inserted {dur} ms. Cursor reset to 0.")

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
            
            for msg in mid:
                self.w.frameUpdate() 
                current_time_sec += msg.time 
                
                if hasattr(msg, 'channel'):
                    ch = msg.channel
                    
                    if msg.type == 'control_change':
                        if msg.control == 7:
                            current_vol[ch] = msg.value
                        elif msg.control == 11:
                            current_exp[ch] = msg.value
                        elif msg.control == 64:
                            if msg.value >= 64 and not pedal_down[ch]:
                                pedal_down[ch] = True
                            elif msg.value < 64 and pedal_down[ch]:
                                pedal_down[ch] = False
                                for n_info in pedal_held_notes[ch]:
                                    notes.append({
                                        'start': n_info['start'],
                                        'end': current_time_sec,
                                        'note': n_info['note'],
                                        'vel': n_info['vel']
                                    })
                                pedal_held_notes[ch].clear()
                        elif msg.control == 67:
                            soft_pedal_down[ch] = msg.value >= 64
                                
                    elif msg.type == 'note_on' and msg.velocity > 0:
                        if msg.note not in active_notes[ch]:
                            active_notes[ch][msg.note] = []
                            
                        soft_multiplier = 0.7 if soft_pedal_down[ch] else 1.0
                        baked_vel = msg.velocity * (current_vol[ch] / 127.0) * (current_exp[ch] / 127.0) * soft_multiplier
                        
                        active_notes[ch][msg.note].append({
                            'start': current_time_sec, 
                            'vel': baked_vel,
                            'note': msg.note
                        })
                        
                    elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                        if msg.note in active_notes[ch] and len(active_notes[ch][msg.note]) > 0:
                            note_info = active_notes[ch][msg.note].pop(0)
                            
                            if pedal_down[ch]:
                                pedal_held_notes[ch].append(note_info)
                            else:
                                notes.append({
                                    'start': note_info['start'], 
                                    'end': current_time_sec, 
                                    'note': note_info['note'], 
                                    'vel': note_info['vel']
                                })
                                
            for ch in range(16):
                for n_info in pedal_held_notes[ch]:
                    notes.append({
                        'start': n_info['start'],
                        'end': current_time_sec,
                        'note': n_info['note'],
                        'vel': n_info['vel']
                    })
                for note_list in active_notes[ch].values():
                    for n_info in note_list:
                        notes.append({
                            'start': n_info['start'],
                            'end': current_time_sec,
                            'note': n_info['note'],
                            'vel': n_info['vel']
                        })
                        
            notes.sort(key=lambda x: x['start'])
            NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
            
            def note_to_str(n, inst): 
                return str(n) if "drum" in inst else f"{NAMES[n % 12]}{(n // 12) - 1}"
                
            result = []
            
            # --- AUTO NORMALIZE TIMBRE (MAX 95 FOR FORTE) ---
            max_v = max((n['vel'] for n in notes), default=1)
            vol_multiplier = 95.0 / max_v if max_v > 0 else 1.0
                
            for n in notes:
                self.w.frameUpdate()
                
                start_ms = int(round(n['start'] * 1000))
                dur_ms = int(round((n['end'] - n['start']) * 1000))
                
                if dur_ms <= 0: dur_ms = 10
                
                note_str = note_to_str(n['note'], inst_choice)
                
                final_vel = int(round(n['vel'] * vol_multiplier))
                final_vel = max(1, min(127, final_vel))
                
                result.append(f"{note_str}@{start_ms}-{dur_ms}-{final_vel}")
                
            seq_str = " ".join(result)
            
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

        except Exception as e:
            self.announce("Error extracting MIDI")
            print(e)

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
            self.run_step_sequencer(inst_keys[sel])
            break

    def run_step_sequencer(self, inst_type):
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
        sf2_path = core.config.get(f"{inst_type} musical toolkit", "")
        
        self.save_state()
        
        total_bytes = ms_to_bytes(total_time_ms)
        total_bytes -= (total_bytes % BYTES_PER_FRAME)
        if total_bytes <= 0: total_bytes = BYTES_PER_FRAME
        
        offset_bytes = ms_to_bytes(self.cursor_ms)
        req_len = offset_bytes + total_bytes
        if len(self.current_track.pcm) < req_len:
            self.current_track.pcm.extend(b"\x00" * (req_len - len(self.current_track.pcm)))
            
        task = BackgroundMixerTask(self, self.current_track, offset_bytes, events, total_time_ms, inst_type, sf2_path)
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
        
        task = BackgroundMixerTask(self, metro, 0, events, total_time_ms, "drum", core.config.get("drum musical toolkit", ""))
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

    def open_toolbar_menu(self):
        m = menu.menu()
        m.init(self.w, "Toolbar")
        actions = [
            "Set Selection Start (Q)", "Set Selection End (E)", "Select All (Ctrl+A)",
            "Undo (Ctrl+Z)", "Redo (Ctrl+Y)", "Cut (Ctrl+X)", "Copy (Ctrl+C)", "Paste (Ctrl+V)", 
            "Mix Paste (Ctrl+M)", "Insert Silence", "New Track (Ctrl+N)", "Delete Track (Ctrl+F4)", 
            "Arranger & Beat Studio (I)", "Set Tempo (BPM)", "Track Volume", "Toggle Mute", 
            "Toggle Solo", "Save Project (.mte)", "Open Project (.mte)", "Close"
        ]
        for a in actions: m.append(a)
        m.open()

        while True:
            self.w.frameUpdate()
            sel = m.frameUpdate()
            if sel is None: continue
            if sel == -1 or sel == len(actions) - 1: break

            if sel == 0: self.marker_start_ms = self.cursor_ms; self.announce(f"Start: {format_time(self.marker_start_ms)}")
            elif sel == 1: self.marker_end_ms = self.cursor_ms; self.announce(f"End: {format_time(self.marker_end_ms)}")
            elif sel == 2: self.marker_start_ms, self.marker_end_ms = 0, self.current_track.get_length_ms(); self.announce("Selected all")
            elif sel == 3: self.trigger_undo()
            elif sel == 4: self.trigger_redo()
            elif sel == 5: self.cut_selection()
            elif sel == 6: self.copy_selection()
            elif sel == 7: self.paste_clipboard()
            elif sel == 8: self.mix_clipboard()
            elif sel == 9: self.insert_silence()
            elif sel == 10: self.add_new_track()
            elif sel == 11: self.delete_track()
            elif sel == 12: self.open_instrument_studio()
            elif sel == 13:
                v = kbt(None, "Tempo", "BPM:", str(self.bpm))
                if v and v.strip().isdigit(): self.bpm = int(v.strip()); self.announce(f"{self.bpm} BPM")
            elif sel == 14:
                v = kbt(None, "Track Volume", "0 to 200%:", str(self.current_track.volume))
                if v and v.strip().isdigit(): self.current_track.volume = max(0, min(200, int(v.strip()))); self.announce(f"{self.current_track.volume}%")
            elif sel == 15: self.current_track.muted = not self.current_track.muted; self.announce("Muted" if self.current_track.muted else "Unmuted")
            elif sel == 16: self.current_track.solo = not self.current_track.solo; self.announce("Solo On" if self.current_track.solo else "Solo Off")
            elif sel == 17: self.save_project()
            elif sel == 18: self.load_project(append=False)
            break

    def save_project(self):
        fname = kbt(None, "Save Project", "Config file name (.mte):", "project.mte")
        if not fname: return
        if not fname.lower().endswith(".mte"): fname += ".mte"

        base_dir, base_name = os.path.dirname(os.path.abspath(fname)), os.path.splitext(os.path.basename(fname))[0]
        proj = {"bpm": self.bpm, "cursor_ms": self.cursor_ms, "tracks": []}
        
        for i, t in enumerate(self.tracks):
            pcm_name = f"{base_name}_tr{i + 1}.pcm"
            with open(os.path.join(base_dir, pcm_name), "wb") as pf: pf.write(t.pcm)
            proj["tracks"].append({"name": t.name, "volume": t.volume, "pan": t.pan, "muted": t.muted, "solo": t.solo, "pcm_file": pcm_name})

        with open(fname, "w", encoding="utf-8") as f: json.dump(proj, f, indent=2)
        self.announce("Project saved")

    def load_project(self, append=False):
        fname = kbt(None, "Open Project", "Select .mte file:", "", file_dialog=True)
        if not fname or not os.path.exists(fname): return
        try:
            with open(fname, "r", encoding="utf-8") as f: proj = json.load(f)
        except Exception: self.announce("Error opening file"); return

        base_dir = os.path.dirname(os.path.abspath(fname))
        self.save_state()
        if not append: self.tracks.clear(); self.bpm = proj.get("bpm", 120)

        for t_info in proj.get("tracks", []):
            tr = Track(t_info.get("name", "Track"))
            tr.volume, tr.muted, tr.solo = t_info.get("volume", 100), t_info.get("muted", False), t_info.get("solo", False)
            pcm_path = os.path.join(base_dir, t_info.get("pcm_file", ""))
            if os.path.exists(pcm_path):
                with open(pcm_path, "rb") as pf: tr.pcm = bytearray(pf.read())
            self.tracks.append(tr)

        if not self.tracks: self.tracks.append(Track("Track 1"))
        self.active_track_idx, self.cursor_ms = 0, 0
        self.announce(f"{len(self.tracks)} tracks ready")

    def run(self):
        self.announce("Music Tracker Editor. Track 1")

        while True:
            self.w.frameUpdate()
            
            if self.w.keyPressed("exit"): self.stop_play(); break

            ctrl, shift = self.w.keyPressing("lcontrol") or self.w.keyPressing("rcontrol"), self.w.keyPressing("lshift") or self.w.keyPressing("rshift")

            if self.w.keyPressed("backspace"): self.open_toolbar_menu(); continue
            if self.w.keyPressed("i") and not ctrl: self.open_instrument_studio(); continue
            if ctrl and self.w.keyPressed("z"): self.trigger_undo(); continue
            if ctrl and self.w.keyPressed("y"): self.trigger_redo(); continue
            if ctrl and self.w.keyPressed("n"): self.add_new_track(); continue
            if ctrl and self.w.keyPressed("f4"): self.delete_track(); continue
                
            if self.w.keyPressed("tab") and ctrl:
                self.switch_track(-1 if shift else 1); continue
            elif self.w.keyPressed("tab") and not ctrl:
                self.seek_mode_idx = (self.seek_mode_idx + (-1 if shift else 1)) % len(self.seek_modes)
                self.announce(f"Seek mode: {self.seek_modes[self.seek_mode_idx]}"); continue
                
            if self.w.keyPressed("q") and not ctrl: self.marker_start_ms = self.cursor_ms; self.announce(f"Start: {format_time(self.marker_start_ms)}")
            elif self.w.keyPressed("e") and not ctrl:
                self.marker_end_ms = self.cursor_ms
                self.announce(f"End: {format_time(self.cursor_ms)}, {abs(self.marker_end_ms - self.marker_start_ms)} ms")
            if ctrl and self.w.keyPressed("a"): self.marker_start_ms, self.marker_end_ms = 0, self.current_track.get_length_ms(); self.announce("Selected all")
            elif ctrl and self.w.keyPressed("x"): self.cut_selection()
            elif ctrl and self.w.keyPressed("c"): self.copy_selection()
            elif ctrl and self.w.keyPressed("v"): self.paste_clipboard()
            elif ctrl and self.w.keyPressed("m"): self.mix_clipboard()
            elif ctrl and self.w.keyPressed("s"): self.save_project()
            elif ctrl and self.w.keyPressed("o"): self.load_project(append=shift)

            if self.w.keyPressed("b") and not ctrl:
                b_ms = (60.0 / self.bpm) * 1000.0
                self.cursor_ms = int(round(self.cursor_ms / b_ms) * b_ms)
                self.announce(f"Snap: {format_time(self.cursor_ms)}")

            if self.w.keyPressed("space"): self.toggle_play(all_tracks=not shift)

            if self.w.keyPressed("left") or self.w.keyPressed("right"):
                mode = self.seek_modes[self.seek_mode_idx]
                step_ms = 100
                if mode == "10 ms": step_ms = 10
                elif mode == "100 ms": step_ms = 100
                elif mode == "1 sec": step_ms = 1000
                elif mode == "1 Beat": step_ms = int((60.0 / self.bpm) * 1000.0)
                elif mode == "1 Bar": step_ms = int((60.0 / self.bpm) * 1000.0 * self.time_sig)

                delta = -step_ms if self.w.keyPressed("left") else step_ms
                
                if self.is_playing:
                    was_all = not self.play_is_solo
                    current_pos = self.cursor_ms
                    if self.preview:
                        try: current_pos = self.play_start_pos + self.preview.position
                        except: pass
                    self.stop_play()
                    self.cursor_ms = max(0, min(self.get_max_length(not was_all), current_pos + delta))
                    self.toggle_play(was_all)
                else:
                    self.cursor_ms = max(0, min(self.get_max_length(self.play_is_solo), self.cursor_ms + delta))
                
                self.announce(format_time(self.cursor_ms))
                continue

            if self.w.keyPressed("home"):
                if self.is_playing:
                    was_all = not self.play_is_solo
                    self.stop_play()
                    self.cursor_ms = 0
                    self.toggle_play(was_all)
                else:
                    self.cursor_ms = 0
                self.announce(f"Home {format_time(0)}")
                
            elif self.w.keyPressed("end"):
                if self.is_playing:
                    self.stop_play()
                self.cursor_ms = self.current_track.get_length_ms()
                self.announce(f"End {format_time(self.cursor_ms)}")

def run():
    app = MusicTrackerEditor()
    app.run()