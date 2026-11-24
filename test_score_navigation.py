from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from score_navigation import lane, vertical_notes
from test_input_clefs import namespace

FIXTURES = [Path(__file__).with_name(name) for name in (
    'Haydn - Sonata No.37 in D Major Mov. 1.mxl',
    'Haydn-sonata-in-c-major-hob xvi-1-allegro fingering.mxl')]


def item(staff, voice, pitches, start=0, duration=1):
    return dict(staff_id=str(staff), staff_order=staff, voice_id=str(voice),
                staff_name=f'Staff {staff + 1}', clef='treble' if staff == 0 else 'bass',
                notes=pitches if staff == 0 else [], lh_notes=pitches if staff else [],
                score_offset=start, score_duration=duration, beats=duration,
                pitch_names={}, velocity=80)


class VoiceNavigationTests(unittest.TestCase):
    def editor(self, items):
        editor = namespace['ImportModeEditor']()
        editor.st = namespace['ImportModeState']()
        editor.st.items = items
        editor.announce = Mock()
        editor.speak_current = Mock()
        editor.synth = SimpleNamespace(play_notes=Mock())
        return editor

    def test_vertical_order_includes_held_notes_separate_unisons_and_rests(self):
        items = [item(0, 1, [60, 72], 1), item(0, 2, [60], 0, 2),
                 item(1, 5, [48], 1), item(1, 6, [], 1), item(1, 5, [50], 2)]
        self.assertEqual(vertical_notes(items, 1), [(0, 72), (0, 60), (1, 60), (2, 48), (3, None)])
        self.assertEqual(vertical_notes(items, 2), [(4, 50)])

    def test_cycle_preserves_anchor_and_score_then_left_right_stays_in_voice(self):
        items = [item(0, 1, [72, 60], 1), item(0, 2, [65], 0, 3),
                 item(1, 5, [48], 1), item(0, 1, [74], 2), item(0, 2, [67], 3)]
        before = deepcopy(items)
        editor = self.editor(items)
        for expected in ([72], [60], [65], [48], [72]):
            editor.navigate_vertical(1)
            self.assertEqual(editor.synth.play_notes.call_args.args[0], expected)
        editor.navigate_vertical(-1)
        self.assertEqual(editor.st.cursor, 2)
        editor.navigate_vertical(-1)
        self.assertEqual(editor.st.active_lane, ['0', '2'])
        editor.navigate_clef(1)
        self.assertEqual(editor.st.cursor, 4)
        self.assertEqual(items, before)
        self.assertEqual(editor.st.input_pitch_offset, 0)

    def test_alt_down_dispatches_vertical_reader(self):
        editor = self.editor([item(0, 1, [72, 60])])
        class Keyboard:
            frame = 0
            def frameUpdate(self): self.frame += 1
            def keyPressed(self, key): return key == ('down' if self.frame == 1 else 'exit')
            def keyPressing(self, key): return key == 'lalt'
        editor.w = Keyboard()
        editor.track = SimpleNamespace(name='Test')
        editor.synth.close = Mock()
        editor.run()
        self.assertEqual(editor.synth.play_notes.call_args.args[0], [72])
        self.assertEqual(editor.st.input_pitch_offset, 0)

    def test_time_seek_keeps_selected_voice(self):
        items = [item(0, 1, [72]), item(0, 2, [60]),
                 item(0, 1, [74], 1), item(0, 2, [62], 1)]
        for value in items:
            value['start_ms'] = value['score_offset'] * 500
        editor = self.editor(items)
        editor.app = SimpleNamespace(bpm=120)
        editor.st.cursor = 1
        editor.st.active_lane = ['0', '2']
        editor.seek_by_beats(1)
        self.assertEqual(editor.st.cursor, 3)
        self.assertIsNone(editor._vertical_context)

    @unittest.skipUnless(all(path.is_file() for path in FIXTURES), 'local Haydn fixtures unavailable')
    def test_both_local_haydn_scores_keep_lanes_and_allow_complete_vertical_cycle(self):
        from music21 import converter
        from multiformat import score_to_import_items
        for path in FIXTURES:
            with self.subTest(score=path.name):
                score = converter.parse(path, forceSource=True)
                items = score_to_import_items(score)
                self.assertEqual(len(items), len(list(score.expandRepeats().recurse().notesAndRests)))
                lanes = {lane(i) for i in items}
                self.assertEqual(len(lanes), 4 if 'No.37' in path.name else 2)
                # Secondary voices enter in different measures; they need not
                # all sound together. Each must be reachable at its own onset.
                samples = [next(i for i in items if lane(i) == key) for key in lanes]
                slices = [vertical_notes(items, i['score_offset']) for i in samples]
                self.assertEqual({lane(items[n]) for rows in slices for n, _ in rows}, lanes)
                rows = max(slices, key=len)
                anchor = items[rows[0][0]]['score_offset']
                rows = vertical_notes(items, anchor)
                editor = self.editor(items)
                editor.st.cursor = rows[0][0]
                before = deepcopy(items)
                visited = []
                for _ in rows:
                    editor.navigate_vertical(1)
                    visited.append(editor.st.cursor)
                self.assertEqual(visited, [n for n, _ in rows])
                self.assertEqual(items, before)
