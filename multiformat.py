"""Unified multi-format I/O: encrypted INV, MPC, MIDI, MusicXML, WAV, TXT, and native dialogs."""
import array
import copy
import html
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import wave
import zipfile
import zlib

from pyaudiogaming import file as pf

# Project-local music21/verovio dependency directory if present.
_LOCAL_DEPS = Path(__file__).resolve().parent / ".mxl_deps"
if _LOCAL_DEPS.is_dir() and str(_LOCAL_DEPS) not in sys.path:
    sys.path.append(str(_LOCAL_DEPS))

SAMPLE_RATE = 44100
CHANNELS = 2
SAMPLE_WIDTH = 2
INV_MAGIC = b"INVENC1\x00"
INV_PASSWORD = "virtual-instrument-inv-key-v1"
MPC_MAGIC = b"MPCV1\x00"
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

FORMAT_MAP = {
    ".inv": "inv",
    ".mte": "mte",
    ".mpc": "mpc",
    ".mid": "midi",
    ".midi": "midi",
    ".mxl": "musicxml",
    ".musicxml": "musicxml",
    ".xml": "musicxml",
    ".wav": "wav",
    ".txt": "txt",
}

SAVE_FORMATS = [
    ("inv", "Encrypted Project (.inv)", ".inv", "INV projects (*.inv)|*.inv"),
    ("mpc", "Music Pattern Container (.mpc)", ".mpc", "MPC patterns (*.mpc)|*.mpc"),
    ("wav", "WAV Audio Mixdown (.wav)", ".wav", "WAV audio (*.wav)|*.wav"),
    ("mid", "Standard MIDI (.mid)", ".mid", "MIDI files (*.mid)|*.mid"),
    ("txt", "Sequence Text (.txt)", ".txt", "Text sequences (*.txt)|*.txt"),
]

OPEN_WILDCARD = (
    "All supported (*.inv;*.mte;*.mpc;*.mid;*.midi;*.mxl;*.musicxml;*.xml;*.wav;*.txt)|"
    "*.inv;*.mte;*.mpc;*.mid;*.midi;*.mxl;*.musicxml;*.xml;*.wav;*.txt|"
    "INV Projects (*.inv;*.mte)|*.inv;*.mte|"
    "MPC Patterns (*.mpc)|*.mpc|"
    "MIDI & MusicXML (*.mid;*.midi;*.mxl;*.musicxml;*.xml)|*.mid;*.midi;*.mxl;*.musicxml;*.xml|"
    "WAV & Text (*.wav;*.txt)|*.wav;*.txt|"
    "All files (*.*)|*.*"
)


def detect_format(path):
    return FORMAT_MAP.get(Path(path).suffix.lower(), "unknown")


# --- Native File Dialogs (Desktop wx with graceful fallback) ---

