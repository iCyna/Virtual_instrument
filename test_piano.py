"""Test live piano routing and keyboard frames without opening an audio device."""
import ast
import os
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock


class Instrument:
    def __init__(self):
        self.handle = object()
        self.events = []
        self.closed = False
        self.create_instrument = Mock(return_value=True)
        self.create_empty_stream = Mock()
        self.load_font = Mock(return_value='font')
        self.set_fonts = Mock()
        self.set_chunk = Mock()
        self.play = Mock()

    def send_midi(self, chan, event, param):
        self.events.append((chan, event, param))

    def send_event(self, chan, event, param):
        self.events.append((chan, event, param))

    def close(self):
        self.closed = True


def load_piano():
    source = Path(__file__).with_name('piano.py')
    tree = ast.parse(source.read_text(encoding='utf-8'))
    tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
    instruments = []
    def factory():
        instrument = Instrument()
        instruments.append(instrument)
        return instrument
    config = dict(active_engine='vst', vst_path=str(source), vst_chunk=b'preset', sf2_path='piano.sf2', sf2_id=3)
    core = SimpleNamespace(config={'instruments': {'piano': config}}, recording=False, recorder=None, save=Mock())
    namespace = dict(os=os, sys=sys, __file__=str(source), core=core,
                     vst=factory, musical=factory, setting=SimpleNamespace(run=Mock(), open_instrument_settings=Mock()),
                     recorder=SimpleNamespace(mainloop=Mock()), time=SimpleNamespace(monotonic=lambda: 1.0))
    exec(compile(tree, str(source), 'exec'), namespace)
    return namespace, instruments


