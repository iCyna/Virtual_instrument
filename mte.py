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
import multiformat
from pyaudiogaming import vb
from pyaudiogaming.inputBox import kbt
from pyaudiogaming.sound_pool import playsingle

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
            root = tk.Tk()
            root.withdraw()
            text = root.clipboard_get()
            root.update()
            root.destroy()
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
            root = tk.Tk()
            root.withdraw()
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()
            root.destroy()
            return True
        except Exception:
            return False


def mix_pcm_buffers(base_data, overlay_data, offset_bytes=0, overlay_volume=1.0):
    if not overlay_data:
        return
    valid_len = len(overlay_data) - (len(overlay_data) % BYTES_PER_FRAME)
    if valid_len <= 0:
        return
    overlay_frozen = bytes(overlay_data[:valid_len])
    offset_bytes -= (offset_bytes % BYTES_PER_FRAME)
    req_len = max(len(base_data), offset_bytes + valid_len)
    if len(base_data) < req_len:
        base_data.extend(b"\x00" * (req_len - len(base_data)))

    if HAS_NUMPY:
        try:
            base_frozen = bytes(base_data[offset_bytes:offset_bytes + valid_len])
            base_view = np.frombuffer(base_frozen, dtype=np.int16)
            ov_view = np.frombuffer(overlay_frozen, dtype=np.int16)
            mixed = base_view.astype(np.int32) + (ov_view.astype(np.float32) * overlay_volume).astype(np.int32)
            np.clip(mixed, -32768, 32767, out=mixed)
            base_data[offset_bytes:offset_bytes + valid_len] = mixed.astype(np.int16).tobytes()
            return
        except Exception:
            pass

    import array
    base_arr = array.array("h", base_data[offset_bytes:offset_bytes + valid_len])
    ov_arr = array.array("h", overlay_frozen)
    for idx in range(len(ov_arr)):
        val = base_arr[idx] + int(ov_arr[idx] * overlay_volume)
        base_arr[idx] = max(-32768, min(32767, val))
    base_data[offset_bytes:offset_bytes + valid_len] = base_arr.tobytes()


def parse_single_note(note_str, inst_type):
    note_str = note_str.strip().upper()
    if "drum" in inst_type:
        return int(note_str) if note_str.isdigit() else -1
    match = re.match(r"([A-G][#B]?)(\d)", note_str)
    if match:
        note_name, octave = match.group(1), int(match.group(2))
        note_map = {
            "C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3,
            "E": 4, "F": 5, "F#": 6, "GB": 6, "G": 7, "G#": 8,
            "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11,
        }
        return 12 + (octave * 12) + note_map.get(note_name, 0)
    return -1


def parse_sequence_to_events(seq_str, inst_type, bpm):
    beat_ms = int((60.0 / bpm) * 1000)
    events, current_time, max_time = [], 0, 0
    tokens = seq_str.strip().upper().split()
    if not tokens:
        return None, 0

    for token in tokens:
        start_offset_ms, is_absolute_ms = None, False
        if "@" in token:
            token_parts = token.split("@")
            pitch_str = token_parts[0]
            rest_parts = token_parts[1].split("-")
            start_offset_ms = int(float(rest_parts[0]))
            is_absolute_ms = True
            parts = [pitch_str] + rest_parts[1:]
        else:
            parts = token.split("-")
            pitch_str = parts[0]

        if is_absolute_ms:
            try:
                dur_ms = int(float(parts[1])) if len(parts) > 1 else 500
            except ValueError:
                dur_ms = 500
        else:
            try:
                dur_beats = float(parts[1]) if len(parts) > 1 else 1.0
            except ValueError:
                dur_beats = 1.0
            dur_ms = int(dur_beats * beat_ms)

        try:
            velocity = int(parts[2]) if len(parts) > 2 else 100
        except ValueError:
            velocity = 100
        velocity = max(0, min(127, velocity))

        if pitch_str == "R":
            current_time = (start_offset_ms + dur_ms) if start_offset_ms is not None else (current_time + dur_ms)
            max_time = max(max_time, current_time)
            continue

        is_down_strum, is_up_strum = pitch_str.startswith("~["), pitch_str.startswith("^[")
        if is_down_strum or is_up_strum:
            pitch_str = pitch_str[1:]

        if pitch_str.startswith("[") and pitch_str.endswith("]"):
            midi_notes = [parse_single_note(n, inst_type) for n in pitch_str[1:-1].split(",")]
        else:
            midi_notes = [parse_single_note(pitch_str, inst_type)]

        strum_delay = 20 if (is_down_strum or is_up_strum) else 0
        if is_up_strum:
            midi_notes.reverse()

        note_start_time = start_offset_ms if start_offset_ms is not None else current_time
        for idx, n in enumerate(midi_notes):
            if n != -1:
                on_time = note_start_time + (idx * strum_delay)
                off_time = max(on_time + 10, note_start_time + dur_ms)
                events.extend([(on_time, "on", n, velocity), (off_time, "off", n, 0)])
                max_time = max(max_time, off_time)

        current_time = (current_time + dur_ms) if start_offset_ms is None else max_time

    if not events:
        return None, 0
    events.sort(key=lambda item: item[0])
    return events, max_time


