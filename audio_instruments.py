"""Application instrument operations on pyaudiogaming's native BASS wrappers and VST3 (DawDreamer)."""
import base64
import ctypes
import os
from pathlib import Path
import queue
import struct
import tempfile
import threading
import time

from pyaudiogaming import buffer, system
from pyaudiogaming.sound_pool import musical as BaseMusical, sound as PushSound, vst as BaseVST
from pyaudiogaming.sound_modules import control, pybassmidi


def _load_pybassvst():
    if system.get_platform().get("os") == "android":
        raise RuntimeError("VST2 instruments are not supported on Android.")
    from pyaudiogaming.sound_modules import pybassvst
    return pybassvst


def _load_dawdreamer():
    if system.get_platform().get("os") == "android":
        raise RuntimeError("VST3 instruments are not supported on Android.")
    try:
        import dawdreamer as daw
    except ImportError as exc:
        raise RuntimeError("VST3 requires dawdreamer. Install with: pip install dawdreamer") from exc
    return daw


def _float_audio_to_pcm16(audio):
    import numpy as np
    arr = np.asarray(audio, dtype=np.float32)
    if arr.ndim == 1:
        arr = np.stack([arr, arr], axis=0)
    elif arr.shape[0] == 1:
        arr = np.concatenate([arr, arr], axis=0)
    elif arr.shape[0] > 2:
        arr = arr[:2]
    interleaved = np.clip(arr.T, -1.0, 1.0)
    return (interleaved * 32767.0).astype(np.int16).tobytes()


def _resolve_vst3_bundle(vst3_path):
    """DawDreamer expects the absolute .vst3 bundle path (normalize if user picked inner x86_64-win file)."""
    target = Path(os.path.abspath(str(vst3_path)))
    if target.is_file() and target.parent.name.lower() in ("x86_64-win", "x86-win"):
        contents = target.parent.parent
        if contents.name.lower() == "contents" and contents.parent.suffix.lower() == ".vst3":
            return str(contents.parent)
    return str(target)


def _juce_b64_encode(data):
    alpha = ".ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+"
    out = []
    n, pos = len(data), 0
    while pos < n:
        chunk = data[pos:pos + 3]
        pos += 3
        val = 0
        for idx, byte in enumerate(chunk):
            val |= (byte << (8 * idx))
        for step in range(len(chunk) + 1):
            out.append(alpha[(val >> (6 * step)) & 63])
    return f"{n}." + "".join(out)


def _surge_fxp_to_vc2(fxp_path):
    with open(fxp_path, "rb") as src:
        raw = src.read()
    pos = raw.find(b"sub3", 0, 128)
    if pos == -1:
        return None
    sub3 = raw[pos:]
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?> '
        f"<VST3PluginState><IComponent>{_juce_b64_encode(sub3)}</IComponent></VST3PluginState>"
    ).encode("utf-8")
    return b"VC2!" + struct.pack("<I", len(xml)) + xml


def _sfz_to_sfizz_vc2(sfz_path):
    """Encode an .sfz file path into a sfizz VST3 VC2! state blob (version 0)."""
    norm = os.path.abspath(str(sfz_path)).replace("\\", "/").encode("utf-8")
    blob = struct.pack("<QI", 0, len(norm) + 1) + norm + b"\x00" + struct.pack("<fiii", 0.0, 64, 0, 8192)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?> '
        f"<VST3PluginState><IComponent>{_juce_b64_encode(blob)}</IComponent></VST3PluginState>"
    ).encode("utf-8")
    return b"VC2!" + struct.pack("<I", len(xml)) + xml


def _categorize_param(name, label):
    text = f"{name} {label}".lower()
    if any(k in text for k in ("output", "volume", "gain", "master", "level", "cutoff", "resonan", "algorithm", "feedback", "transpose", "tune", "preset", "program")):
        return "Quick / Main"
    if any(k in text for k in ("op1", "op2", "op3", "op4", "op5", "op6", "osc", "wave", "pitch", "coarse", "fine", "detune", "voice", "poly", "mono", "unison", "octave")):
        return "Oscillator / Voice"
    if any(k in text for k in ("filter", "env", "eg ", "eg_", "attack", "decay", "sustain", "release", "rate", "break", "curve")):
        return "Filter & Envelope"
    if any(k in text for k in ("lfo", "mod", "vibrato", "tremolo", "wheel", "aftertouch", "velocity", "sens")):
        return "LFO & Mod"
    if any(k in text for k in ("reverb", "delay", "chorus", "flang", "phaser", "distort", "drive", "eq", "comp", "pan", "stereo", "fx", "mix", "wet", "dry")):
        return "Effects & Mix"
    return "Other"


