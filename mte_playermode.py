import os
import time
import threading

import multiformat
from pyaudiogaming import vb
from pyaudiogaming.inputBox import kbt
from pyaudiogaming.sound_pool import sound

import mte
from mte import (
    Track, ms_to_bytes, bytes_to_ms, format_time,
    mix_pcm_buffers, BYTES_PER_FRAME,
)


class PlaybackThread(threading.Thread):
    def __init__(self, app, all_tracks=True):
        super().__init__()
        self.app, self.all_tracks = app, all_tracks
        self.daemon, self.active = True, True

    def run(self):
        try:
            chunk_bytes = ms_to_bytes(100)
            start_byte = ms_to_bytes(self.app.cursor_ms)
            current_byte = start_byte
            max_len_bytes = (max([len(t.pcm) for t in self.app.tracks], default=0)
                             if self.all_tracks else len(self.app.current_track.pcm))
            if start_byte >= max_len_bytes:
                self.app.is_playing = False
                return

            self.app.preview = sound()
            self.app.preview.stream("", draw=True)
            self.app.preview.play()

            while self.app.is_playing and self.active and current_byte < max_len_bytes:
                mixed_chunk = bytearray(b"\x00" * chunk_bytes)
                has_solo = any(t.solo for t in self.app.tracks)
                tracks = self.app.tracks if self.all_tracks else [self.app.current_track]
                for tr in tracks:
                    if self.all_tracks:
                        if has_solo and not tr.solo:
                            continue
                        if not has_solo and tr.muted:
                            continue
                    t_len = len(tr.pcm)
                    if current_byte < t_len:
                        end_byte = min(current_byte + chunk_bytes, t_len)
                        mix_pcm_buffers(mixed_chunk, tr.pcm[current_byte:end_byte], 0, tr.volume / 100.0)
                if not self.app.is_playing or not self.active:
                    break
                self.app.preview.push(bytes(mixed_chunk))
                current_byte += chunk_bytes

                while self.app.is_playing and self.active:
                    try:
                        pos_ms = self.app.preview.position
                    except Exception:
                        pos_ms = 0
                    if bytes_to_ms(current_byte - start_byte) - pos_ms > 400:
                        time.sleep(0.02)
                    else:
                        break

            while self.app.is_playing and self.active:
                try:
                    pos_ms = self.app.preview.position
                except Exception:
                    pos_ms = 0
                if pos_ms >= bytes_to_ms(current_byte - start_byte) - 50:
                    break
                time.sleep(0.05)

            if self.app.is_playing and self.active:
                self.app.is_playing = False
                self.app.cursor_ms = bytes_to_ms(max_len_bytes)
                self.app.announce("Track ended")
        except Exception as exc:
            print(f"Playback error: {exc}")
            self.app.is_playing = False


