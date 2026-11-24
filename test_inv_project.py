import ast
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import zipfile

from multiformat import (
    export_sequence_txt, export_wav, import_sequence_txt, import_wav,
    is_encrypted_inv, read_mpc, read_project, write_mpc, write_project,
)

source = ast.parse(Path('mte_importmode.py').read_text(encoding='utf-8'))
state_node = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'ImportModeState')
namespace = {}
exec(compile(ast.Module(body=[state_node], type_ignores=[]), '<state>', 'exec'), namespace)
State = namespace['ImportModeState']


def track(name):
    return SimpleNamespace(name=name, pcm=bytearray(), volume=100, pan=0, muted=False, solo=False, import_state=None)


class ProjectTests(unittest.TestCase):
    def test_roundtrip_portable_editable_score_encrypted(self):
        first = track('Piano tiếng Việt')
        first.pcm = bytearray(b'\x01\x02' * 50)
        first.pan = -25
        first.import_state = State('piano')
        first.import_state.items = [dict(notes=[60, 64], lh_notes=[48], beats=0.5, velocity=49,
                                         clef_notes={'treble': [60, 64], 'bass': [48]})]
        first.import_state.sel_start = first.import_state.sel_end = 0
        app = SimpleNamespace(tracks=[first, track('Second')], bpm=96, cursor_ms=250,
                              active_track_idx=1, time_sig_numerator=6, time_sig_denominator=8)
        with tempfile.TemporaryDirectory(dir='.') as folder:
            path = Path(folder) / 'song.inv'
            write_project(path, app)
            self.assertTrue(is_encrypted_inv(path))
            self.assertFalse(zipfile.is_zipfile(path))
            moved = Path(folder) / 'moved'
            moved.mkdir()
            destination = moved / 'song.inv'
            path.rename(destination)
            metadata, loaded = read_project(destination, track, State)
        self.assertEqual(loaded[0].pcm, first.pcm)
        self.assertEqual(vars(loaded[0].import_state), vars(first.import_state))
        self.assertEqual(loaded[0].pan, -25)
        self.assertEqual(metadata['time_sig_denominator'], 8)
        self.assertEqual(metadata['bpm'], 96)
        self.assertEqual(len(loaded), 2)

    def test_legacy_unencrypted_inv_still_loads(self):
        tr = track('Legacy')
        tr.pcm = bytearray(b'\x03\x04' * 20)
        app = SimpleNamespace(tracks=[tr], bpm=110, cursor_ms=0, active_track_idx=0,
                              time_sig_numerator=4, time_sig_denominator=4)
        with tempfile.TemporaryDirectory(dir='.') as folder:
            path = Path(folder) / 'legacy.inv'
            write_project(path, app, encrypt=False)
            self.assertFalse(is_encrypted_inv(path))
            metadata, loaded = read_project(path, track, State)
        self.assertEqual(loaded[0].pcm, tr.pcm)
        self.assertEqual(metadata['bpm'], 110)

    def test_mpc_wav_and_txt_roundtrip(self):
        tr = track('Pattern 1')
        tr.pcm = bytearray(b'\x10\x00\x20\x00' * 32)
        tr.import_state = State('piano')
        tr.import_state.items = [dict(notes=[60], lh_notes=[], beats=1.0, velocity=90)]
        app = SimpleNamespace(tracks=[tr], bpm=128, cursor_ms=0, active_track_idx=0,
                              time_sig_numerator=4, time_sig_denominator=4)
        with tempfile.TemporaryDirectory(dir='.') as folder:
            mpc_path = Path(folder) / 'beat.mpc'
            wav_path = Path(folder) / 'mix.wav'
            txt_path = Path(folder) / 'seq.txt'
            write_mpc(mpc_path, app)
            meta, loaded = read_mpc(mpc_path, track, State)
            self.assertEqual(meta['bpm'], 128)
            self.assertEqual(loaded[0].import_state.items[0]['notes'], [60])

            export_wav(str(wav_path), tr.pcm)
            self.assertEqual(import_wav(str(wav_path)), tr.pcm)

            export_sequence_txt(str(txt_path), 'C4-1-100 E4-1-100')
            self.assertEqual(import_sequence_txt(str(txt_path)), 'C4-1-100 E4-1-100')

    def test_bad_file_leaves_existing_project_file_intact(self):
        with tempfile.TemporaryDirectory(dir='.') as folder:
            path = Path(folder) / 'bad.inv'
            path.write_text('{"tracks": [], "bpm": 0}')
            with self.assertRaises(ValueError):
                read_project(path, track, State)


if __name__ == '__main__':
    unittest.main()
