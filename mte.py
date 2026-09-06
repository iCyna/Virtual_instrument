# -*- coding: utf-8 -*-
"""
Music Tracker Editor (MTE)
Integrated Audio Tracker, Sequencer & Arranger for instrument-virtual gaming toolkit
Interface Language: English
"""

import os
import sys
import wave
import struct
import json
import time
import math
import random
import tempfile
import re
import winsound

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

import core
from pyaudiogaming import menu
from pyaudiogaming.inputBox import kbt
from pyaudiogaming.sound_pool import sound, musical
from pyaudiogaming.sound_lib.instrument import MIDIStream

# Audio PCM Standards: 44.1 kHz, 16-bit Little-Endian Stereo
SAMPLE_RATE = 44100
CHANNELS = 2
SAMPLE_WIDTH = 2
BYTES_PER_FRAME = CHANNELS * SAMPLE_WIDTH

def ms_to_bytes(ms):
    return int((float(ms) * SAMPLE_RATE) / 1000.0) * BYTES_PER_FRAME

def bytes_to_ms(byte_count):
    return int(((byte_count // BYTES_PER_FRAME) * 1000.0) / SAMPLE_RATE)

def format_time(ms):
    secs = ms / 1000.0
    return f"{int(secs // 60):02d}:{secs % 60:05.2f}"

# =============================================================================
# Audio Mixing (NumPy optimized for zero-latency playback)
# =============================================================================
def mix_pcm_buffers(base_data, overlay_data, offset_bytes=0, overlay_volume=1.0):
    req_len = max(len(base_data), offset_bytes + len(overlay_data))
    if len(base_data) < req_len:
        base_data.extend(b"\x00" * (req_len - len(base_data)))

    if not overlay_data:
        return

    if HAS_NUMPY:
        num_samples = len(overlay_data) // 2
        base_view = np.frombuffer(base_data, dtype=np.int16, count=num_samples, offset=offset_bytes)
        ov_view = np.frombuffer(overlay_data, dtype=np.int16)
        
        # Mix and clamp to prevent clipping
        mixed = base_view.astype(np.int32) + (ov_view.astype(np.float32) * overlay_volume).astype(np.int32)
        np.clip(mixed, -32768, 32767, out=mixed)
        base_data[offset_bytes : offset_bytes + len(overlay_data)] = mixed.astype(np.int16).tobytes()
    else:
        # Fallback using standard array if NumPy is unavailable
        import array
        base_arr = array.array('h', base_data[offset_bytes : offset_bytes + len(overlay_data)])
        ov_arr = array.array('h', overlay_data)
        for i in range(len(ov_arr)):
            val = base_arr[i] + int(ov_arr[i] * overlay_volume)
            base_arr[i] = max(-32768, min(32767, val))
        base_data[offset_bytes : offset_bytes + len(overlay_data)] = base_arr.tobytes()

# =============================================================================
# Manual Note & Chord Parser (Supports Sharps/Flats)
# =============================================================================
def parse_single_note(note_str, inst_type):
    note_str = note_str.strip().upper()
    if inst_type == "drum":
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

# =============================================================================
# Offline MIDI Renderer (Event-Based Jumping for High Speed)
# =============================================================================
def render_midi_sequence(sf2_path, events, total_ms, is_drum=False):
    inst = musical()
    w = core.getW()
    try:
        inst.handle = MIDIStream(channels=16, decode=True)
        inst.freq = SAMPLE_RATE
        
        if sf2_path and os.path.exists(sf2_path):
            inst.set_fonts(inst.load_font(sf2_path))
        
        events.sort(key=lambda x: x[0])
        out_buffer = bytearray()
        chan = 9 if is_drum else 0
        MIDI_EVENT_NOTE = 1
        
        # Process events by jumping to avoid unnecessary loops
        for ev in events:
            ev_time = ev[0]
            target_bytes = ms_to_bytes(ev_time)
            current_bytes = len(out_buffer)
            
            if target_bytes > current_bytes:
                req_bytes = target_bytes - current_bytes
                req_bytes -= (req_bytes % BYTES_PER_FRAME)
                if req_bytes > 0:
                    raw = inst.get_data(frame_size=req_bytes // 2, data_type="raw")
                    out_buffer.extend(raw if raw else b"\x00" * req_bytes)
            
            param = ev[2] | (ev[3] << 8) if ev[1] == "on" else ev[2] | (0 << 8)
            inst.send_event(chan, MIDI_EVENT_NOTE, param)
                
        # Pad remaining silence up to total_ms
        target_bytes = ms_to_bytes(total_ms)
        current_bytes = len(out_buffer)
        if target_bytes > current_bytes:
            req_bytes = target_bytes - current_bytes
            req_bytes -= (req_bytes % BYTES_PER_FRAME)
            if req_bytes > 0:
                raw = inst.get_data(frame_size=req_bytes // 2, data_type="raw")
                out_buffer.extend(raw if raw else b"\x00" * req_bytes)
                
        # 250ms sustain tail to prevent sudden cut-offs
        tail_bytes = ms_to_bytes(250)
        raw = inst.get_data(frame_size=tail_bytes // 2, data_type="raw")
        if raw: out_buffer.extend(raw)
            
        return out_buffer
    finally:
        inst.close()

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
        self.seek_mode_idx = 1 # Default 100ms
        
        self.preview = None
        self.is_playing = False
        self.play_clock = 0.0
        self.play_start_pos = 0
        self.play_is_solo = False
        self.temp_wav = os.path.join(tempfile.gettempdir(), "_mte_render.wav")

    @property
    def current_track(self): return self.tracks[self.active_track_idx]

    def announce(self, text): self.w.say(text)

    # ---------------- State Management & Undo/Redo ----------------
    def reset_playback(self):
        if self.preview:
            try:
                self.preview.stop()
                self.preview.close()
            except Exception: pass
            self.preview = None
        self.is_playing = False

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

    # ---------------- Render & Playback ----------------
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

    def write_wav(self, filepath, pcm):
        with wave.open(filepath, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm)

    def toggle_play(self, all_tracks=True):
        if self.is_playing:
            if self.preview: self.preview.setPaused(True)
            self.is_playing = False
            elapsed = int((time.time() - self.play_clock) * 1000)
            self.cursor_ms = min(self.get_max_length(self.play_is_solo), self.play_start_pos + elapsed)
            self.announce("Paused")
            return
            
        if self.preview and getattr(self.preview, 'paused', False):
            self.preview.setPaused(False)
            self.is_playing = True
            self.play_clock = time.time()
            self.play_start_pos = self.cursor_ms
            self.announce("Resumed")
            return

        self.reset_playback()
        data = self.render_mixdown(solo_current=not all_tracks)
        if not data:
            self.announce("Empty track")
            return
            
        import uuid
        self.temp_wav = os.path.join(tempfile.gettempdir(), f"_mte_render_{uuid.uuid4().hex[:6]}.wav")
        self.write_wav(self.temp_wav, data)
        
        self.preview = sound()
        self.preview.stream(self.temp_wav)
        self.preview.seek(self.cursor_ms)
        self.preview.play()
        self.preview.setPaused(False)
        self.is_playing = True
        self.play_is_solo = not all_tracks
        self.play_clock = time.time()
        self.play_start_pos = self.cursor_ms
        self.announce("Playing Mixdown" if all_tracks else f"Playing Solo {self.current_track.name}")

    def stop_play(self):
        self.reset_playback()
        self.announce("Stopped")

    def get_max_length(self, solo_current=False):
        return self.current_track.get_length_ms() if solo_current else max([t.get_length_ms() for t in self.tracks], default=0)

    # ---------------- Track Operations ----------------
    def add_new_track(self):
        self.save_state()
        new_track = Track(f"Track {len(self.tracks) + 1}")
        self.tracks.append(new_track)
        self.active_track_idx = len(self.tracks) - 1
        self.cursor_ms = 0
        self.announce(f"{new_track.name} created. Cursor 0")

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

    # ---------------- Editing Functions ----------------
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
        self.announce("Pasted. Cursor reset to 0")

    def mix_clipboard(self):
        if not self.clipboard:
            self.announce("Clipboard empty")
            return
        self.save_state()
        cb = ms_to_bytes(self.cursor_ms)
        mix_pcm_buffers(self.current_track.pcm, self.clipboard, offset_bytes=cb)
        self.cursor_ms = 0
        self.announce("Mixed. Cursor reset to 0")

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
        self.announce(f"Inserted {dur} ms. Cursor reset to 0")

    # ---------------- Instrument Studio & Sequencer ----------------
    def open_instrument_studio(self):
        m = menu.menu()
        m.init(self.w, "Arranger & Instrument Studio")
        m.append("Advanced Step Sequencer (Notes/Chords)")
        m.append("Metronome Beat Generator")
        m.append("Launch Live MIDI Instruments")
        m.append("Back")
        m.open()

        while True:
            self.w.frameUpdate()
            sel = m.frameUpdate()
            if sel is None: continue
            if sel == -1 or sel == 3: break
            if sel == 0: self.open_step_sequencer(); break
            elif sel == 1: self.arrange_metronome(); break
            elif sel == 2: self.launch_live_midi_instruments(); break

    def open_step_sequencer(self):
        m = menu.menu()
        m.init(self.w, "Select Instrument")
        m.append("Piano")
        m.append("Guitar")
        m.append("Drums")
        m.append("Back")
        m.open()
        
        while True:
            self.w.frameUpdate()
            sel = m.frameUpdate()
            if sel is None: continue
            if sel == -1 or sel == 3: return
            self.run_step_sequencer({0: "piano", 1: "guitar", 2: "drum"}[sel])
            break

    def run_step_sequencer(self, inst_type):
        msg = "Strumming: ~[C3,E3] (down), ^[C3,E3] (up)\n" if inst_type == "guitar" else ""
        msg += ("Syntax: Note-Beat-Velocity (e.g., Eb4-1-120 [E4,G4,C5]-0.5-80 R-1):" 
                if inst_type != "drum" else 
                "Drum Syntax: Code-Beat-Velocity (e.g., 36-1-127 38-1-50 [36,42]-0.5-90):")
               
        seq_str = kbt(None, f"{inst_type.capitalize()} Sequencer", msg, "")
        if not seq_str: return

        beat_ms = int((60.0 / self.bpm) * 1000)
        events, current_time = [], 0

        for token in seq_str.strip().upper().split():
            parts = token.split("-")
            pitch_str = parts[0]
            
            try: dur_beats = float(parts[1]) if len(parts) > 1 else 1.0
            except ValueError: dur_beats = 1.0
            try: velocity = int(parts[2]) if len(parts) > 2 else 100
            except ValueError: velocity = 100
            
            velocity, dur_ms = max(0, min(127, velocity)), int(dur_beats * beat_ms)

            if pitch_str == 'R':
                current_time += dur_ms
                continue

            is_down_strum, is_up_strum = pitch_str.startswith('~['), pitch_str.startswith('^[')
            if is_down_strum or is_up_strum: pitch_str = pitch_str[1:] 

            midi_notes = [parse_single_note(n, inst_type) for n in pitch_str[1:-1].split(',')] if (pitch_str.startswith('[') and pitch_str.endswith(']')) else [parse_single_note(pitch_str, inst_type)]
            strum_delay = 20 if (is_down_strum or is_up_strum) else 0
            if is_up_strum: midi_notes.reverse() 

            for i, n in enumerate(midi_notes):
                if n != -1:
                    events.extend([
                        (current_time + (i * strum_delay), 'on', n, velocity),
                        (current_time + dur_ms, 'off', n, 0)
                    ])
            current_time += dur_ms

        if not events:
            self.announce("No valid notes found.")
            return

        self.save_state()
        sf2_path = core.config.get(f"{inst_type} musical toolkit", "")
        self.announce("Building...")
        pcm = render_midi_sequence(sf2_path, events, current_time, is_drum=(inst_type == "drum"))
        
        mix_pcm_buffers(self.current_track.pcm, pcm, offset_bytes=ms_to_bytes(self.cursor_ms))
        self.cursor_ms = 0
        self.announce("Done! Cursor reset to 0.")

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

        self.save_state()
        self.announce("Generating metronome track...")
        pcm = render_midi_sequence(core.config.get("drum musical toolkit", ""), events, bars * self.time_sig * beat_ms, is_drum=True)
        
        metro = Track(f"Metronome {self.bpm}")
        metro.pcm = pcm
        self.tracks.append(metro)
        self.active_track_idx, self.cursor_ms = len(self.tracks) - 1, 0
        self.announce(f"{metro.name} generated. Cursor 0")

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

    # ---------------- Toolbar & File Ops ----------------
    def open_toolbar_menu(self):
        m = menu.menu()
        m.init(self.w, "Toolbar")
        actions = [
            "Set Selection Start (Q)", "Set Selection End (E)", "Select All (Ctrl+A)",
            "Undo (Ctrl+Z)", "Redo (Ctrl+Y)", "Cut (Ctrl+X)", "Copy (Ctrl+C)", "Paste (Ctrl+V)", 
            "Mix Paste (Ctrl+M)", "Insert Silence", "New Track (Ctrl+N)", "Delete Track (Ctrl+F4)", 
            "Arranger & Beat Studio (I)", "Set Tempo (BPM)", "Track Volume", "Toggle Mute", 
            "Toggle Solo", "Export Mixdown (.wav)", "Export Active Track (.wav)", 
            "Save Project (.mte)", "Open Project (.mte)", "Close"
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
            elif sel == 17: self.export_wav_dialog(mixdown=True)
            elif sel == 18: self.export_wav_dialog(mixdown=False)
            elif sel == 19: self.save_project()
            elif sel == 20: self.load_project(append=False)
            break

    def export_wav_dialog(self, mixdown=True):
        fname = kbt(None, "Export WAV", "File name:", "master_mix.wav" if mixdown else f"{self.current_track.name.replace(' ', '_')}.wav")
        if not fname: return
        if not fname.lower().endswith(".wav"): fname += ".wav"
        data = self.render_mixdown() if mixdown else bytearray(self.current_track.pcm)
        if not data: self.announce("No audio data"); return
        self.write_wav(fname, data); self.announce(f"Exported {fname}")

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

    # ---------------- Main Loop ----------------
    def run(self):
        self.announce("Music Tracker Editor. Track 1")

        while True:
            self.w.frameUpdate()
            
            # Monitor track playback status for Auto-Stop
            if self.is_playing and self.preview and not self.preview.playing:
                self.is_playing = False
                self.cursor_ms = self.get_max_length(self.play_is_solo)
                self.announce("Track ended")
            
            if self.w.keyPressed("exit"): self.stop_play(); break

            ctrl, shift = self.w.keyPressing("lcontrol") or self.w.keyPressing("rcontrol"), self.w.keyPressing("lshift") or self.w.keyPressing("rshift")

            if self.w.keyPressed("backspace"): self.open_toolbar_menu(); continue
            if self.w.keyPressed("i") and not ctrl: self.open_instrument_studio(); continue
            if ctrl and self.w.keyPressed("z"): self.trigger_undo(); continue
            if ctrl and self.w.keyPressed("y"): self.trigger_redo(); continue
            if ctrl and self.w.keyPressed("n"): self.add_new_track(); continue
            if ctrl and self.w.keyPressed("f4"): self.delete_track(); continue
                
            # Track Navigation & Seek Modes
            if self.w.keyPressed("tab") and ctrl:
                self.switch_track(-1 if shift else 1); continue
            elif self.w.keyPressed("tab") and not ctrl:
                self.seek_mode_idx = (self.seek_mode_idx + (-1 if shift else 1)) % len(self.seek_modes)
                self.announce(f"Seek mode: {self.seek_modes[self.seek_mode_idx]}"); continue
                
            # Selection & Clipboard
            if self.w.keyPressed("q") and not ctrl: self.marker_start_ms = self.cursor_ms; self.announce(f"Start: {format_time(self.cursor_ms)}")
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

            # Snap to Beat
            if self.w.keyPressed("b") and not ctrl:
                b_ms = (60.0 / self.bpm) * 1000.0
                self.cursor_ms = int(round(self.cursor_ms / b_ms) * b_ms)
                self.announce(f"Snap: {format_time(self.cursor_ms)}")

            if self.w.keyPressed("space"): self.toggle_play(all_tracks=not shift)

            # Live Seeking
            if self.w.keyPressed("left") or self.w.keyPressed("right"):
                mode = self.seek_modes[self.seek_mode_idx]
                step_ms = 100
                if mode == "10 ms": step_ms = 10
                elif mode == "100 ms": step_ms = 100
                elif mode == "1 sec": step_ms = 1000
                elif mode == "1 Beat": step_ms = int((60.0 / self.bpm) * 1000.0)
                elif mode == "1 Bar": step_ms = int((60.0 / self.bpm) * 1000.0 * self.time_sig)

                self.cursor_ms = max(0, min(self.get_max_length(self.play_is_solo), self.cursor_ms + (-step_ms if self.w.keyPressed("left") else step_ms)))
                
                if self.is_playing and self.preview:
                    self.preview.seek(self.cursor_ms)
                    self.play_start_pos, self.play_clock = self.cursor_ms, time.time()
                    
                self.announce(format_time(self.cursor_ms))
                continue

            if self.w.keyPressed("home"):
                self.cursor_ms = 0
                if self.is_playing and self.preview: self.preview.seek(0); self.play_start_pos, self.play_clock = 0, time.time()
                self.announce(f"Home {format_time(0)}")
            elif self.w.keyPressed("end"):
                self.cursor_ms = self.current_track.get_length_ms()
                self.announce(f"End {format_time(self.cursor_ms)}")

def run():
    app = MusicTrackerEditor()
    app.run()