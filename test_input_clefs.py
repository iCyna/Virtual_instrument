"""Exercise editor navigation without starting the platform audio engine."""
import ast
from pathlib import Path
import unittest

source = ast.parse(Path(__file__).with_name('mte_importmode.py').read_text(encoding='utf-8'))
methods = {'input_note_pitch', 'adjust_pitch', 'switch_clef', 'clef_notes', 'navigate_clef', 'navigate_vertical', 'read_chord_note', 'midi_to_name', 'run', 'build_sequence_string', 'toggle_preview_play', 'delete_current', 'insert_item', 'change_duration', 'get_effective_beats', 'get_item_time_ms', 'seek_by_beats', 'speak_current', 'get_bar_beat_position'}
classes = []
for node in source.body:
    if isinstance(node, ast.FunctionDef) and node.name == 'item_playback_events':
        classes.append(node)
    if isinstance(node, ast.ClassDef) and node.name == 'ImportModeState':
        classes.append(node)
    elif isinstance(node, ast.ClassDef) and node.name == 'ImportModeEditor':
        node.body = [method for method in node.body if isinstance(method, ast.FunctionDef) and method.name in methods]
        classes.append(node)
namespace = {'NOTE_BASE': {'c': 0, 'd': 2, 'e': 4, 'f': 5, 'g': 7, 'a': 9, 'b': 11}, 'NAMES': ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']}
exec(compile(ast.Module(body=classes, type_ignores=[]), '<editor navigation>', 'exec'), namespace)


class ClefTests(unittest.TestCase):
    def setUp(self):
        self.editor = namespace['ImportModeEditor']()
        self.editor.st = namespace['ImportModeState']()
        self.messages = []
        self.editor.announce = self.messages.append
        self.editor.speak_current = lambda: None

    def test_key_accidentals_and_one_shot_arrows(self):
        editor = self.editor
        editor.st.key_tonic = 'G'
        self.assertEqual(editor.input_note_pitch('f', 4), 66)
        editor.st.items = [{'notes': [60]}]
        editor.st.sel_start = editor.st.sel_end = 0
        editor.adjust_pitch(-1)
        self.assertEqual(editor.input_note_pitch('f', 4), 65)
        self.assertEqual(editor.input_note_pitch('f', 4), 66)
        self.assertEqual(editor.st.items[0]['notes'], [60])
        editor.st.key_tonic = 'F'
        self.assertEqual(editor.input_note_pitch('b', 4), 70)
        editor.st.key_tonic, editor.st.key_mode = 'A', 'Minor'
        self.assertEqual(editor.input_note_pitch('c', 4), 60)
        editor.st.key_tonic, editor.st.key_mode = 'G', '7 (Mixolydian)'
        self.assertEqual(editor.input_note_pitch('f', 4), 65)

    def test_defaults_and_switching(self):
        self.assertEqual(self.editor.st.clefs, ['treble', 'bass'])
        self.editor.switch_clef(1)
        self.assertEqual(self.editor.st.active_clef, 'bass')
        self.assertEqual(self.editor.st.input_pitch_offset, 0)
        self.editor.switch_clef(1)
        self.assertEqual(self.editor.st.active_clef, 'treble')

    def test_filter_navigation_and_legacy_left_hand(self):
        state = self.editor.st
        state.items = [{'notes': [60], 'lh_notes': [48]},
                       {'notes': [62], 'clef': 'alto'},
                       {'notes': [64], 'clef': 'treble'}]
        self.editor.navigate_clef(1)
        self.assertEqual(state.cursor, 2)
        state.active_clef = 'alto'
        self.editor.navigate_clef(-1)
        self.assertEqual(state.cursor, 1)
        state.active_clef = 'bass'
        self.assertEqual(self.editor.clef_notes(state.items[0]), [48])
        self.editor.navigate_clef(-1)
        self.assertEqual(state.cursor, 0)