class PlayerModeMixin:
    """Player playback, tracks, selection, clipboard, unified vb workspace, and file I/O."""

    def reset_playback(self):
        self.is_playing = False
        if hasattr(self, "playback_thread") and self.playback_thread:
            self.playback_thread.active = False
        if self.preview:
            try:
                self.preview.stop()
                self.preview.close()
                from pyaudiogaming import buffer
                if self.preview.sound_token in buffer.hSound_poolbuffers:
                    del buffer.hSound_poolbuffers[self.preview.sound_token]
            except Exception:
                pass
            self.preview = None

    def save_state(self):
        self.reset_playback()
        self.dirty = True
        if len(self.undo_stack) > 15:
            self.undo_stack.pop(0)
        state = {"active_idx": self.active_track_idx, "cursor": self.cursor_ms, "tracks": []}
        for tr in self.tracks:
            nt = Track(tr.name)
            nt.pcm = bytearray(tr.pcm)
            nt.volume, nt.pan, nt.muted, nt.solo = tr.volume, tr.pan, tr.muted, tr.solo
            nt.import_state = tr.import_state
            state["tracks"].append(nt)
        self.undo_stack.append(state)
        self.redo_stack.clear()

    def restore_state(self, state):
        self.active_track_idx, self.cursor_ms = state["active_idx"], state["cursor"]
        self.tracks = []
        for tr in state["tracks"]:
            nt = Track(tr.name)
            nt.pcm = bytearray(tr.pcm)
            nt.volume, nt.pan, nt.muted, nt.solo = tr.volume, tr.pan, tr.muted, tr.solo
            nt.import_state = tr.import_state
            self.tracks.append(nt)

    def _swap_state(self, pop_stack, push_stack, msg):
        self.reset_playback()
        if not pop_stack:
            self.announce(f"Nothing to {msg.split()[0].lower()}")
            return
        c_state = {"active_idx": self.active_track_idx, "cursor": self.cursor_ms, "tracks": []}
        for tr in self.tracks:
            nt = Track(tr.name)
            nt.pcm = bytearray(tr.pcm)
            nt.volume, nt.pan, nt.muted, nt.solo = tr.volume, tr.pan, tr.muted, tr.solo
            nt.import_state = tr.import_state
            c_state["tracks"].append(nt)
        push_stack.append(c_state)
        self.restore_state(pop_stack.pop())
        self.dirty = True
        self.announce(msg)

    def trigger_undo(self):
        self._swap_state(self.undo_stack, self.redo_stack, "Undo successful")

    def trigger_redo(self):
        self._swap_state(self.redo_stack, self.undo_stack, "Redo successful")

    def render_mixdown(self, solo_current=False):
        if solo_current:
            return bytearray(self.current_track.pcm)
        max_len = max([len(t.pcm) for t in self.tracks], default=0)
        if max_len == 0:
            return bytearray()
        mixed = bytearray(b"\x00" * max_len)
        has_solo = any(t.solo for t in self.tracks)
        for tr in self.tracks:
            if (has_solo and not tr.solo) or (not has_solo and tr.muted):
                continue
            mix_pcm_buffers(mixed, tr.pcm, offset_bytes=0, overlay_volume=tr.volume / 100.0)
        return mixed

    def get_max_length(self, solo_current=False):
        return (self.current_track.get_length_ms() if solo_current
                else max([t.get_length_ms() for t in self.tracks], default=0))

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
        self.is_playing, self.play_is_solo, self.play_start_pos = True, not all_tracks, self.cursor_ms
        self.playback_thread = PlaybackThread(self, all_tracks)
        self.playback_thread.start()
        self.announce("Playing" if all_tracks else f"Solo {self.current_track.name}")

    def stop_play(self):
        if self.is_playing and self.preview:
            try:
                elapsed_ms = self.preview.position
            except Exception:
                elapsed_ms = 0
            self.cursor_ms = min(self.get_max_length(self.play_is_solo), self.play_start_pos + elapsed_ms)
        self.is_playing = False
        if hasattr(self, "playback_thread") and self.playback_thread:
            self.playback_thread.active = False
        self.reset_playback()
        self.announce("Stopped")

    def add_new_track(self):
        self.save_state()
        new_track = Track(f"Track {len(self.tracks) + 1}")
        self.tracks.append(new_track)
        self.active_track_idx, self.cursor_ms = len(self.tracks) - 1, 0
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
        if not self.tracks:
            return
        self.active_track_idx = (self.active_track_idx + delta) % len(self.tracks)
        tr = self.current_track
        state = ", Muted" if tr.muted else (", Solo" if tr.solo else "")
        self.announce(f"{tr.name}, {tr.get_length_ms()} ms{state}")

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
        mix_pcm_buffers(self.current_track.pcm, self.clipboard, offset_bytes=ms_to_bytes(self.cursor_ms))
        self.cursor_ms = 0
        self.announce("Mixed. Cursor reset to 0.")

    def insert_silence(self):
        ans = kbt(None, "Insert Silence", "Silence duration in ms:", "100")
        if not ans:
            return
        try:
            dur = int(ans.strip())
        except ValueError:
            return
        if dur <= 0:
            return
        self.save_state()
        cb = ms_to_bytes(self.cursor_ms)
        if cb > len(self.current_track.pcm):
            self.current_track.pcm.extend(b"\x00" * (cb - len(self.current_track.pcm)))
        self.current_track.pcm[cb:cb] = b"\x00" * ms_to_bytes(dur)
        self.cursor_ms = 0
        self.announce(f"Inserted {dur} ms. Cursor reset to 0.")

    def new_project(self):
        if self.dirty and not vb.confirm("New Project", "Discard unsaved changes and start a new project?", window=self.w):
            return
        self.stop_play()
        self.tracks = [Track("Track 1")]
        self.active_track_idx, self.cursor_ms = 0, 0
        self.marker_start_ms, self.marker_end_ms = 0, 0
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.project_path, self.dirty = None, False
        self.announce("New empty project ready.")

    def open_discrete_mixer(self):
        form = vb.form(self.w, config={"label": "Discrete Track Mixer", "adjacent_submit": False})
        for idx, tr in enumerate(self.tracks):
            form.add(f"tr_{idx}", "check", value=not tr.muted, label=f"{tr.name} ({tr.get_length_ms()} ms)")
        form.add("play_sel", "button", label="Play Selected Tracks")
        form.add("mix_sel", "button", label="Mixdown Selected to New Track")
        form.add("close", "button", label="Close")

        action = form.open()
        if action in (-1, "close"):
            return
        selected = [bool(form.get(f"tr_{idx}")) for idx in range(len(self.tracks))]
        chosen = [self.tracks[idx] for idx, on in enumerate(selected) if on]
        if not chosen:
            vb.warning_box("No Selection", "Select at least one track.", window=self.w)
            return
        if action == "play_sel":
            for idx, tr in enumerate(self.tracks):
                tr.solo = selected[idx]
            self.toggle_play(all_tracks=True)
        elif action == "mix_sel":
            max_len = max([len(tr.pcm) for tr in chosen], default=0)
            if max_len == 0:
                vb.warning_box("Empty Tracks", "Selected tracks contain no audio.", window=self.w)
                return
            self.save_state()
            mixed_tr = Track(f"Mixdown ({len(chosen)} tr)")
            mixed_tr.pcm = bytearray(b"\x00" * max_len)
            for tr in chosen:
                mix_pcm_buffers(mixed_tr.pcm, tr.pcm, offset_bytes=0, overlay_volume=tr.volume / 100.0)
            self.tracks.append(mixed_tr)
            self.active_track_idx, self.cursor_ms = len(self.tracks) - 1, 0
            self.announce(f"Created {mixed_tr.name}")

    def open_toolbar_menu(self):
        tr = self.current_track
        form = vb.form(self.w, config={"label": "Music Tracker Workspace", "adjacent_submit": False})
        form.add("section", "tab", choices=["File", "Track & Mixer", "Edit", "Studio"], value=0, label="Workspace Tab")

        # Tab 0: File & Settings
        form.add("file_cmd", "list", value=0, choices=[
            "Save Project (Ctrl+S)",
            "Save As / Export Multi-Format (Ctrl+Shift+S)",
            "Open / Import File (Ctrl+O)",
            "New Empty Project",
            "Settings (F1)",
        ], label="File Commands", tab_page="File")
        form.add("run_file", "button", label="Execute File Command", tab_page="File")

        # Tab 1: Track & Mixer (inline vb controls + track action list)
        form.add("bpm", "input", value=str(self.bpm), number_only=True, label="Tempo (BPM)", tab_page="Track & Mixer")
        form.add("volume", "slider", value=int(tr.volume), min=0, max=200, step=5, unit="%",
                 label=f"{tr.name} Volume", tab_page="Track & Mixer")
        form.add("muted", "switch", value=bool(tr.muted), label="Mute Track", tab_page="Track & Mixer")
        form.add("solo", "switch", value=bool(tr.solo), label="Solo Track", tab_page="Track & Mixer")
        form.add("apply_track", "button", label="Apply Track & Tempo", tab_page="Track & Mixer")
        form.add("track_cmd", "list", value=0, choices=[
            "New Track (Ctrl+N)",
            "Delete Current Track (Ctrl+F4)",
            "Discrete Track Mixer (Ctrl+Space)",
        ], label="Track Actions", tab_page="Track & Mixer")
        form.add("run_track", "button", label="Run Track Action", tab_page="Track & Mixer")

        # Tab 2: Edit
        form.add("edit_cmd", "list", value=0, choices=[
            "Set Selection Start (-)",
            "Set Selection End (=)",
            "Select All (Ctrl+A)",
            "Undo (Ctrl+Z)",
            "Redo (Ctrl+Y)",
            "Cut (Ctrl+X)",
            "Copy (Ctrl+C)",
            "Paste (Ctrl+V)",
            "Mix Paste (Ctrl+M)",
            "Insert Silence...",
        ], label="Edit Commands", tab_page="Edit")
        form.add("run_edit", "button", label="Run Edit Command", tab_page="Edit")

        # Tab 3: Studio
        form.add("studio_cmd", "list", value=0, choices=[
            "Arranger & Instrument Studio (I)",
            "New Input Score (P)",
            "Continue Input Mode (Ctrl+P)",
            "Play Live Instruments (Alt+F1)",
            "VST3 Sound & Presets (Ctrl+F1)",
        ], label="Studio Commands", tab_page="Studio")
        form.add("run_studio", "button", label="Open Studio Command", tab_page="Studio")

        form.add("close", "button", label="Close")

        action = form.open()
        if action in (-1, "close"):
            return
        if action == "run_file":
            sel = int(form.get("file_cmd") or 0)
            if sel == 0:
                self.save_project(save_as=False)
            elif sel == 1:
                self.save_project(save_as=True)
            elif sel == 2:
                self.load_project(append=False)
            elif sel == 3:
                self.new_project()
            elif sel == 4:
                self.open_settings()
        elif action == "apply_track":
            bpm_str = str(form.get("bpm") or "").strip()
            if bpm_str.isdigit() and 20 <= int(bpm_str) <= 400:
                self.bpm = int(bpm_str)
            tr.volume = max(0, min(200, int(form.get("volume") or 100)))
            tr.muted = bool(form.get("muted"))
            tr.solo = bool(form.get("solo"))
            self.dirty = True
            self.announce(f"Updated {tr.name}: {self.bpm} BPM, volume {tr.volume}%")
        elif action == "run_track":
            sel = int(form.get("track_cmd") or 0)
            if sel == 0:
                self.add_new_track()
            elif sel == 1:
                self.delete_track()
            elif sel == 2:
                self.open_discrete_mixer()
        elif action == "run_edit":
            sel = int(form.get("edit_cmd") or 0)
            if sel == 0:
                self.marker_start_ms = self.cursor_ms
                self.announce(f"Start: {format_time(self.marker_start_ms)}")
            elif sel == 1:
                self.marker_end_ms = self.cursor_ms
                self.announce(f"End: {format_time(self.cursor_ms)}, {abs(self.marker_end_ms - self.marker_start_ms)} ms")
            elif sel == 2:
                self.marker_start_ms, self.marker_end_ms = 0, self.current_track.get_length_ms()
                self.announce("Selected all")
            elif sel == 3:
                self.trigger_undo()
            elif sel == 4:
                self.trigger_redo()
            elif sel == 5:
                self.cut_selection()
            elif sel == 6:
                self.copy_selection()
            elif sel == 7:
                self.paste_clipboard()
            elif sel == 8:
                self.mix_clipboard()
            elif sel == 9:
                self.insert_silence()
        elif action == "run_studio":
            sel = int(form.get("studio_cmd") or 0)
            if sel == 0:
                self.open_instrument_studio()
            elif sel == 1:
                self.new_input_score()
            elif sel == 2:
                self.open_import_mode()
            elif sel == 3:
                self.launch_live_midi_instruments()
            elif sel == 4:
                self.open_vst3_quick_controls()

    def open_vst3_quick_controls(self):
        import setting
        if self.is_playing:
            self.stop_play()
        pref = self.current_track.import_state.inst_type if self.current_track.import_state is not None else "piano"
        setting.open_quick_vst3_controls(self.w, preferred_inst=pref)
        self.announce("Back to Music Tracker Editor")

    def _export_by_format(self, fmt_id, path):
        if fmt_id == "inv":
            multiformat.write_project(path, self, encrypt=True)
            self.project_path, self.dirty = path, False
            return "Encrypted INV project saved"
        if fmt_id == "mpc":
            multiformat.write_mpc(path, self)
            self.project_path, self.dirty = path, False
            return "MPC pattern saved"
        if fmt_id == "wav":
            pcm = self.render_mixdown(solo_current=False)
            if not pcm:
                raise ValueError("Project audio is empty.")
            multiformat.export_wav(path, pcm)
            return "WAV audio exported"
        if fmt_id == "mid":
            multiformat.export_midi(path, self)
            return "MIDI file exported"
        if fmt_id == "txt":
            if self.current_track.import_state is None or not self.current_track.import_state.items:
                raise ValueError("Current track has no editable sequence to export.")
            from mte_importmode import ImportModeEditor
            ed = ImportModeEditor.__new__(ImportModeEditor)
            ed.app, ed.track, ed.st = self, self.current_track, self.current_track.import_state
            multiformat.export_sequence_txt(path, ed.build_sequence_string())
            return "Sequence text exported"
        raise ValueError(f"Unsupported export format: {fmt_id}")

    def save_project(self, save_as=False):
        if not save_as and self.project_path:
            fmt_id = multiformat.detect_format(self.project_path)
            if fmt_id in ("inv", "mpc"):
                try:
                    msg = self._export_by_format(fmt_id, self.project_path)
                    self.announce(msg)
                except Exception as exc:
                    vb.error_box("Save Error", f"Could not save project: {exc}", window=self.w)
                return

        default_path = self.project_path or os.path.abspath("project.inv")
        fmt_labels = [entry[1] for entry in multiformat.SAVE_FORMATS]
        form = vb.form(self.w, config={"label": "Save & Export Project", "adjacent_submit": False})
        form.add("fmt", "combo", value=0, choices=fmt_labels, label="Format")
        form.add("path", "input", value=default_path, label="Output File Path")
        form.add("browse", "button", label="Browse...")
        form.add("save", "button", label="Save")
        form.add("cancel", "button", label="Cancel")

        while True:
            action = form.open()
            if action in (-1, "cancel"):
                return
            fmt_idx = int(form.get("fmt") or 0)
            fmt_id, fmt_label, ext, wildcard = multiformat.SAVE_FORMATS[fmt_idx]
            if action == "browse":
                cur_name = os.path.basename(str(form.get("path") or f"project{ext}"))
                stem = os.path.splitext(cur_name)[0] or "project"
                try:
                    picked = multiformat.save_file("Save & Export", stem + ext, wildcard)
                except Exception:
                    vb.info_box("File Browser", "Native dialog unavailable. Edit the path field directly.", window=self.w)
                    picked = None
                if picked:
                    form.set("path", picked)
                continue

            fname = str(form.get("path") or "").strip()
            if not fname:
                vb.warning_box("Missing Path", "Enter or browse a destination file path.", window=self.w)
                continue
            if not fname.lower().endswith(ext):
                fname += ext
            try:
                msg = self._export_by_format(fmt_id, fname)
            except Exception as exc:
                vb.error_box("Save Error", f"Could not save file: {exc}", window=self.w)
                continue
            self.announce(f"{msg}: {os.path.basename(fname)}")
            return

    def load_project(self, append=False):
        if not append and self.dirty:
            if not vb.confirm("Unsaved Changes", "Current project has unsaved changes. Continue?", window=self.w):
                return

        form = vb.form(self.w, config={"label": "Open / Import File", "adjacent_submit": False})
        form.add("path", "input", value="", label="File Path")
        form.add("browse", "button", label="Browse...")
        form.add("mode", "combo", value=1 if append else 0, choices=[
            "Replace Current Project",
            "Append as New Track(s)",
            "Import into Current Track",
        ], label="Open Mode")
        form.add("open", "button", label="Open")
        form.add("cancel", "button", label="Cancel")

        while True:
            action = form.open()
            if action in (-1, "cancel"):
                return
            if action == "browse":
                try:
                    picked = multiformat.open_file("Open Project or Music File")
                except Exception:
                    picked = kbt(None, "Open File", "Enter file path:", "", file_dialog=True)
                if picked:
                    form.set("path", picked)
                continue

            fname = str(form.get("path") or "").strip()
            if not fname or not os.path.isfile(fname):
                vb.warning_box("File Not Found", "Please select an existing file.", window=self.w)
                continue
            mode = int(form.get("mode") or 0)
            break

        fmt = multiformat.detect_format(fname)
        if fmt in ("midi", "musicxml"):
            self.extract_midi_to_string(filepath=fname)
            return
        if fmt == "txt":
            try:
                seq = multiformat.import_sequence_txt(fname)
            except Exception as exc:
                vb.error_box("Open Error", f"Could not read text sequence: {exc}", window=self.w)
                return
            self.run_step_sequencer("piano", sequence=seq)
            return
        if fmt == "wav":
            try:
                pcm = multiformat.import_wav(fname)
            except Exception as exc:
                vb.error_box("Open Error", f"Could not import WAV: {exc}", window=self.w)
                return
            self.stop_play()
            self.save_state()
            if mode == 2:
                mix_pcm_buffers(self.current_track.pcm, pcm, offset_bytes=ms_to_bytes(self.cursor_ms))
            else:
                wav_track = Track(os.path.splitext(os.path.basename(fname))[0])
                wav_track.pcm = pcm
                if mode == 0:
                    self.tracks = [wav_track]
                    self.active_track_idx = 0
                else:
                    self.tracks.append(wav_track)
                    self.active_track_idx = len(self.tracks) - 1
            self.cursor_ms = 0
            self.announce(f"Imported WAV: {os.path.basename(fname)}")
            return

        try:
            if fmt == "mpc":
                metadata, tracks = multiformat.read_mpc(fname, Track)
            else:
                metadata, tracks = multiformat.read_project(fname, Track)
        except Exception as exc:
            vb.error_box("Open Error", f"Could not open project: {exc}", window=self.w)
            return

        self.stop_play()
        self.save_state()
        if mode == 1:
            self.tracks.extend(tracks)
        else:
            self.tracks = tracks
            self.bpm = metadata.get("bpm", 120)
            self.time_sig_numerator = metadata.get("time_sig_numerator", 4)
            self.time_sig_denominator = metadata.get("time_sig_denominator", 4)
            self.time_sig = self.time_sig_numerator * 4 / self.time_sig_denominator
            self.project_path = fname if fmt in ("inv", "mpc") else None
            self.dirty = False

        self.active_track_idx = min(metadata.get("active_track_idx", 0), len(self.tracks) - 1)
        self.cursor_ms = metadata.get("cursor_ms", 0)
        self.announce(f"{len(self.tracks)} tracks ready")
        if mode == 0:
            if self.current_track.import_state is None:
                score_index = next((idx for idx, tr in enumerate(self.tracks)
                                    if tr.import_state is not None), None)
                if score_index is not None:
                    self.active_track_idx = score_index
            if self.current_track.import_state is not None:
                self.open_import_mode()

    def run_player_loop(self):
        self.announce("Music Tracker Editor. Track 1. Backspace for workspace, F1 for Settings, Ctrl+F1 for VST3 Presets, Alt+F1 for Live Instruments.")

        while True:
            self.w.frameUpdate()
            if self.w.keyPressed("exit"):
                if self.dirty and not vb.confirm("Exit", "You have unsaved changes. Exit anyway?", window=self.w):
                    continue
                self.stop_play()
                break

            ctrl = self.w.keyPressing("lcontrol") or self.w.keyPressing("rcontrol")
            shift = self.w.keyPressing("lshift") or self.w.keyPressing("rshift")

            if self.w.keyPressed("alt+f1"):
                self.launch_live_midi_instruments()
                continue
            if ctrl and self.w.keyPressed("f1"):
                self.open_vst3_quick_controls()
                continue
            if self.w.keyPressed("f1") and not (ctrl or shift or self.w.keyPressing("alt") or self.w.keyPressing("meta")):
                self.open_settings()
                continue
            if self.w.keyPressed("backspace"):
                self.open_toolbar_menu()
                continue
            if self.w.keyPressed("i") and not ctrl:
                self.open_instrument_studio()
                continue
            if self.w.keyPressed("p") and not ctrl:
                self.new_input_score()
                continue
            if ctrl and self.w.keyPressed("p"):
                self.open_import_mode()
                continue
            if ctrl and self.w.keyPressed("z"):
                self.trigger_undo()
                continue
            if ctrl and self.w.keyPressed("y"):
                self.trigger_redo()
                continue
            if ctrl and self.w.keyPressed("n"):
                self.add_new_track()
                continue
            if ctrl and self.w.keyPressed("f4"):
                self.delete_track()
                continue

            if self.w.keyPressed("tab") and ctrl:
                self.switch_track(-1 if shift else 1)
                continue
            elif self.w.keyPressed("tab") and not ctrl:
                self.seek_mode_idx = (self.seek_mode_idx + (-1 if shift else 1)) % len(self.seek_modes)
                self.announce(f"Seek mode: {self.seek_modes[self.seek_mode_idx]}")
                continue

            if self.w.keyPressed("-") and not ctrl:
                self.marker_start_ms = self.cursor_ms
                self.announce(f"Start: {format_time(self.marker_start_ms)}")
            elif self.w.keyPressed("=") and not ctrl:
                self.marker_end_ms = self.cursor_ms
                self.announce(f"End: {format_time(self.cursor_ms)}, {abs(self.marker_end_ms - self.marker_start_ms)} ms")

            if ctrl and self.w.keyPressed("a"):
                self.marker_start_ms, self.marker_end_ms = 0, self.current_track.get_length_ms()
                self.announce("Selected all")
            elif ctrl and self.w.keyPressed("x"):
                self.cut_selection()
            elif ctrl and self.w.keyPressed("c"):
                self.copy_selection()
            elif ctrl and self.w.keyPressed("v"):
                self.paste_clipboard()
            elif ctrl and self.w.keyPressed("m"):
                self.mix_clipboard()
            elif ctrl and self.w.keyPressed("s"):
                self.save_project(save_as=shift)
            elif ctrl and self.w.keyPressed("o"):
                self.load_project(append=shift)

            if self.w.keyPressed("b") and not ctrl:
                b_ms = (60.0 / self.bpm) * 1000.0
                self.cursor_ms = int(round(self.cursor_ms / b_ms) * b_ms)
                self.announce(f"Snap: {format_time(self.cursor_ms)}")

            if self.w.keyPressed("space"):
                if ctrl:
                    self.open_discrete_mixer()
                else:
                    self.toggle_play(all_tracks=not shift)
                continue

            if self.w.keyPressed("left") or self.w.keyPressed("right"):
                mode = self.seek_modes[self.seek_mode_idx]
                step_ms = 100
                if mode == "10 ms":
                    step_ms = 10
                elif mode == "100 ms":
                    step_ms = 100
                elif mode == "1 sec":
                    step_ms = 1000
                elif mode == "1 Beat":
                    step_ms = int((60.0 / self.bpm) * 1000.0)
                elif mode == "1 Bar":
                    step_ms = int((60.0 / self.bpm) * 1000.0 * self.time_sig)
                delta = -step_ms if self.w.keyPressed("left") else step_ms

                if self.is_playing:
                    was_all = not self.play_is_solo
                    current_pos = self.cursor_ms
                    if self.preview:
                        try:
                            current_pos = self.play_start_pos + self.preview.position
                        except Exception:
                            pass
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