class musical(BaseMusical):
    def create_empty_stream(self, channels=16, frequency=44100, decode=False):
        self.close()
        self.freq = frequency
        self.handle = pybassmidi.BASS_MIDI_StreamCreate(
            channels, control.parse_flags(0, decode=decode), frequency)
        if not self.handle:
            raise RuntimeError("Could not create MIDI stream")
        self.store_entry = control.register_hstream(self.handle)
        buffer.hSound_poolbuffers[self.sound_token] = self
        return self.handle

    def set_fonts(self, fonts):
        if isinstance(fonts, int):
            fonts = [(fonts, -1, 0)]
        mappings = (pybassmidi.BASS_MIDI_FONT * len(fonts))(
            *(pybassmidi.BASS_MIDI_FONT(*font) for font in fonts))
        return bool(pybassmidi.BASS_MIDI_StreamSetFonts(self.handle, mappings, len(fonts)))

    def send_event(self, chan, event, param):
        return bool(pybassmidi.BASS_MIDI_StreamEvent(self.handle, chan, event, param))


class vst(BaseVST):
    def create_instrument(self, dll_path, frequency=44100, channels=2, flags=0, ThreeD=False, **kwargs):
        pybassvst = _load_pybassvst()
        self.close()
        self.freq, self.chans = frequency, channels
        path, unicode_flag = control.encode_path(dll_path)
        self.vst_handle = pybassvst.BASS_VST_ChannelCreate(
            frequency, channels, ctypes.cast(path, ctypes.c_char_p),
            control.parse_flags(flags | unicode_flag, ThreeD=ThreeD, **kwargs))
        if not self.vst_handle:
            return False
        self.handle = self.vst_handle
        self.store_entry = control.register_hstream(self.handle)
        buffer.hSound_poolbuffers[self.sound_token] = self
        if ThreeD:
            self.attach_hrtf_dsp()
        return True

    def send_midi(self, chan, event, param):
        pybassvst = _load_pybassvst()
        return bool(pybassvst.BASS_VST_ProcessEvent(self.vst_handle, chan, event, param))

    def set_chunk(self, chunk_bytes, is_preset=True):
        if not self.vst_handle or not chunk_bytes:
            return False
        pybassvst = _load_pybassvst()
        data = ctypes.create_string_buffer(chunk_bytes)
        return bool(pybassvst.BASS_VST_SetChunk(
            self.vst_handle, is_preset, data, len(chunk_bytes)))