    def test_space_plays_both_clefs_on_shared_timeline(self):
        from types import SimpleNamespace
        class Clock:
            now = 0.0
            def monotonic(self):
                return self.now
            def sleep(self, seconds):
                self.now += seconds
        clock = Clock()
        class Thread:
            def __init__(self, target, **kwargs):
                self.target = target
            def start(self):
                self.target()
        namespace.update(time=clock, threading=SimpleNamespace(Thread=Thread))
        editor = self.editor
        editor.app = SimpleNamespace(bpm=120)
        editor.is_playing_seq = False
        editor.st.items = [
            {'notes': [60], 'beats': 1, 'start_ms': 0, 'preview_ms': 500},
            {'lh_notes': [48], 'beats': 4, 'start_ms': 0, 'preview_ms': 3000},
            {'notes': [64], 'beats': 1, 'start_ms': 1000, 'preview_ms': 1000},
        ]
        played = []
        editor.play_item_preview = lambda item: played.append((clock.now, item))
        editor.toggle_preview_play()
        self.assertEqual(played[0][0], played[1][0])
        self.assertAlmostEqual(played[2][0], 1.0, delta=0.01)
        self.assertGreaterEqual(clock.now, 3.0)
        self.assertFalse(editor.is_playing_seq)

    def test_space_starts_at_cursor_and_keeps_other_clef(self):
        # Reuse the deterministic clock setup and polyphonic fixture above.
        self.test_space_plays_both_clefs_on_shared_timeline()
        editor = self.editor
        editor.st.cursor = 2
        played = []
        editor.play_item_preview = lambda item: played.append(item)
        editor.toggle_preview_play()
        self.assertEqual(len(played), 2)
        self.assertEqual(played[0]['lh_notes'], [48])
        self.assertEqual(played[0]['preview_ms'], 2000)
        self.assertEqual(played[1]['notes'], [64])
        self.assertFalse(any(item.get('notes') == [60] for item in played))

    def test_space_includes_all_notes_at_cursor_onset(self):
        self.test_space_plays_both_clefs_on_shared_timeline()
        self.editor.st.cursor = 1
        played = []
        self.editor.play_item_preview = played.append
        self.editor.toggle_preview_play()
        self.assertEqual(len(played), 3)
        self.assertEqual(played[0]['notes'], [60])

    def test_space_at_end_does_not_restart(self):
        self.test_space_plays_both_clefs_on_shared_timeline()
        self.editor.st.cursor = len(self.editor.st.items)
        played = []
        self.editor.play_item_preview = played.append
        self.editor.toggle_preview_play()
        self.assertEqual(played, [])

    def test_right_reaches_virtual_rest_and_left_returns_to_last_note(self):
        state = self.editor.st
        state.items = [{'notes': [60]}]
        spoken = []
        self.editor.speak_current = lambda: spoken.append(state.cursor)
        self.editor.navigate_clef(-1)
        self.editor.navigate_clef(1)
        self.editor.navigate_clef(1)
        self.editor.navigate_clef(-1)
        self.assertEqual(spoken, [0, 1, 1, 0])
        self.assertEqual(len(state.items), 1)

    def test_delete_keys_at_virtual_rest_make_previous_note_replaceable(self):
        from types import SimpleNamespace

        editor = self.editor
        del editor.speak_current
        for delete_key in ('delete', 'backspace'):
            with self.subTest(key=delete_key):
                keys = iter(('end', delete_key, 'exit'))
                keyboard = SimpleNamespace(
                    frameUpdate=lambda: setattr(keyboard, 'key', next(keys)),
                    keyPressed=lambda key: keyboard.key == key,
                    keyPressing=lambda key: False,
                )
                editor.w = keyboard
                editor.track = SimpleNamespace(name='Test')
                editor.app = SimpleNamespace(time_sig=4)
                editor.synth = SimpleNamespace(close=lambda: None)
                editor.format_item_speech = lambda item: str(item['notes'])
                state = editor.st
                state.items = [
                    dict(notes=[60], beats=2, staff_id=1, voice_id=1),
                    dict(notes=[64], beats=1, staff_id=1, voice_id=2),
                    dict(rest_clef='treble', beats=1, staff_id=1, voice_id=1),
                ]
                state.cursor = len(state.items)
                state.active_lane = (1, 1)
                self.messages.clear()
                editor.run()
                self.assertIn('Virtual rest, end of score, Bar 2 Beat 1', self.messages)
                self.assertEqual(state.cursor, 0)
                self.assertEqual(state.items[0]['notes'], [])
                self.assertEqual(state.items[1]['notes'], [64])
                filled = editor.insert_item(dict(notes=[62], beats=1))
                self.assertEqual(filled['notes'], [62])
                self.assertEqual(filled['beats'], 2)
                self.assertEqual(len(state.items), 3)