class BackgroundMixerTask(threading.Thread):
    def __init__(self, app, track, offset_bytes, events, total_time_ms, inst_type):
        super().__init__()
        self.app, self.track, self.offset_bytes = app, track, offset_bytes
        self.events, self.total_time_ms, self.inst_type = events, total_time_ms, inst_type
        self.daemon = True

    def run(self):
        inst = None
        try:
            inst_config = core.resolve_config(core.config, self.inst_type)
            engine = inst_config.get("active_engine", "sf2") if core.vst_supported() else "sf2"
            is_vst = engine == "vst"
            chan = 9 if "drum" in self.inst_type else 0

            if engine == "vst3":
                from audio_instruments import vst3
                inst = vst3()
                if not inst.create_instrument(inst_config.get("vst3_path", ""), frequency=SAMPLE_RATE):
                    self.app.announce(f"Error: Cannot load {self.inst_type} VST3 plugin.")
                    return
                if inst_config.get("vst3_state"):
                    inst.set_state(inst_config["vst3_state"])
                raw = inst.render_events(self.events, self.total_time_ms, chan=chan)
                if raw:
                    mix_pcm_buffers(self.track.pcm, raw, self.offset_bytes, 1.0)
                return

            if is_vst:
                from audio_instruments import vst
                inst = vst()
                if not inst.create_instrument(inst_config["vst_path"], frequency=SAMPLE_RATE, flags=0x200000):
                    self.app.announce("Error: Cannot load VST. Ensure DLL is architecture compatible.")
                    return
                if inst_config.get("vst_chunk"):
                    inst.set_chunk(inst_config["vst_chunk"])
            else:
                from audio_instruments import musical
                inst = musical()
                inst.create_empty_stream(channels=16, frequency=SAMPLE_RATE, decode=True)
                inst.freq = SAMPLE_RATE
                sf2_path = inst_config.get("sf2_path", "")
                if sf2_path and os.path.exists(sf2_path):
                    with font_load_lock:
                        loaded_font = inst.load_font(sf2_path)
                    inst.set_fonts(loaded_font)
                inst.send_event(chan, 2, int(inst_config.get("sf2_id", 0)))

            event_idx, num_events = 0, len(self.events)
            total_bytes = ms_to_bytes(self.total_time_ms)
            total_bytes -= (total_bytes % BYTES_PER_FRAME)
            current_bytes, chunk_bytes = 0, ms_to_bytes(100)

            while current_bytes < total_bytes:
                while event_idx < num_events:
                    ev_bytes = ms_to_bytes(self.events[event_idx][0])
                    if ev_bytes <= current_bytes:
                        ev = self.events[event_idx]
                        param = ev[2] | (ev[3] << 8) if ev[1] == "on" else ev[2]
                        if is_vst:
                            inst.send_midi(chan, 1, param)
                        else:
                            inst.send_event(chan, 1, param)
                        event_idx += 1
                    else:
                        break

                req = min(chunk_bytes, total_bytes - current_bytes)
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
                        try:
                            play_pos_ms = self.app.play_start_pos + self.app.preview.position
                        except Exception:
                            pass
                    dist = play_pos_ms - bytes_to_ms(self.offset_bytes + current_bytes)
                    if dist > 0:
                        time.sleep(0)
                    elif dist > -1500:
                        time.sleep(0.002)
                    else:
                        time.sleep(0.02)
                else:
                    time.sleep(0.015)

            inst.close()
            try:
                from pyaudiogaming import buffer
                if inst.sound_token in buffer.hSound_poolbuffers:
                    del buffer.hSound_poolbuffers[inst.sound_token]
            except Exception:
                pass
        except Exception as exc:
            print(f"Background render error: {exc}")
            self.app.announce(f"Could not load {self.inst_type}: {exc}")
        finally:
            if inst is not None:
                inst.close()