class vst3:
    """Universal VST3 Instrument host backed by DawDreamer (supports Surge XT, sfizz, Dexed, etc.)."""

    def __init__(self):
        self.engine, self.plugin = None, None
        self.freq, self.chans, self.block_size = 44100, 2, 512
        self.handle, self.sound_token, self.last_error = None, None, ""
        self._param_by_name = {}
        self._stream, self._thread, self._running = None, None, False
        self._lock = threading.Lock()
        self._midi_q = queue.Queue()

    def create_instrument(self, vst3_path, frequency=44100, channels=2, **kwargs):
        daw = _load_dawdreamer()
        self.close()
        self.last_error = ""
        if not vst3_path:
            self.last_error = "VST3 path is empty."
            return False
        self.freq, self.chans = int(frequency), int(channels)
        resolved = _resolve_vst3_bundle(vst3_path)
        try:
            self.engine = daw.RenderEngine(self.freq, self.block_size)
            self.plugin = self.engine.make_plugin_processor("vst3_inst", resolved)
            self.engine.load_graph([(self.plugin, [])])
        except Exception as exc:
            self.engine, self.plugin = None, None
            self.last_error = str(exc)
            return False
        return True

    def get_state(self):
        if self.plugin is None:
            return ""
        handle, tmp = tempfile.mkstemp(prefix="vst3-", suffix=".state")
        os.close(handle)
        try:
            self.plugin.save_state(tmp)
            with open(tmp, "rb") as src:
                raw = src.read()
            return base64.b64encode(raw).decode("ascii") if raw else ""
        except Exception:
            return ""
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def set_state(self, state_b64):
        if self.plugin is None or not state_b64:
            return False
        handle, tmp = tempfile.mkstemp(prefix="vst3-", suffix=".state")
        os.close(handle)
        try:
            raw = base64.b64decode(state_b64.encode("ascii")) if isinstance(state_b64, str) else bytes(state_b64)
            with open(tmp, "wb") as out:
                out.write(raw)
            self.plugin.load_state(tmp)
            if self.engine is not None:
                self.plugin.clear_midi()
                self.engine.load_graph([(self.plugin, [])])
                self.engine.render(0.08)
            return True
        except Exception:
            return False
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def load_preset_file(self, preset_path):
        if self.plugin is None or not preset_path or not os.path.isfile(preset_path):
            return False
        try:
            low = str(preset_path).lower()
            if low.endswith(".sfz"):
                return self.set_state(_sfz_to_sfizz_vc2(preset_path))
            if low.endswith(".fxp"):
                vc2 = _surge_fxp_to_vc2(preset_path)
                if vc2 is not None:
                    return self.set_state(vc2)
            if low.endswith(".vstpreset"):
                self.plugin.load_vst3_preset(str(preset_path))
            else:
                self.plugin.load_preset(str(preset_path))
            return True
        except Exception:
            return False

    def get_parameter_index(self):
        if self.plugin is None:
            return []
        self._param_by_name.clear()
        entries = []
        for desc in self.plugin.get_parameters_description():
            p_idx = int(desc.get("index", len(entries)))
            raw_name = str(desc.get("name", f"Param {p_idx}")).strip() or f"Param {p_idx}"
            if raw_name.lower().startswith("midi cc "):
                continue
            key = f"{p_idx}:{raw_name}"
            if raw_name.lower() == "program":
                key = "program"
            self._param_by_name[key] = p_idx
            val_strs = list(desc.get("valueStrings") or [])
            is_bool = bool(desc.get("isBoolean", False))
            cur_txt = str(desc.get("currentValText") or desc.get("text") or "")
            entries.append(dict(
                name=key, param_index=p_idx, label=raw_name,
                category=_categorize_param(raw_name, desc.get("category", "")),
                value=cur_txt if val_strs else float(desc.get("defaultValue", 0.0)),
                string_value=cur_txt, raw_value=float(desc.get("defaultValue", 0.0)),
                min=0.0, max=1.0, valid_values=val_strs, is_bool=is_bool, loaded=False,
            ))
        return entries

    def hydrate_parameters(self, entries, force=False):
        if self.plugin is None or not entries:
            return entries
        for entry in entries:
            if entry.get("loaded") and not force:
                continue
            p_idx = entry.get("param_index", self._param_by_name.get(entry["name"]))
            if p_idx is None:
                entry["loaded"] = True
                continue
            try:
                raw_val = float(self.plugin.get_parameter(p_idx))
                txt = str(self.plugin.get_parameter_text(p_idx) or "")
            except Exception:
                raw_val, txt = 0.0, ""
            val_strs = entry.get("valid_values") or []
            if entry.get("is_bool"):
                val = raw_val >= 0.5
            elif val_strs:
                val = txt if txt in val_strs else val_strs[min(len(val_strs) - 1, max(0, int(round(raw_val * (len(val_strs) - 1)))))]
            else:
                val = raw_val
            entry.update(raw_value=raw_val, value=val, string_value=txt, loaded=True)
        return entries

    def get_parameters(self):
        return self.hydrate_parameters(self.get_parameter_index())

    def get_parameter_display(self, name):
        if self.plugin is None:
            return ""
        p_idx = self._param_by_name.get(name)
        if p_idx is None:
            return ""
        try:
            return str(self.plugin.get_parameter_text(p_idx) or "")
        except Exception:
            return ""

    def set_parameter(self, name, value, use_raw=False):
        if self.plugin is None:
            return False
        p_idx = self._param_by_name.get(name)
        if p_idx is None:
            return False
        try:
            with self._lock:
                if use_raw:
                    norm = max(0.0, min(1.0, float(value)))
                elif isinstance(value, bool):
                    norm = 1.0 if value else 0.0
                elif isinstance(value, (int, float)):
                    norm = max(0.0, min(1.0, float(value)))
                else:
                    # Discrete string value -> map to normalized 0..1 index
                    descs = self.plugin.get_parameters_description()
                    vals = list(descs[p_idx].get("valueStrings") or []) if p_idx < len(descs) else []
                    if vals and value in vals and len(vals) > 1:
                        norm = vals.index(value) / float(len(vals) - 1)
                    else:
                        norm = 0.0
                self.plugin.set_parameter(p_idx, norm)
            return True
        except Exception:
            return False

    def show_native_gui(self):
        if self.plugin is None:
            return ""
        self.plugin.open_editor()
        return self.get_state()

    def send_midi(self, chan, event, param):
        if event == 1:
            note, vel = int(param) & 0x7F, (int(param) >> 8) & 0x7F
            if vel > 0:
                self._midi_q.put((note, vel))
            return True
        return False

    def send_event(self, chan, event, param):
        return self.send_midi(chan, event, param)

    def render_events(self, events, total_time_ms, chan=0):
        if self.plugin is None or self.engine is None:
            return b""
        active = {}
        notes_out = []
        for ev_ms, kind, note_num, vel in events:
            t_sec = max(0.0, float(ev_ms) / 1000.0)
            n = int(note_num) & 0x7F
            if kind == "on" and int(vel) > 0:
                active.setdefault(n, []).append((t_sec, int(vel) & 0x7F))
            else:
                if active.get(n):
                    st_sec, v = active[n].pop(0)
                    notes_out.append((n, v, st_sec, max(0.02, t_sec - st_sec)))
        end_sec = max(0.15, float(total_time_ms) / 1000.0)
        for n, pending in active.items():
            for st_sec, v in pending:
                notes_out.append((n, v, st_sec, max(0.05, end_sec - st_sec)))
        with self._lock:
            self.plugin.clear_midi()
            for n, v, st_sec, dur_sec in notes_out:
                self.plugin.add_midi_note(n, v, st_sec, dur_sec)
            self.engine.load_graph([(self.plugin, [])])
            self.engine.render(end_sec)
            audio = self.engine.get_audio()
        return _float_audio_to_pcm16(audio)

    def play_test_chord(self, notes=(60, 64, 67, 72), dur_ms=420, velocity=100, chan=0, style="arpeggio"):
        if self.plugin is None:
            return False
        events = []
        step_ms = 170 if style != "chord" else 0
        for idx, n in enumerate(notes):
            on_ms = idx * step_ms
            off_ms = on_ms + int(dur_ms)
            events.append((on_ms, "on", int(n), int(velocity)))
            events.append((off_ms, "off", int(n), 0))
        total_ms = (max(0, len(notes) - 1) * step_ms) + int(dur_ms) + 450
        pcm = self.render_events(events, total_time_ms=total_ms, chan=chan)
        if not pcm:
            return False

        def _play_worker():
            snd = PushSound()
            try:
                snd.stream("", draw=True)
                snd.play()
                snd.push(pcm)
                time.sleep((total_ms + 120) / 1000.0)
            except Exception:
                pass
            finally:
                try:
                    snd.stop()
                    snd.close()
                except Exception:
                    pass

        threading.Thread(target=_play_worker, daemon=True).start()
        return True

    def play(self):
        if self.plugin is None or self._running:
            return
        self._stream = PushSound()
        self._stream.stream("", draw=True)
        self._stream.play()
        self.handle = getattr(self._stream, "handle", None)
        self.sound_token = getattr(self._stream, "sound_token", None)
        self._running = True
        self._thread = threading.Thread(target=self._pump_loop, daemon=True)
        self._thread.start()

    def _pump_loop(self):
        while self._running and self.plugin is not None:
            batch = []
            while True:
                try:
                    batch.append(self._midi_q.get_nowait())
                except queue.Empty:
                    break
            if batch:
                events = []
                for note, vel in batch:
                    events.append((0, "on", note, vel))
                    events.append((420, "off", note, 0))
                try:
                    pcm = self.render_events(events, total_time_ms=550)
                    if pcm and self._stream is not None and self._running:
                        self._stream.push(pcm)
                except Exception as exc:
                    print(f"VST3 live render error: {exc}")
            time.sleep(0.015)

    def close(self):
        self._running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=0.3)
        self._thread = None
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self.handle = None
        self.plugin = None
        self.engine = None