    def test_delete_and_refill_current_slot(self):
        editor = self.editor
        editor.format_item_speech = lambda item: str(item['notes'])
        state = editor.st
        state.items = [
            {'notes': [60], 'beats': 1},
            {'notes': [62], 'lh_notes': [48], 'beats': 2, 'start_ms': 500},
            {'notes': [64], 'beats': 1},
        ]
        state.cursor = 1
        editor.delete_current()
        self.assertEqual(state.cursor, 1)
        self.assertEqual(state.items[0]['notes'], [60])
        self.assertEqual(state.items[1]['notes'], [])
        self.assertEqual(state.items[1]['lh_notes'], [48])
        filled = editor.insert_item({'notes': [65], 'beats': 1})
        self.assertEqual(len(state.items), 3)
        self.assertEqual(filled['notes'], [65])
        self.assertEqual(filled['beats'], 2)
        self.assertEqual(filled['start_ms'], 500)
        self.assertEqual(state.items[2]['notes'], [64])

    def test_duration_only_changes_cursor_and_preserves_input_defaults(self):
        state = self.editor.st
        state.items = [dict(notes=[60], beats=1, dur_name='Quarter'),
                       dict(notes=[62], beats=1, dur_name='Quarter', preview_ms=500)]
        state.cursor = 1
        self.editor.change_duration(duration=(2, 'Half'))
        self.assertEqual(state.items[0]['beats'], 1)
        self.assertEqual(state.items[1]['beats'], 2)
        self.assertEqual(state.items[1]['preview_ms'], 1000)
        self.assertEqual(state.current_beats, 1)
        self.editor.change_duration(toggle='dotted')
        self.assertEqual(state.items[1]['beats'], 3)
        self.assertFalse(state.is_dotted)
        state.cursor = 2
        self.editor.change_duration(duration=(4, 'Whole'))
        self.assertEqual(state.items[1]['beats'], 3)
        self.assertEqual(state.current_beats, 4)

    def test_empty_clef_keeps_cursor(self):
        self.editor.st.active_clef = 'alto'
        self.editor.st.items = [{'notes': [60]}]
        self.editor.navigate_clef(1)
        self.assertEqual(self.editor.st.cursor, 0)
        self.assertTrue(self.messages)

    def test_read_chord_notes_in_pitch_order_and_keep_cursor(self):
        from types import SimpleNamespace
        editor = self.editor
        played = []
        editor.synth = SimpleNamespace(play_notes=lambda notes, *a, **kw: played.append(notes))
        editor.st.items = [dict(notes=[67, 60, 64], lh_notes=[48])]
        for direction in (1, 1, 1, 1, -1):
            editor.read_chord_note(direction)
        self.assertEqual(played, [[60], [64], [67], [67], [64]])
        self.assertEqual(editor.st.cursor, 0)
        self.assertEqual(editor.st.items[0]['notes'], [67, 60, 64])
        editor.st.active_clef = 'bass'
        editor.read_chord_note(-1)
        self.assertEqual(played[-1], [48])
        editor.st.cursor = 1
        editor.read_chord_note(1)
        self.assertEqual(len(played), 6)

    def test_chord_reader_resets_at_new_item_and_ignores_rests(self):
        from types import SimpleNamespace
        played = []
        editor = self.editor
        editor.synth = SimpleNamespace(play_notes=lambda notes, *a, **kw: played.append(notes))
        editor.st.items = [dict(notes=[60, 64]), dict(notes=[62, 65]), dict(notes=[])]
        editor.read_chord_note(-1)
        editor.st.cursor = 1
        editor.read_chord_note(1)
        editor.st.cursor = 2
        editor.read_chord_note(1)
        self.assertEqual(played, [[64], [62]])

    @unittest.skipUnless(Path(__file__).with_name('Haydn-sonata-in-c-major-hob xvi-1-allegro fingering.mxl').is_file(),
                         'local Haydn score is not present')
    def test_haydn_notation_and_playback_roundtrip(self):
        from types import SimpleNamespace
        from music21 import converter
        from multiformat import score_to_import_items, score_to_sequence
        path = Path(__file__).with_name('Haydn-sonata-in-c-major-hob xvi-1-allegro fingering.mxl')
        score = converter.parse(path, forceSource=True)
        items = score_to_import_items(score)
        self.assertEqual(len(items), len(list(score.expandRepeats().recurse().notesAndRests)))
        first = items[0]
        self.assertEqual(first['notes'], [72])
        self.assertEqual(first['beats'], 1)
        self.assertEqual(first['score_position'], (1, 1.0))
        self.assertIn('mordent', first['notation_marks'])
        lower_in_treble = [i for i in items if i['clef'] == 'bass' and i['notation_clef'] == 'treble']
        self.assertTrue(lower_in_treble)
        self.assertTrue(all(i['lh_notes'] and not i['notes'] for i in lower_in_treble if i['lh_notes']))
        self.editor.st.items = items
        self.editor.app = SimpleNamespace(bpm=144)
        self.assertEqual(sorted(self.editor.build_sequence_string().split()), sorted(score_to_sequence(score).split()))

