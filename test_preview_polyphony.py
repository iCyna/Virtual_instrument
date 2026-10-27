"""Verify MIDI messages without loading native audio libraries."""
import ast
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest

source = ast.parse(Path(__file__).with_name('mte_importmode.py').read_text(encoding='utf-8'))
synth_class = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'LivePreviewSynth')

class PolyphonyTests(unittest.TestCase):
    def make_synth(self, vst=False):
        pending = []
        class Thread:
            def __init__(self, target, **kwargs):
                self.target = target
            def start(self):
                pending.append(self.target)
        namespace = {'threading': SimpleNamespace(Thread=Thread),
                     'time': SimpleNamespace(sleep=lambda seconds: None)}
        exec(compile(ast.Module(body=[synth_class], type_ignores=[]), '<synth>', 'exec'), namespace)
        synth = namespace['LivePreviewSynth'].__new__(namespace['LivePreviewSynth'])
        events = []
        synth.inst = SimpleNamespace(send_event=lambda *args: events.append(args),
                                     send_midi=lambda *args: events.append(args))
        synth.is_vst = vst
        synth.chan = 0
        synth._note_lock = threading.Lock()
        synth._active_notes = {}
        return synth, events, pending

    def test_dense_chords_send_every_pitch_before_returning(self):
        for vst in (False, True):
            synth, events, pending = self.make_synth(vst)
            synth.play_notes([48, 55, 60, 64, 67, 72], 1000)
            self.assertEqual([event[2] & 255 for event in events], [48, 55, 60, 64, 67, 72])
            self.assertTrue(all(event[2] >> 8 == 100 for event in events))
            pending[0]()
            self.assertEqual(len(events), 12)
            self.assertFalse(synth._active_notes)

    def test_short_voice_cannot_cut_off_overlapping_unison(self):
        for vst in (False, True):
            synth, events, pending = self.make_synth(vst)
            synth.play_notes([60, 64, 67], 500)
            synth.play_notes([48, 60], 2000)
            pending[0]()
            off = [event[2] for event in events if event[2] >> 8 == 0]
            self.assertEqual(off, [64, 67])
            self.assertEqual(synth._active_notes, {48: 1, 60: 1})
            pending[1]()
            self.assertFalse(synth._active_notes)
            self.assertEqual(sum(event[2] == 60 for event in events), 1)

    def test_older_note_off_cannot_cut_off_repeated_pitch(self):
        synth, events, pending = self.make_synth()
        synth.play_notes([60], 1000)
        synth.play_notes([60, 64], 500)
        pending[1]()
        self.assertNotIn((0, 1, 60), events)
        pending[0]()
        self.assertEqual(events[-1], (0, 1, 60))

if __name__ == '__main__':
    unittest.main()
