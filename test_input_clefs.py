"""Exercise editor navigation without starting the platform audio engine."""
import ast
from pathlib import Path
import unittest

source = ast.parse(Path(__file__).with_name('mte_importmode.py').read_text(encoding='utf-8'))
methods = {'switch_clef', 'clef_notes', 'navigate_clef', 'toggle_preview_play'}
classes = []
for node in source.body:
    if isinstance(node, ast.ClassDef) and node.name == 'ImportModeState':
        classes.append(node)
    elif isinstance(node, ast.ClassDef) and node.name == 'ImportModeEditor':
        node.body = [method for method in node.body if isinstance(method, ast.FunctionDef) and method.name in methods]
        classes.append(node)
namespace = {}
exec(compile(ast.Module(body=classes, type_ignores=[]), '<editor navigation>', 'exec'), namespace)


class ClefTests(unittest.TestCase):
    def setUp(self):
        self.editor = namespace['ImportModeEditor']()
        self.editor.st = namespace['ImportModeState']()
        self.messages = []
        self.editor.announce = self.messages.append
        self.editor.speak_current = lambda: None

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

    def test_empty_clef_keeps_cursor(self):
        self.editor.st.active_clef = 'alto'
        self.editor.st.items = [{'notes': [60]}]
        self.editor.navigate_clef(1)
        self.assertEqual(self.editor.st.cursor, 0)
        self.assertTrue(self.messages)


if __name__ == '__main__':
    unittest.main()