class PianoTests(unittest.TestCase):
    def setUp(self):
        self.ns, self.instruments = load_piano()
        self.config = self.ns['core'].config['instruments']['piano']

    def engine(self):
        return self.ns['PianoEngine'](self.config)

    def run_frames(self, frames):
        class Window:
            index = -1
            say = Mock()
            def frameUpdate(self):
                self.index += 1
                if self.index >= len(frames):
                    raise AssertionError('Piano did not exit')
            def keyPressed(self, key):
                return key in frames[self.index][0]
            def keyPressing(self, key):
                return key in frames[self.index][1]
        window = Window()
        self.ns['core'].getW = lambda: window
        self.ns['run']()
        return window

    def test_vst_initializes_preset_and_routes_live_and_backing(self):
        engine = self.engine()
        inst = self.instruments[-1]
        inst.create_instrument.assert_called_once_with(self.config['vst_path'], frequency=44100)
        inst.set_chunk.assert_called_once_with(b'preset')
        engine.send_event(1, 1, 60 | (90 << 8))
        self.assertEqual(inst.events[-1], (0, 1, 60 | (90 << 8)))
        self.assertIs(engine.handle, inst.handle)

    def test_sf2_uses_selected_program(self):
        self.config['active_engine'] = 'sf2'
        engine = self.engine()
        self.assertFalse(engine.is_vst)
        self.assertIn((0, 2, 3), self.instruments[-1].events)

    def test_missing_vst_closes_failed_stream(self):
        self.config['vst_path'] = 'missing-plugin.dll'
        with self.assertRaises(RuntimeError):
            self.engine()
        self.assertTrue(self.instruments[-1].closed)

    def test_overlapping_live_and_backing_do_not_cut_each_other(self):
        engine = self.engine()
        engine.send_event(0, 1, 60 | (100 << 8))
        engine.send_event(1, 1, 60 | (90 << 8))
        engine.send_event(1, 1, 60)
        self.assertEqual(len(self.instruments[-1].events), 2)
        engine.send_event(0, 1, 60)
        self.assertEqual(self.instruments[-1].events[-1], (0, 1, 60))
        self.assertEqual(engine.voices, {})

    def test_layout_has_two_complete_chromatic_octaves(self):
        self.assertEqual(set(self.ns['PIANO_KEYS'].values()), set(range(48, 82)))

    def test_two_hands_release_original_notes_after_octave_change(self):
        self.run_frames([(set(), {'z', 'q', 'two'}), ({'page_up'}, {'z', 'q', 'two'}),
                         (set(), set()), ({'exit'}, set())])
        events = self.instruments[0].events
        for note in (48, 60, 61):
            self.assertIn((0, 1, note | (100 << 8)), events)
            self.assertIn((0, 1, note), events)
        self.assertEqual(sum(bool(param >> 8) for _, event, param in events if event == 1), 3)
        self.assertTrue(self.instruments[0].closed)

    def test_extended_keys_play_and_release_without_starting_backing(self):
        keys = {'o', 'p', '[', ']', 'backslash', 'comma', 'dot', 'slash',
                'nine', 'zero', 'minus', 'equal', 'l', 'semicolon'}
        self.run_frames([(keys, keys), (set(), set()), ({'exit'}, set())])
        events = self.instruments[0].events
        notes = [self.ns['PIANO_KEYS'][key] for key in keys]
        for note in notes:
            self.assertIn((0, 1, note | (100 << 8)), events)
            self.assertIn((0, 1, note), events)
        self.assertEqual(sum(bool(param >> 8) for _, event, param in events if event == 1), len(keys))

    def test_ctrl_slot_does_not_play_black_key_or_shift_octave(self):
        self.run_frames([({'two'}, {'lcontrol', 'lalt', 'two'}),
                         (set(), {'z'}), (set(), set()), ({'exit'}, set())])
        events = self.instruments[0].events
        self.assertEqual([param & 255 for _, event, param in events if event == 1 and param >> 8], [48])
        self.assertEqual(self.ns['core'].config['piano pitch slot']['two'], 0)
        self.ns['core'].save.assert_called_once()

    def test_each_shift_doubles_only_its_hand(self):
        for shift, expected in [('lshift', [48, 60, 64]),
                                ('rshift', [48, 64, 76])]:
            with self.subTest(shift=shift):
                self.setUp()
                self.run_frames([(set(), {shift, 'z', 'e'}), (set(), set()), ({'exit'}, set())])
                ons = [param & 255 for _, event, param in self.instruments[0].events if event == 1 and param >> 8]
                self.assertEqual(ons, expected)

    def test_both_shifts_double_both_hands_without_latching(self):
        self.run_frames([(set(), {'lshift', 'rshift', 'z', 'e'}),
                         (set(), set()), (set(), {'z', 'e'}), (set(), set()), ({'exit'}, set())])
        ons = [param & 255 for _, event, param in self.instruments[0].events if event == 1 and param >> 8]
        self.assertEqual(ons, [48, 60, 64, 76, 48, 64])

    def test_shift_adds_and_removes_octave_while_base_note_stays_held(self):
        self.run_frames([(set(), {'e'}), (set(), {'e', 'rshift'}),
                         (set(), {'e'}), (set(), set()), ({'exit'}, set())])
        events = [(param & 255, bool(param >> 8)) for _, event, param in self.instruments[0].events if event == 1]
        self.assertEqual(events, [(64, True), (76, True), (76, False), (64, False)])

    def test_standalone_controls_shift_down_and_up_once_per_tap(self):
        self.run_frames([(set(), {'lcontrol'}), (set(), {'lcontrol'}), (set(), set()),
                         (set(), {'z'}), (set(), set()),
                         (set(), {'rcontrol'}), (set(), set()),
                         (set(), {'z'}), (set(), set()), ({'exit'}, set())])
        ons = [param & 255 for _, event, param in self.instruments[0].events if event == 1 and param >> 8]
        self.assertEqual(ons, [36, 48])

    def test_ctrl_shortcut_release_does_not_transpose(self):
        self.run_frames([({'o'}, {'lcontrol', 'o'}), (set(), {'lcontrol'}),
                         (set(), set()), (set(), {'z'}), (set(), set()), ({'exit'}, set())])
        ons = [param & 255 for _, event, param in self.instruments[0].events if event == 1 and param >> 8]
        self.assertEqual(ons, [48])

    def test_sustain_and_recorder_receive_live_audio_object(self):
        self.run_frames([(set(), {'space', 'z'}), (set(), {'space'}),
                         (set(), set()), ({'exit'}, set())])
        events = self.instruments[0].events
        self.assertIn((0, 15, 127), events)
        self.assertIn((0, 15, 0), events)
        obj = self.ns['recorder'].mainloop.call_args_list[0].args[0]
        self.assertIs(obj.handle, self.instruments[0].handle)

    def test_settings_reloads_engine_and_cleans_held_notes(self):
        self.run_frames([(set(), {'z'}), ({'f1'}, set()), ({'exit'}, set())])
        self.assertEqual(len(self.instruments), 2)
        self.assertTrue(all(inst.closed for inst in self.instruments))
        self.assertIn((0, 1, 48), self.instruments[0].events)
        self.ns['setting'].run.assert_called_once()

    def test_default_uses_bundled_vst_matching_python_architecture(self):
        self.config.update(active_engine='sf2', vst_path='')
        self.run_frames([({'exit'}, set())])
        filename = '4Front Piano x64.dll' if sys.maxsize > 2**32 else '4Front Piano.dll'
        self.assertTrue(self.config['vst_path'].endswith(filename))
        self.assertEqual(self.config['active_engine'], 'vst')


if __name__ == '__main__':
    unittest.main()