class Track:
    def __init__(self, name="Track 1"):
        self.name, self.pcm = name, bytearray()
        self.volume, self.pan, self.muted, self.solo = 100, 0, False, False
        self.import_state = None

    def get_length_ms(self):
        return bytes_to_ms(len(self.pcm))


from mte_playermode import PlayerModeMixin


class MusicTrackerEditor(PlayerModeMixin):
    def __init__(self):
        self.w = core.getW()
        self.tracks = [Track("Track 1")]
        self.active_track_idx = 0
        self.cursor_ms, self.marker_start_ms, self.marker_end_ms = 0, 0, 0
        self.clipboard = bytearray()
        self.undo_stack, self.redo_stack = [], []
        self.project_path, self.dirty = None, False

        self.bpm = 120
        self.time_sig, self.time_sig_numerator, self.time_sig_denominator = 4, 4, 4
        self.seek_modes = ["10 ms", "100 ms", "1 sec", "1 Beat", "1 Bar"]
        self.seek_mode_idx = 1

        self.preview, self.is_playing = None, False
        self.play_clock, self.play_start_pos, self.play_is_solo = 0.0, 0, False

    @property
    def current_track(self):
        return self.tracks[self.active_track_idx]

    def announce(self, text):
        self.w.say(text)

    def open_instrument_studio(self):
        display_names = ["Piano", "Guitar", "Bass", "Strings", "Synth", "Flute", "Drums", "Electronic Drums"]
        inst_keys = ["piano", "guitar", "bass", "strings", "synth", "flute", "drum", "electronic drum"]
        live_list = list(core.live_instruments.items())

        form = vb.form(self.w, config={"label": "Arranger & Instrument Studio", "adjacent_submit": False})
        form.add("section", "tab", choices=["Sequencer", "Metronome", "Import Music", "Live Instruments"],
                 value=0, label="Studio Tab")

        # Tab 0: Sequencer & Input Mode
        form.add("inst", "combo", value=0, choices=display_names, label="Instrument", tab_page="Sequencer")
        form.add("method", "radio", value=0, choices=[
            "Manual Text Input",
            "Load Sequence File (.txt)",
            "Set Import Mode Instrument (Ctrl+P)",
        ], label="Input Method", tab_page="Sequencer")
        form.add("run_seq", "button", label="Start", tab_page="Sequencer")

        # Tab 1: Metronome
        form.add("bars", "input", value="4", number_only=True, label="Number of Bars", tab_page="Metronome")
        form.add("gen_metro", "button", label="Generate Metronome Track", tab_page="Metronome")

        # Tab 2: Import MIDI / MusicXML
        form.add("imp_target", "combo", value=0, choices=[
            "Pitched Instruments (Piano/Guitar/Strings...)",
            "Drums / Electronic Drums",
        ], label="MIDI Target", tab_page="Import Music")
        form.add("xml_mode", "combo", value=0, choices=[
            "Open in Input Mode",
            "Convert to Sequence Text",
        ], label="MusicXML Output", tab_page="Import Music")
        form.add("run_import", "button", label="Choose Music File (.mid, .mxl, .xml)...", tab_page="Import Music")

        # Tab 3: Live Instruments
        form.add("live_inst", "list", value=0, choices=[name for name, mod in live_list],
                 label="Live Instruments", tab_page="Live Instruments")
        form.add("launch_live", "button", label="Launch Live Instrument", tab_page="Live Instruments")

        form.add("close", "button", label="Close")

        action = form.open()
        if action in (-1, "close"):
            return
        if action == "run_seq":
            inst_type = inst_keys[int(form.get("inst") or 0)]
            method = int(form.get("method") or 0)
            if method == 0:
                self.run_step_sequencer(inst_type, from_file=False)
            elif method == 1:
                self.run_step_sequencer(inst_type, from_file=True)
            else:
                from mte_importmode import ImportModeState
                if self.current_track.import_state is None:
                    self.current_track.import_state = ImportModeState(inst_type)
                else:
                    self.current_track.import_state.inst_type = inst_type
                self.dirty = True
                self.announce(f"Import Mode set to {inst_type.title()} for {self.current_track.name}. Press Ctrl+P to open.")
        elif action == "gen_metro":
            bars_val = str(form.get("bars") or "4").strip()
            if bars_val.isdigit() and int(bars_val) > 0:
                self.arrange_metronome(bars=int(bars_val))
            else:
                vb.warning_box("Invalid Bars", "Enter a positive number of bars.", window=self.w)
        elif action == "run_import":
            inst_choice = "drum" if int(form.get("imp_target") or 0) == 1 else "piano"
            xml_output = "input" if int(form.get("xml_mode") or 0) == 0 else "text"
            self.extract_midi_to_string(inst_choice=inst_choice, xml_output=xml_output)
        elif action == "launch_live" and live_list:
            sel = int(form.get("live_inst") or 0)
            name, instrument = live_list[sel]
            if self.is_playing:
                self.stop_play()
            self.announce(f"Opening {name}")
            instrument.run()
            self.announce("Back to Music Tracker Editor")

    def new_input_score(self):
        from mte_importmode import ImportModeEditor, ImportModeState
        track = Track("New score")
        track.import_state = ImportModeState("piano")
        editor = ImportModeEditor(self, track)
        if not editor.open_rhythm_menu():
            editor.synth.close()
            return
        self.stop_play()
        self.save_state()
        if len(self.tracks) == 1 and not self.current_track.pcm and self.current_track.import_state is None:
            self.tracks[0] = track
        else:
            self.tracks.append(track)
        self.active_track_idx = self.tracks.index(track)
        self.cursor_ms = 0
        editor.run()

    def open_import_mode(self):
        from mte_importmode import ImportModeEditor, ImportModeState
        if self.current_track.import_state is None:
            self.current_track.import_state = ImportModeState("piano")
        self.stop_play()
        editor = ImportModeEditor(self, self.current_track)
        editor.run()

    def run_step_sequencer(self, inst_type, from_file=False, sequence=None):
        if sequence is not None:
            seq_str = sequence
        elif from_file:
            filepath = kbt(None, "Load Sequence File", "Enter path or choose .txt file:", "", file_dialog=True)
            if not filepath or not os.path.exists(filepath):
                self.announce("File not found.")
                return
            try:
                seq_str = multiformat.import_sequence_txt(filepath)
                self.announce(f"Loaded {os.path.basename(filepath)}")
            except Exception as exc:
                vb.error_box("Read Error", f"Error reading file: {exc}", window=self.w)
                return
        else:
            msg = "Type '*clip' to paste from clipboard.\n"
            msg += "Strumming: ~[C3,E3] (down), ^[C3,E3] (up)\n" if inst_type == "guitar" else ""
            msg += ("Syntax: Note-Beat-Velocity (e.g., Eb4-1-120 [E4,G4,C5]-0.5 R-1):"
                    if "drum" not in inst_type else
                    "Drum Syntax: Code-Beat-Velocity (e.g., 36-1-127 38-1-50 [36,42]-0.5):")
            seq_str = kbt(None, f"{inst_type.title()} Sequencer", msg, "")
            if not seq_str:
                return
            if seq_str.strip().lower() == "*clip":
                clip_data = get_clipboard_text()
                if not clip_data:
                    self.announce("Clipboard is empty or inaccessible.")
                    return
                seq_str = clip_data
                self.announce("Loaded sequence from clipboard.")

        seq_str = seq_str.replace("\n", " ").replace("\r", " ")
        self.announce("Parsing sequence...")
        events, seq_time = parse_sequence_to_events(seq_str, inst_type, self.bpm)
        if not events:
            self.announce("No valid notes found.")
            return

        total_time_ms = seq_time + 500
        self.save_state()
        total_bytes = ms_to_bytes(total_time_ms)
        total_bytes -= (total_bytes % BYTES_PER_FRAME)
        if total_bytes <= 0:
            total_bytes = BYTES_PER_FRAME

        offset_bytes = ms_to_bytes(self.cursor_ms)
        req_len = offset_bytes + total_bytes
        if len(self.current_track.pcm) < req_len:
            self.current_track.pcm.extend(b"\x00" * (req_len - len(self.current_track.pcm)))

        task = BackgroundMixerTask(self, self.current_track, offset_bytes, events, total_time_ms, inst_type)
        task.start()
        self.announce("Sequence rendering in background. You can play or seek immediately.")
        self.cursor_ms = 0

    def arrange_metronome(self, bars=None):
        if bars is None:
            bars_str = kbt(None, "Metronome Track", "Enter number of bars:", "4")
            if not bars_str or not bars_str.strip().isdigit():
                return
            bars = int(bars_str.strip())
        beat_ms = int((60.0 / self.bpm) * 1000)
        events = []
        pulse_beats = 4 / getattr(self, "time_sig_denominator", 4)
        for bar in range(bars):
            for beat in range(getattr(self, "time_sig_numerator", int(self.time_sig))):
                t_ms = (bar * self.time_sig + beat * pulse_beats) * beat_ms
                note = 76 if beat == 0 else 77
                events.extend([(t_ms, "on", note, 110), (t_ms + 100, "off", note, 0)])

        total_time_ms = bars * self.time_sig * beat_ms + 500
        self.save_state()
        self.announce("Generating metronome track...")
        metro = Track(f"Metronome {self.bpm}")
        total_bytes = ms_to_bytes(total_time_ms)
        total_bytes -= (total_bytes % BYTES_PER_FRAME)
        if total_bytes <= 0:
            total_bytes = BYTES_PER_FRAME
        metro.pcm = bytearray(total_bytes)
        self.tracks.append(metro)
        self.active_track_idx = len(self.tracks) - 1
        self.cursor_ms = 0
        task = BackgroundMixerTask(self, metro, 0, events, total_time_ms, "drum")
        task.start()
        self.announce(f"{metro.name} generated. Rendering in background.")

    def launch_live_midi_instruments(self):
        instruments = list(core.live_instruments.items())
        form = vb.form(self.w, config={"label": "Live Instruments", "adjacent_submit": False})
        form.add("inst", "list", value=0, choices=[name for name, mod in instruments], label="Select Instrument")
        form.add("launch", "button", label="Launch")
        form.add("cancel", "button", label="Close")
        if form.open() != "launch":
            return
        name, instrument = instruments[int(form.get("inst") or 0)]
        if self.is_playing:
            self.stop_play()
        self.announce(f"Opening {name}")
        instrument.run()
        self.announce("Back to Music Tracker Editor")

    def open_settings(self):
        import setting
        if self.is_playing:
            self.stop_play()
        setting.run()
        self.announce("Back to Music Tracker Editor")

    def extract_midi_to_string(self, filepath=None, inst_choice=None, xml_output="input"):
        if not filepath:
            try:
                filepath = multiformat.open_file("Select Music File",
                    "Music files (*.mid;*.midi;*.mxl;*.musicxml;*.xml)|*.mid;*.midi;*.mxl;*.musicxml;*.xml")
            except Exception:
                filepath = kbt(None, "Select Music File", "Choose .mid, .mxl, .musicxml or .xml:", "", file_dialog=True)
        if not filepath or not os.path.exists(filepath):
            return

        fmt = multiformat.detect_format(filepath)
        is_xml = fmt == "musicxml"
        if not is_xml and not HAS_MIDO:
            vb.error_box("Missing Dependency", "Missing mido library. Please install: pip install mido", window=self.w)
            return

        if inst_choice is None:
            inst_choice = "piano"

        self.announce("Reading MusicXML..." if is_xml else "Extracting MIDI...")
        state = {"done": False, "seq": "", "err": "", "progress": 0, "items": None}

        def extraction_worker():
            try:
                if is_xml:
                    score = multiformat.load_score(filepath)
                    if xml_output == "input":
                        state["items"] = multiformat.score_to_import_items(score)
                    else:
                        state["seq"] = multiformat.score_to_sequence(score)
                    state["progress"] = 100
                else:
                    state["seq"] = multiformat.import_midi_to_sequence(
                        filepath, inst_choice=inst_choice,
                        progress_cb=lambda pct: state.__setitem__("progress", pct))
            except Exception as exc:
                state["err"] = str(exc)
            finally:
                state["done"] = True

        threading.Thread(target=extraction_worker, daemon=True).start()
        last_pct = -1
        while not state["done"]:
            self.w.frameUpdate()
            if state["progress"] > last_pct:
                playsingle("collections/audio/progress.ogg", pitch=15 + (state["progress"] * 5))
                last_pct = state["progress"]
            time.sleep(0.01)

        if state["err"]:
            vb.error_box("Import Error", "Error importing music: " + state["err"], window=self.w)
            return

        if is_xml and xml_output == "input":
            imported_items = state["items"]
            if not imported_items:
                self.announce("No notes or rests found")
                return
            from mte_importmode import ImportModeState
            st = ImportModeState("piano")
            st.items = imported_items
            for item in imported_items:
                if item["clef"] not in st.clefs:
                    st.clefs.append(item["clef"])
            st.active_clef = imported_items[0]["clef"]
            if "staff_id" in imported_items[0]:
                st.active_lane = [imported_items[0]["staff_id"], imported_items[0]["voice_id"]]
            self.current_track.import_state = st
            self.dirty = True
            self.open_import_mode()
            return

        seq_str = state["seq"]
        if not seq_str:
            self.announce("No playable notes found")
            return

        form = vb.form(self.w, config={"label": "Extraction Complete", "adjacent_submit": False})
        form.add("action", "list", value=0, choices=[
            "Load into Current Track for Playback",
            "Copy to Clipboard",
            "Save Sequence File (.txt)",
        ], label="Next Action")
        form.add("ok", "button", label="Apply")
        form.add("cancel", "button", label="Discard")
        if form.open() != "ok":
            return
        sel = int(form.get("action") or 0)
        if sel == 0:
            self.run_step_sequencer(inst_choice, sequence=seq_str)
        elif sel == 1:
            ok = set_clipboard_text(seq_str)
            self.announce("Copied to clipboard!" if ok else "Failed to copy.")
        elif sel == 2:
            base_name = os.path.splitext(os.path.basename(filepath))[0] + ".txt"
            try:
                out_file = multiformat.save_file("Save Sequence", base_name, "Text files (*.txt)|*.txt")
            except Exception:
                out_file = kbt(None, "Save Sequence", "Enter output .txt path:", base_name)
            if out_file:
                multiformat.export_sequence_txt(out_file, seq_str)
                self.announce(f"Exported to {out_file}")

    def run(self):
        self.run_player_loop()


def run():
    app = MusicTrackerEditor()
    app.run()