    def test_ctrl_alt_up_dispatches_chord_reader_before_clef_switch(self):
        from types import SimpleNamespace
        class Keyboard:
            frame = 0
            def frameUpdate(self):
                self.frame += 1
            def keyPressed(self, key):
                return key == ('exit' if self.frame == 2 else 'up')
            def keyPressing(self, key):
                return key in ('lcontrol', 'lalt')
        editor = self.editor
        editor.w = Keyboard()
        editor.track = SimpleNamespace(name='Test')
        played = []
        editor.synth = SimpleNamespace(play_notes=lambda notes, *a, **kw: played.append(notes), close=lambda: None)
        editor.st.items = [dict(notes=[60, 64, 67])]
        editor.run()
        self.assertEqual(played, [[60]])
        self.assertEqual(editor.st.active_clef, 'treble')
        self.assertEqual(editor.st.cursor, 0)
        self.assertEqual(editor.st.input_pitch_offset, 0)

    @unittest.skipUnless(Path(__file__).with_name('Haydn - Sonata No.37 in D Major Mov. 1.mxl').is_file(),
                         'local Haydn D major score is not present')
    def test_haydn_d_major_articulations_and_export(self):
        from types import SimpleNamespace
        from music21 import converter
        from multiformat import score_to_import_items, score_to_sequence
        score = converter.parse(Path(__file__).with_name('Haydn - Sonata No.37 in D Major Mov. 1.mxl'),
                                forceSource=True)
        items = score_to_import_items(score)
        for mark, gate in (('staccatissimo', 0.20), ('staccato', 0.40)):
            marked = [item for item in items if mark in item['notation_marks']
                      and len(item['playback_events']) == 1 and 'tie' not in item['dur_name']]
            self.assertGreater(len(marked), 50)
            for item in marked:
                event = item['playback_events'][0]
                available_ms = item['preview_ms'] - event['offset_ms']
                effective_gate = 0.20 if 'staccatissimo' in item['notation_marks'] else gate
                self.assertAlmostEqual(event['duration_ms'], available_ms * effective_gate, delta=1)
        self.editor.st.items = items
        self.editor.app = SimpleNamespace(bpm=120)
        self.assertEqual(sorted(self.editor.build_sequence_string().split()), sorted(score_to_sequence(score).split()))

    def test_realized_events_follow_transpose_and_duration_edits(self):
        item = dict(notes=[62], beats=2, preview_ms=1000, notation_notes=[60], notation_beats=1,
                    playback_events=[dict(notes=[60], offset_ms=0, duration_ms=100, velocity=90),
                                     dict(notes=[59], offset_ms=100, duration_ms=100, velocity=90)])
        events = namespace['item_playback_events'](item)
        self.assertEqual([e['notes'] for e in events], [[62], [61]])
        self.assertEqual(events[1]['offset_ms'], 200)
        self.assertEqual(events[1]['duration_ms'], 200)
        item['notes'] = []
        self.assertEqual(namespace['item_playback_events'](item), [])

    def test_start_at_tie_continuation_keeps_remaining_held_note(self):
        from types import SimpleNamespace
        self.test_space_plays_both_clefs_on_shared_timeline()
        editor = self.editor
        editor.st.items = [
            dict(notes=[60], beats=1, start_ms=0, preview_ms=500, notation_notes=[60], notation_beats=1,
                 playback_events=[dict(notes=[60], offset_ms=0, duration_ms=1000, velocity=90)]),
            dict(notes=[60], beats=1, start_ms=500, preview_ms=500, notation_notes=[60], notation_beats=1,
                 playback_events=[])]
        editor.st.cursor = 1
        played = []
        editor.play_item_preview = lambda item: played.extend(namespace['item_playback_events'](item))
        editor.toggle_preview_play()
        self.assertEqual(len(played), 1)
        self.assertEqual(played[0]['notes'], [60])
        self.assertEqual(played[0]['duration_ms'], 500)


if __name__ == '__main__':
    unittest.main()
