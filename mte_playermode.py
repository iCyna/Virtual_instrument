import os
import json
import time
import threading
from pyaudiogaming import menu
from pyaudiogaming.inputBox import kbt
from pyaudiogaming.sound_pool import sound

import mte
from mte import (
    Track, ms_to_bytes, bytes_to_ms, format_time, 
    mix_pcm_buffers, BYTES_PER_FRAME
)

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
                    except Exception:
                        pos_ms = 0
                    
                    pushed_ms = bytes_to_ms(current_byte - start_byte)
                    if pushed_ms - pos_ms > 400: 
                        time.sleep(0.02)
                    else:
                        break
                        
            while self.app.is_playing and self.active:
                try:
                    pos_ms = self.app.preview.position
                except Exception:
                    pos_ms = 0
                
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


class PlayerModeMixin:
    """Quản lý toàn bộ thao tác Player, Track, Vùng chọn, Clipboard, Toolbar và Phím tắt"""

    def reset_playback(self):
        self.is_playing = False
        if hasattr(self, 'playback_thread') and self.playback_thread:
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
        if len(self.undo_stack) > 15:
            self.undo_stack.pop(0)
        state = {"active_idx": self.active_track_idx, "cursor": self.cursor_ms, "tracks": []}
        for t in self.tracks:
            nt = Track(t.name)
            nt.pcm = bytearray(t.pcm)
            nt.volume, nt.pan, nt.muted, nt.solo = t.volume, t.pan, t.muted, t.solo
            nt.import_state = t.import_state
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
            nt.import_state = t.import_state
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
            nt.import_state = t.import_state
            c_state["tracks"].append(nt)
        push_stack.append(c_state)
        self.restore_state(pop_stack.pop())
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
        for t in self.tracks:
            if (has_solo and not t.solo) or (not has_solo and t.muted):
                continue
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
                try:
                    elapsed_ms = self.preview.position
                except Exception:
                    elapsed_ms = 0
                self.cursor_ms = min(self.get_max_length(self.play_is_solo), self.play_start_pos + elapsed_ms)
                
        self.is_playing = False
        if hasattr(self, 'playback_thread') and self.playback_thread:
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
        if not self.tracks:
            return
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
        if not ans:
            return
        try:
            dur = int(ans.strip())
        except ValueError:
            return
        if dur <= 0:
            return
        
        self.save_state()
        silence = b"\x00" * ms_to_bytes(dur)
        cb = ms_to_bytes(self.cursor_ms)
        if cb > len(self.current_track.pcm):
            self.current_track.pcm.extend(b"\x00" * (cb - len(self.current_track.pcm)))
        self.current_track.pcm[cb:cb] = silence
        self.cursor_ms = 0
        self.announce(f"Inserted {dur} ms. Cursor reset to 0.")

    def open_discrete_mixer(self):
        """Bảng chọn phát rời rạc hoặc Mixdown các track tùy ý"""
        selected = [not t.muted for t in self.tracks]
        while True:
            m = menu.menu()
            m.init(self.w, "Discrete Track Mixer & Play")
            for i, t in enumerate(self.tracks):
                mark = "[X]" if selected[i] else "[ ]"
                m.append(f"{mark} {t.name} ({t.get_length_ms()} ms)")
            m.append("Play Selected Tracks Only")
            m.append("Mixdown Selected to New Track")
            m.append("Close")
            m.open()

            sel = None
            while sel is None:
                self.w.frameUpdate()
                sel = m.frameUpdate()

            if sel == -1 or sel == len(self.tracks) + 2:
                break
            elif 0 <= sel < len(self.tracks):
                selected[sel] = not selected[sel]
                state_str = "Selected" if selected[sel] else "Unselected"
                self.announce(f"{self.tracks[sel].name} {state_str}")
            elif sel == len(self.tracks):
                chosen_tracks = [self.tracks[i] for i in range(len(self.tracks)) if selected[i]]
                if not chosen_tracks:
                    self.announce("No tracks selected.")
                    continue
                for i, t in enumerate(self.tracks):
                    t.solo = selected[i]
                self.toggle_play(all_tracks=True)
                break
            elif sel == len(self.tracks) + 1:
                chosen_tracks = [self.tracks[i] for i in range(len(self.tracks)) if selected[i]]
                if not chosen_tracks:
                    self.announce("No tracks selected.")
                    continue
                max_len = max([len(t.pcm) for t in chosen_tracks], default=0)
                if max_len == 0:
                    self.announce("Selected tracks are empty.")
                    continue
                self.save_state()
                mixed_tr = Track(f"Mixdown ({len(chosen_tracks)} tr)")
                mixed_tr.pcm = bytearray(b"\x00" * max_len)
                for t in chosen_tracks:
                    mix_pcm_buffers(mixed_tr.pcm, t.pcm, offset_bytes=0, overlay_volume=t.volume / 100.0)
                self.tracks.append(mixed_tr)
                self.active_track_idx = len(self.tracks) - 1
                self.cursor_ms = 0
                self.announce(f"Created {mixed_tr.name}")
                break

    def open_toolbar_menu(self):
        m = menu.menu()
        m.init(self.w, "Toolbar")
        actions = [
            "Set Selection Start (Q)", "Set Selection End (E)", "Select All (Ctrl+A)",
            "Undo (Ctrl+Z)", "Redo (Ctrl+Y)", "Cut (Ctrl+X)", "Copy (Ctrl+C)", "Paste (Ctrl+V)", 
            "Mix Paste (Ctrl+M)", "Insert Silence", "New Track (Ctrl+N)", "Delete Track (Ctrl+F4)", 
            "Arranger & Beat Studio (I)", "Open Import Mode (P)", "Discrete Track Mixer (Ctrl+Space)",
            "Set Tempo (BPM)", "Track Volume", "Toggle Mute", "Toggle Solo", 
            "Save Project (.mte)", "Open Project (.mte)", "Close"
        ]
        for a in actions:
            m.append(a)
        m.open()

        while True:
            self.w.frameUpdate()
            sel = m.frameUpdate()
            if sel is None:
                continue
            if sel == -1 or sel == len(actions) - 1:
                break

            if sel == 0:
                self.marker_start_ms = self.cursor_ms
                self.announce(f"Start: {format_time(self.marker_start_ms)}")
            elif sel == 1:
                self.marker_end_ms = self.cursor_ms
                self.announce(f"End: {format_time(self.cursor_ms)}, {abs(self.marker_end_ms - self.marker_start_ms)} ms")
            elif sel == 2:
                self.marker_start_ms, self.marker_end_ms = 0, self.current_track.get_length_ms()
                self.announce("Selected all")
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
            elif sel == 13: self.open_import_mode()
            elif sel == 14: self.open_discrete_mixer()
            elif sel == 15:
                v = kbt(None, "Tempo", "BPM:", str(self.bpm))
                if v and v.strip().isdigit():
                    self.bpm = int(v.strip())
                    self.announce(f"{self.bpm} BPM")
            elif sel == 16:
                v = kbt(None, "Track Volume", "0 to 200%:", str(self.current_track.volume))
                if v and v.strip().isdigit():
                    self.current_track.volume = max(0, min(200, int(v.strip())))
                    self.announce(f"{self.current_track.volume}%")
            elif sel == 17:
                self.current_track.muted = not self.current_track.muted
                self.announce("Muted" if self.current_track.muted else "Unmuted")
            elif sel == 18:
                self.current_track.solo = not self.current_track.solo
                self.announce("Solo On" if self.current_track.solo else "Solo Off")
            elif sel == 19: self.save_project()
            elif sel == 20: self.load_project(append=False)
            break

    def save_project(self):
        fname = kbt(None, "Save Project", "Config file name (.mte):", "project.mte")
        if not fname:
            return
        if not fname.lower().endswith(".mte"):
            fname += ".mte"

        base_dir, base_name = os.path.dirname(os.path.abspath(fname)), os.path.splitext(os.path.basename(fname))[0]
        proj = {"bpm": self.bpm, "cursor_ms": self.cursor_ms, "tracks": []}
        
        for i, t in enumerate(self.tracks):
            pcm_name = f"{base_name}_tr{i + 1}.pcm"
            with open(os.path.join(base_dir, pcm_name), "wb") as pf:
                pf.write(t.pcm)
            proj["tracks"].append({
                "name": t.name, "volume": t.volume, "pan": t.pan, 
                "muted": t.muted, "solo": t.solo, "pcm_file": pcm_name
            })

        with open(fname, "w", encoding="utf-8") as f:
            json.dump(proj, f, indent=2)
        self.announce("Project saved")

    def load_project(self, append=False):
        fname = kbt(None, "Open Project", "Select .mte file:", "", file_dialog=True)
        if not fname or not os.path.exists(fname):
            return
        try:
            with open(fname, "r", encoding="utf-8") as f:
                proj = json.load(f)
        except Exception:
            self.announce("Error opening file")
            return

        base_dir = os.path.dirname(os.path.abspath(fname))
        self.save_state()
        if not append:
            self.tracks.clear()
            self.bpm = proj.get("bpm", 120)

        for t_info in proj.get("tracks", []):
            tr = Track(t_info.get("name", "Track"))
            tr.volume, tr.muted, tr.solo = t_info.get("volume", 100), t_info.get("muted", False), t_info.get("solo", False)
            pcm_path = os.path.join(base_dir, t_info.get("pcm_file", ""))
            if os.path.exists(pcm_path):
                with open(pcm_path, "rb") as pf:
                    tr.pcm = bytearray(pf.read())
            self.tracks.append(tr)

        if not self.tracks:
            self.tracks.append(Track("Track 1"))
        self.active_track_idx, self.cursor_ms = 0, 0
        self.announce(f"{len(self.tracks)} tracks ready")

    def run_player_loop(self):
        self.announce("Music Tracker Editor. Track 1")

        while True:
            self.w.frameUpdate()
            
            if self.w.keyPressed("exit"):
                self.stop_play()
                break

            ctrl = self.w.keyPressing("lcontrol") or self.w.keyPressing("rcontrol")
            shift = self.w.keyPressing("lshift") or self.w.keyPressing("rshift")

            if self.w.keyPressed("backspace"): self.open_toolbar_menu(); continue
            if self.w.keyPressed("i") and not ctrl: self.open_instrument_studio(); continue
            if self.w.keyPressed("p") and not ctrl: self.open_import_mode(); continue
            if ctrl and self.w.keyPressed("z"): self.trigger_undo(); continue
            if ctrl and self.w.keyPressed("y"): self.trigger_redo(); continue
            if ctrl and self.w.keyPressed("n"): self.add_new_track(); continue
            if ctrl and self.w.keyPressed("f4"): self.delete_track(); continue
                
            if self.w.keyPressed("tab") and ctrl:
                self.switch_track(-1 if shift else 1)
                continue
            elif self.w.keyPressed("tab") and not ctrl:
                self.seek_mode_idx = (self.seek_mode_idx + (-1 if shift else 1)) % len(self.seek_modes)
                self.announce(f"Seek mode: {self.seek_modes[self.seek_mode_idx]}")
                continue
                
            if self.w.keyPressed("q") and not ctrl:
                self.marker_start_ms = self.cursor_ms
                self.announce(f"Start: {format_time(self.marker_start_ms)}")
            elif self.w.keyPressed("e") and not ctrl:
                self.marker_end_ms = self.cursor_ms
                self.announce(f"End: {format_time(self.cursor_ms)}, {abs(self.marker_end_ms - self.marker_start_ms)} ms")
                
            if ctrl and self.w.keyPressed("a"):
                self.marker_start_ms, self.marker_end_ms = 0, self.current_track.get_length_ms()
                self.announce("Selected all")
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

            if self.w.keyPressed("space"):
                if ctrl:
                    self.open_discrete_mixer()
                else:
                    self.toggle_play(all_tracks=not shift)
                continue

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