def save_file(title, filename, wildcard):
    import wx
    from pyaudiogaming import buffer

    buffer.names_window.append(title)
    try:
        dialog = wx.FileDialog(None, title, defaultFile=filename, wildcard=wildcard,
                               style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        try:
            return dialog.GetPath() if dialog.ShowModal() == wx.ID_OK else None
        finally:
            dialog.Destroy()
    finally:
        buffer.names_window.remove(title)


def open_file(title, wildcard=OPEN_WILDCARD):
    import wx
    from pyaudiogaming import buffer

    buffer.names_window.append(title)
    try:
        dialog = wx.FileDialog(None, title, wildcard=wildcard,
                               style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        try:
            return dialog.GetPath() if dialog.ShowModal() == wx.ID_OK else None
        finally:
            dialog.Destroy()
    finally:
        buffer.names_window.remove(title)


# --- Encrypted INV Project Format ---

def _inv_codec(password=INV_PASSWORD):
    return pf.File(password=password, encode=True, aes=True)


def is_encrypted_inv(path):
    try:
        with open(path, "rb") as src:
            return src.read(len(INV_MAGIC)) == INV_MAGIC
    except OSError:
        return False


def _atomic_write(path, payload):
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".inv-", suffix=".tmp", dir=directory or ".")
    os.close(handle)
    try:
        with open(temporary, "wb") as out:
            out.write(payload)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def _build_project_metadata(app, include_pcm=True):
    tracks_meta = []
    for index, track in enumerate(app.tracks):
        entry = dict(
            name=track.name, volume=track.volume, pan=track.pan,
            muted=track.muted, solo=track.solo,
            pcm_file=f"audio/{index}.pcm" if include_pcm else "",
            import_state=vars(track.import_state) if track.import_state is not None else None,
        )
        tracks_meta.append(entry)
    return dict(
        format="virtual-instrument", version=1, bpm=app.bpm,
        time_sig_numerator=getattr(app, "time_sig_numerator", 4),
        time_sig_denominator=getattr(app, "time_sig_denominator", 4),
        cursor_ms=app.cursor_ms, active_track_idx=app.active_track_idx,
        tracks=tracks_meta,
    )


def write_project(path, app, encrypt=True, password=INV_PASSWORD):
    metadata = _build_project_metadata(app, include_pcm=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, track in enumerate(app.tracks):
            archive.writestr(f"audio/{index}.pcm", bytes(track.pcm))
        archive.writestr("project.json", json.dumps(metadata, ensure_ascii=False))
    raw_zip = buf.getvalue()
    if encrypt:
        codec = _inv_codec(password)
        payload = INV_MAGIC + codec.aes_encrypt(codec.cipher.encrypt(raw_zip))
    else:
        payload = raw_zip
    _atomic_write(path, payload)


def _unpack_tracks(metadata, track_factory, state_factory, archive=None, base_dir=None):
    bpm = metadata.get("bpm", 120)
    numerator = metadata.get("time_sig_numerator", 4)
    denominator = metadata.get("time_sig_denominator", 4)
    if not isinstance(bpm, (int, float)) or not 20 <= bpm <= 400:
        raise ValueError("Invalid BPM")
    if not isinstance(numerator, int) or numerator <= 0 or denominator not in (2, 4, 8, 16):
        raise ValueError("Invalid time signature")
    tracks = []
    for info in metadata.get("tracks", []):
        track = track_factory(info.get("name", "Track"))
        for key, default in [("volume", 100), ("pan", 0), ("muted", False), ("solo", False)]:
            setattr(track, key, info.get(key, default))
        pcm_file = info.get("pcm_file", "")
        if archive is not None and pcm_file and pcm_file in archive.namelist():
            track.pcm = bytearray(archive.read(pcm_file))
        elif pcm_file and base_dir:
            full_pcm = os.path.join(base_dir, pcm_file)
            if os.path.isfile(full_pcm):
                with open(full_pcm, "rb") as audio:
                    track.pcm = bytearray(audio.read())
        state = info.get("import_state")
        if state is not None:
            track.import_state = state_factory(state.get("inst_type", "piano"))
            for key in vars(track.import_state):
                if key in state:
                    setattr(track.import_state, key, state[key])
        tracks.append(track)
    if not tracks:
        raise ValueError("Project contains no tracks")
    return metadata, tracks


def read_project(path, track_factory, state_factory=None, password=INV_PASSWORD):
    if state_factory is None:
        from mte_importmode import ImportModeState
        state_factory = ImportModeState

    with open(path, "rb") as src:
        raw = src.read()

    archive = None
    try:
        if raw.startswith(INV_MAGIC):
            codec = _inv_codec(password)
            try:
                decrypted = codec.cipher.decrypt(codec.aes_decrypt(raw[len(INV_MAGIC):]))
            except Exception as exc:
                raise ValueError(f"Could not decrypt INV project: {exc}")
            archive = zipfile.ZipFile(io.BytesIO(decrypted))
            metadata = json.loads(archive.read("project.json"))
            if metadata.get("format") != "virtual-instrument" or metadata.get("version") != 1:
                raise ValueError("Unsupported INV format/version")
        elif zipfile.is_zipfile(io.BytesIO(raw)):
            archive = zipfile.ZipFile(io.BytesIO(raw))
            metadata = json.loads(archive.read("project.json"))
            if metadata.get("format") != "virtual-instrument" or metadata.get("version") != 1:
                raise ValueError("Unsupported INV format/version")
        else:
            metadata = json.loads(raw.decode("utf-8"))
        return _unpack_tracks(metadata, track_factory, state_factory, archive=archive,
                              base_dir=os.path.dirname(os.path.abspath(path)))
    finally:
        if archive is not None:
            archive.close()


# --- MPC (Music Pattern Container) Format ---

def write_mpc(path, app):
    metadata = _build_project_metadata(app, include_pcm=False)
    metadata["format"] = "mpc-pattern"
    payload = MPC_MAGIC + zlib.compress(json.dumps(metadata, ensure_ascii=False).encode("utf-8"), level=6)
    _atomic_write(path, payload)


def read_mpc(path, track_factory, state_factory=None):
    if state_factory is None:
        from mte_importmode import ImportModeState
        state_factory = ImportModeState
    with open(path, "rb") as src:
        raw = src.read()
    if raw.startswith(MPC_MAGIC):
        metadata = json.loads(zlib.decompress(raw[len(MPC_MAGIC):]).decode("utf-8"))
    else:
        metadata = json.loads(raw.decode("utf-8"))
    if "tracks" not in metadata:
        raise ValueError("Invalid MPC pattern file")
    return _unpack_tracks(metadata, track_factory, state_factory)


# --- WAV Audio Import / Export ---

def export_wav(path, pcm_bytes, sample_rate=SAMPLE_RATE, channels=CHANNELS, sample_width=SAMPLE_WIDTH):
    data = bytes(pcm_bytes)
    frame_size = channels * sample_width
    valid = len(data) - (len(data) % frame_size)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(data[:valid])


def import_wav(path):
    with wave.open(path, "rb") as wf:
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())
    if sw != 2:
        raise ValueError("Only 16-bit PCM WAV files are supported.")
    if ch == 1:
        mono = array.array("h", frames)
        stereo = array.array("h")
        for sample in mono:
            stereo.append(sample)
            stereo.append(sample)
        return bytearray(stereo.tobytes())
    if ch == 2:
        return bytearray(frames)
    raise ValueError(f"Unsupported WAV channel count: {ch}")


# --- Sequence Text Import / Export ---

def export_sequence_txt(path, seq_str):
    _atomic_write(path, str(seq_str).encode("utf-8"))


def import_sequence_txt(path):
    with open(path, "r", encoding="utf-8") as src:
        return src.read()


# --- Standard MIDI Import / Export ---

def import_midi_to_sequence(path, inst_choice="piano", progress_cb=None):
    import mido

    mid = mido.MidiFile(path)
    notes = []
    active_notes = {ch: {} for ch in range(16)}
    pedal_held = {ch: [] for ch in range(16)}
    vol = {ch: 127 for ch in range(16)}
    expr = {ch: 127 for ch in range(16)}
    pedal_down = {ch: False for ch in range(16)}
    soft_down = {ch: False for ch in range(16)}

    cur_sec = 0.0
    total_len = mid.length if mid.length > 0 else 1.0

    for msg in mid:
        cur_sec += msg.time
        if progress_cb is not None:
            progress_cb(min(100, max(0, int((cur_sec / total_len) * 100))))
        if not hasattr(msg, "channel"):
            continue
        ch = msg.channel
        if msg.type == "control_change":
            if msg.control == 7:
                vol[ch] = msg.value
            elif msg.control == 11:
                expr[ch] = msg.value
            elif msg.control == 64:
                if msg.value >= 64 and not pedal_down[ch]:
                    pedal_down[ch] = True
                elif msg.value < 64 and pedal_down[ch]:
                    pedal_down[ch] = False
                    for info in pedal_held[ch]:
                        notes.append(dict(start=info["start"], end=cur_sec, note=info["note"], vel=info["vel"]))
                    pedal_held[ch].clear()
            elif msg.control == 67:
                soft_down[ch] = msg.value >= 64
        elif msg.type == "note_on" and msg.velocity > 0:
            active_notes[ch].setdefault(msg.note, [])
            soft_mult = 0.7 if soft_down[ch] else 1.0
            baked = msg.velocity * (vol[ch] / 127.0) * (expr[ch] / 127.0) * soft_mult
            active_notes[ch][msg.note].append(dict(start=cur_sec, vel=baked, note=msg.note))
        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            if active_notes[ch].get(msg.note):
                info = active_notes[ch][msg.note].pop(0)
                if pedal_down[ch]:
                    pedal_held[ch].append(info)
                else:
                    notes.append(dict(start=info["start"], end=cur_sec, note=info["note"], vel=info["vel"]))

    for ch in range(16):
        for info in pedal_held[ch]:
            notes.append(dict(start=info["start"], end=cur_sec, note=info["note"], vel=info["vel"]))
        for nlist in active_notes[ch].values():
            for info in nlist:
                notes.append(dict(start=info["start"], end=cur_sec, note=info["note"], vel=info["vel"]))

    notes.sort(key=lambda item: item["start"])
    max_v = max((item["vel"] for item in notes), default=1)
    scale = 95.0 / max_v if max_v > 0 else 1.0
    result = []
    for item in notes:
        start_ms = int(round(item["start"] * 1000))
        dur_ms = max(10, int(round((item["end"] - item["start"]) * 1000)))
        midi_num = item["note"]
        nstr = str(midi_num) if "drum" in inst_choice else f"{NOTE_NAMES[midi_num % 12]}{(midi_num // 12) - 1}"
        fvel = max(1, min(127, int(round(item["vel"] * scale))))
        result.append(f"{nstr}@{start_ms}-{dur_ms}-{fvel}")
    if progress_cb is not None:
        progress_cb(100)
    return " ".join(result)


def export_midi(path, app):
    import mido
    from mte import parse_sequence_to_events
    from mte_importmode import ImportModeEditor

    mid = mido.MidiFile(ticks_per_beat=480)
    tempo_us = mido.bpm2tempo(max(20, min(400, int(app.bpm))))
    exported_tracks = 0

    for idx, track in enumerate(app.tracks):
        if track.import_state is None or not track.import_state.items:
            continue
        editor = ImportModeEditor.__new__(ImportModeEditor)
        editor.app, editor.track, editor.st = app, track, track.import_state
        seq_str = editor.build_sequence_string()
        events, total_ms = parse_sequence_to_events(seq_str, track.import_state.inst_type, app.bpm)
        if not events:
            continue
        mtr = mido.MidiTrack()
        mtr.append(mido.MetaMessage("track_name", name=track.name, time=0))
        if exported_tracks == 0:
            mtr.append(mido.MetaMessage("set_tempo", tempo=tempo_us, time=0))
        chan = 9 if "drum" in track.import_state.inst_type else (idx % 16)
        if chan == 9 and "drum" not in track.import_state.inst_type:
            chan = 0
        last_tick = 0
        for ev_ms, kind, note_num, vel in events:
            tick = int(round(mido.second2tick(ev_ms / 1000.0, mid.ticks_per_beat, tempo_us)))
            delta = max(0, tick - last_tick)
            last_tick = tick
            if kind == "on":
                mtr.append(mido.Message("note_on", channel=chan, note=int(note_num), velocity=int(vel), time=delta))
            else:
                mtr.append(mido.Message("note_off", channel=chan, note=int(note_num), velocity=0, time=delta))
        mid.tracks.append(mtr)
        exported_tracks += 1

    if exported_tracks == 0:
        raise ValueError("No editable score tracks available to export as MIDI.")
    mid.save(path)


# --- MusicXML (.mxl / .musicxml / .xml) ---

def load_score(path):
    from music21 import converter
    score = converter.parse(str(path))
    if not score.parts:
        raise ValueError("The file has no musical parts")
    return score


def _merge_playback_ties(score):
    """Merge each tied pitch independently, including changing chord voicings."""
    from music21 import stream
    timing = {id(entry["element"]): entry["durationSeconds"] * 1000
              for entry in score.flatten().secondsMap}
    for part in score.parts:
        active = {}
        for element in list(part.recurse().notes):
            site = element.activeSite
            voice = site if isinstance(site, stream.Voice) else None
            lane = voice.id if voice is not None else None
            onset = element.getOffsetInHierarchy(part)
            if element.isChord:
                if not any(n.tie for n in element.notes):
                    continue
                local_offset = element.offset
                site.remove(element)
                notes = [copy.deepcopy(n) for n in element.notes]
                for n in notes:
                    n.duration = copy.deepcopy(element.duration)
                    n.volume = copy.deepcopy(element.volume)
                    n.articulations = copy.deepcopy(element.articulations)
                    n._notation_source = getattr(element, "_notation_source", None)
                    n._playback_legato = getattr(element, "_playback_legato", False)
                    site.insert(local_offset, n)
            else:
                notes = [element]
            for n in notes:
                pitch_key = (lane, n.pitch.nameWithOctave)
                tie_type = n.tie.type if n.tie else None
                previous = active.get(pitch_key)
                end = onset + n.quarterLength
                if tie_type in ("continue", "stop") and previous and previous[1] == onset:
                    previous[0].quarterLength += n.quarterLength
                    previous[0]._playback_tie_release_ms = timing[id(element)]
                    previous[0]._playback_release_articulations = copy.deepcopy(n.articulations)
                    previous[0]._playback_legato = getattr(n, "_playback_legato", False)
                    site.remove(n)
                    first = previous[0]
                else:
                    first = n
                if tie_type in ("start", "continue"):
                    active[pitch_key] = (first, end)
                else:
                    active.pop(pitch_key, None)
                n.tie = None


def _playback_score(score, *, expand_repeats=True):
    """Realize notation on a copy, shared by track import and editor playback."""
    from music21 import duration, expressions, key, spanner

    performed = copy.deepcopy(score)
    for slur in performed.recurse().getElementsByClass(spanner.Slur):
        for element in slur.getSpannedElements()[:-1]:
            element._playback_legato = True
    if expand_repeats:
        performed = performed.expandRepeats()
    _merge_playback_ties(performed)
    for part in performed.parts:
        pending_graces = []
        for element in list(part.recurse().notesAndRests):
            if element.duration.isGrace:
                pending_graces.append(element)
                continue
            if pending_graces:
                group = [g for g in pending_graces if g.activeSite is element.activeSite]
                if group:
                    site = element.activeSite
                    onset = element.offset
                    stolen = min(float(element.quarterLength) / 4, 0.25)
                    for index, grace in enumerate(group):
                        grace.duration = duration.Duration(stolen / len(group))
                        grace._playback_ornament = True
                        site.setElementOffset(grace, onset + index * stolen / len(group))
                    element.quarterLength -= stolen
                    site.setElementOffset(element, onset + stolen)
                pending_graces = []
            if element.isNote and any(isinstance(e, expressions.Ornament)
                                      for e in element.expressions):
                site = element.activeSite
                onset = element.offset
                realized = expressions.realizeOrnaments(
                    element, keySig=element.getContextByClass(key.KeySignature))
                site.remove(element)
                for played in realized:
                    played._notation_source = getattr(element, "_notation_source", None)
                    played._playback_ornament = True
                    played._playback_legato = getattr(element, "_playback_legato", False)
                    played.articulations = copy.deepcopy(element.articulations)
                    site.insert(onset, played)
                    onset += played.quarterLength
    return performed


def _duration_ms(entry):
    element = entry["element"]
    dur = entry["durationSeconds"] * 1000
    release_ms = getattr(element, "_playback_tie_release_ms", dur)
    marks = {type(a).__name__ for a in getattr(
        element, "_playback_release_articulations", element.articulations)}
    if "Staccatissimo" in marks:
        gate = 0.20
    elif "DetachedLegato" in marks or {"Staccato", "Tenuto"} <= marks:
        gate = 0.65
    elif "Staccato" in marks:
        gate = 0.40
    elif "Spiccato" in marks:
        gate = 0.30
    elif "Tenuto" in marks:
        gate = 1.0
    elif getattr(element, "_playback_legato", False):
        gate = 1.10
    elif hasattr(element, "_playback_tie_release_ms") or getattr(element, "_playback_ornament", False):
        gate = 1.0
    else:
        gate = 0.85
    adjustment = release_ms * (gate - 1)
    if adjustment > 0:
        adjustment = min(60, adjustment)
    return max(10, round(dur + adjustment))


def score_to_sequence(score):
    performed = _playback_score(score)
    tokens = []
    for entry in performed.flatten().secondsMap:
        element = entry["element"]
        if not getattr(element, "isNote", False) and not getattr(element, "isChord", False):
            continue
        start = round(entry["offsetSeconds"] * 1000)
        if element.duration.isGrace:
            continue
        dur = _duration_ms(entry)
        velocity = element.volume.velocity
        velocity = max(1, min(127, velocity if velocity is not None else 90))
        for pitch in element.pitches:
            midi_num = pitch.midi
            name = NOTE_NAMES[midi_num % 12]
            tokens.append((start, f"{name}{midi_num // 12 - 1}@{start}-{dur}-{velocity}"))
    return " ".join(token for start_pos, token in sorted(tokens, key=lambda val: val[0]))


def score_to_import_items(score):
    from music21 import clef, spanner, stream
    performed = copy.deepcopy(score)
    for slur in performed.recurse().getElementsByClass(spanner.Slur):
        for element in slur.getSpannedElements():
            element._notation_slur = True
        for element in slur.getSpannedElements()[:-1]:
            element._playback_legato = True
    performed = performed.expandRepeats()
    for source_id, element in enumerate(performed.recurse().notesAndRests):
        element._notation_source = source_id
    timing = {id(entry["element"]): entry for entry in performed.flatten().secondsMap}
    playback = _playback_score(performed, expand_repeats=False)
    playback_by_source = {}
    for entry in playback.flatten().secondsMap:
        element = entry["element"]
        if not getattr(element, "isNote", False) and not getattr(element, "isChord", False):
            continue
        if element.duration.isGrace:
            continue
        playback_by_source.setdefault(element._notation_source, []).append({
            "notes": [p.midi for p in element.pitches],
            "start_ms": round(entry["offsetSeconds"] * 1000),
            "duration_ms": _duration_ms(entry),
            "velocity": element.volume.velocity or 90,
        })
    events = []
    for part_index, part in enumerate(performed.parts):
        voice_ids = sorted({str(v.id) for v in part.recurse().getElementsByClass(stream.Voice)},
                           key=lambda val: (not val.isdigit(), int(val) if val.isdigit() else val))
        default_voice = voice_ids[0] if voice_ids else "1"
        for element in part.recurse().notesAndRests:
            dur = element.duration
            current = element.getContextByClass(clef.Clef)
            clef_name = {"G": "treble", "F": "bass", "C": "alto"}.get(
                getattr(current, "sign", "G"), "treble")
            notation_clef = clef_name
            if part.__class__.__name__ == "PartStaff":
                staff_number = str(part.id).rsplit("-Staff", 1)[-1]
                if staff_number in ("1", "2"):
                    clef_name = "treble" if staff_number == "1" else "bass"
            pitches = [] if element.isRest else [p.midi for p in element.pitches]
            entry = timing[id(element)]
            offset = float(element.getOffsetInHierarchy(performed))
            voice_id = str(element.activeSite.id) if isinstance(element.activeSite, stream.Voice) else default_voice
            item = {
                "staff_id": str(part_index),
                "staff_order": part_index,
                "staff_name": f"{part.partName or 'Part'}, staff {part_index + 1}",
                "voice_id": voice_id,
                "score_offset": offset,
                "clef": clef_name,
                "notes": pitches if clef_name != "bass" else [],
                "lh_notes": pitches if clef_name == "bass" else [],
                "beats": float(dur.quarterLength),
                "dur_name": dur.type,
                "score_duration": float(dur.quarterLength),
                "dotted": bool(dur.dots),
                "triplet": bool(dur.tuplets),
                "pedal": False, "style_idx": 1,
                "start_ms": round(entry["offsetSeconds"] * 1000),
                "velocity": getattr(getattr(element, "volume", None), "velocity", None) or 90,
                "preview_ms": max(10, round(entry["durationSeconds"] * 1000)),
                "score_position": (element.measureNumber or 1, float(element.beat)),
                "notation_clef": notation_clef,
                "pitch_names": {p.midi: p.nameWithOctave for p in element.pitches},
                "grace": dur.isGrace,
            }
            item["playback_events"] = [dict(ev, offset_ms=ev["start_ms"] - item["start_ms"])
                                       for ev in playback_by_source.get(element._notation_source, [])]
            item["notation_notes"] = pitches[:]
            item["notation_beats"] = item["beats"]
            item["notation_marks"] = [e.name for e in element.expressions]
            item["notation_marks"].extend(a.name for a in element.articulations
                                          if a.__class__.__name__ != "Fingering")
            if getattr(element, "_notation_slur", False):
                item["notation_marks"].append("slur")
            if element.isRest:
                item["rest_clef"] = clef_name
            if getattr(element, "tie", None):
                item["dur_name"] += ", tie " + element.tie.type
            events.append((offset, part_index, item))
    return [item for off, pidx, item in sorted(events, key=lambda row: row[:2])]


def score_rows(score):
    from music21 import clef
    groups = {}
    for index, part in enumerate(score.parts):
        for element in part.recurse().notesAndRests:
            current = element.getContextByClass(clef.Clef)
            sign = getattr(current, "sign", "G")
            name = {"G": "Treble Clef", "F": "Bass Clef", "C": "Alto Clef"}.get(sign, str(sign))
            label = f"{part.partName or 'Part ' + str(index + 1)} - {name}"
            key = (index, sign, getattr(current, "line", 2))
            if key not in groups:
                groups[key] = (label, [])
            pitches = "Rest" if element.isRest else ", ".join(p.nameWithOctave for p in element.pitches)
            dur = element.duration
            details = f"{dur.type}, {float(dur.quarterLength):g} beats"
            if dur.dots:
                details += f", {dur.dots} dotted"
            if dur.tuplets:
                details += ", tuplet"
            if getattr(element, "tie", None):
                details += f", tie {element.tie.type}"
            text = f"Bar {element.measureNumber}, beat {element.beat:g}: {pitches}, {details}"
            groups[key][1].append(text)
    return list(groups.values())


def render_score(path):
    import verovio
    toolkit = verovio.toolkit()
    toolkit.setOptions({"pageWidth": 1800, "scale": 45, "adjustPageHeight": True})
    if not toolkit.loadFile(str(path)):
        raise ValueError("Cannot engrave this MusicXML file")
    return "\n".join(toolkit.renderToSVG(page) for page in range(1, toolkit.getPageCount() + 1))


def show_score_reader(app, path, score, engraved):
    import wx
    import wx.html2
    groups = score_rows(score)
    if not groups:
        raise ValueError("The score contains no notes or rests")
    with tempfile.TemporaryDirectory(prefix="instrument-score-") as folder:
        document = Path(folder) / "score.html"
        document.write_text("<!doctype html><html><meta charset='utf-8'><title>"
                            + html.escape(os.path.basename(path))
                            + "</title><body>" + engraved + "</body></html>", encoding="utf-8")
        dialog = wx.Dialog(None, title="Score - " + os.path.basename(path),
                           size=(1100, 800), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        layout = wx.BoxSizer(wx.VERTICAL)
        layout.Add(wx.StaticText(dialog, label="Alt+Up/Down: switch clef. Left/Right: read notes. Escape: close."), 0, wx.ALL, 8)
        choice = wx.Choice(dialog, choices=[group[0] for group in groups])
        choice.SetName("Clef")
        choice.SetSelection(0)
        layout.Add(choice, 0, wx.EXPAND | wx.ALL, 5)
        notes = wx.ListBox(dialog, choices=groups[0][1], size=(-1, 160))
        notes.SetName("Notes in clef")
        layout.Add(notes, 0, wx.EXPAND | wx.ALL, 5)
        view = wx.html2.WebView.New(dialog)
        view.LoadURL(document.as_uri())
        layout.Add(view, 1, wx.EXPAND)
        close_btn = wx.Button(dialog, wx.ID_CANCEL, "Close")
        layout.Add(close_btn, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        dialog.SetSizer(layout)

        def speak():
            idx = notes.GetSelection()
            if idx != wx.NOT_FOUND:
                app.announce(notes.GetString(idx))

        def change_group(event=None):
            label, rows = groups[choice.GetSelection()]
            notes.Set(rows)
            notes.SetSelection(0)
            notes.SetFocus()
            app.announce(label + ". " + rows[0])

        def on_key(event):
            code = event.GetKeyCode()
            if event.AltDown() and code in (wx.WXK_UP, wx.WXK_DOWN):
                delta = -1 if code == wx.WXK_UP else 1
                choice.SetSelection((choice.GetSelection() + delta) % len(groups))
                change_group()
            elif code in (wx.WXK_LEFT, wx.WXK_RIGHT):
                delta = -1 if code == wx.WXK_LEFT else 1
                idx = max(0, min(notes.GetCount() - 1, notes.GetSelection() + delta))
                notes.SetSelection(idx)
                notes.EnsureVisible(idx)
                speak()
            elif code == wx.WXK_ESCAPE:
                dialog.EndModal(wx.ID_CANCEL)
            else:
                event.Skip()

        choice.Bind(wx.EVT_CHOICE, change_group)
        notes.Bind(wx.EVT_LISTBOX, lambda event: speak())
        dialog.Bind(wx.EVT_CHAR_HOOK, on_key)
        change_group()
        try:
            dialog.ShowModal()
        finally:
            dialog.Destroy()
