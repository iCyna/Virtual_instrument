import tempfile
import unittest
from pathlib import Path

from mte_musicxml import load_score, score_to_import_items, render_score, score_rows, score_to_sequence
from music21 import chord, clef, meter, note, stream, tempo, tie


class MusicXMLTests(unittest.TestCase):
    def make_score(self):
        score = stream.Score()
        right = stream.Part()
        right.partName = 'Piano RH'
        measure = stream.Measure(number=1)
        measure.append(clef.TrebleClef())
        measure.append(meter.TimeSignature('4/4'))
        measure.append(tempo.MetronomeMark(number=120))
        first = note.Note('C4', quarterLength=1)
        first.tie = tie.Tie('start')
        second = note.Note('C4', quarterLength=1)
        second.tie = tie.Tie('stop')
        measure.append(first)
        measure.append(second)
        measure.append(tempo.MetronomeMark(number=60))
        measure.append(chord.Chord(['E4', 'G4'], quarterLength=1))
        measure.append(note.Rest(quarterLength=1))
        right.append(measure)
        score.append(right)
        left = stream.Part()
        left.partName = 'Piano LH'
        measure = stream.Measure(number=1)
        measure.append(clef.BassClef())
        measure.append(meter.TimeSignature('4/4'))
        measure.append(note.Note('C3', quarterLength=4))
        left.append(measure)
        score.append(left)
        return score

    def test_mxl_roundtrip_playback_and_engraving(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / 'score.mxl'
            self.make_score().write('mxl', fp=path)
            score = load_score(path)
            sequence = score_to_sequence(score)
            self.assertIn('C4@0-1000-', sequence)
            self.assertEqual(sequence.count('C4@'), 1)
            self.assertIn('E4@1000-1000-', sequence)
            self.assertIn('G4@1000-1000-', sequence)
            self.assertIn('C3@0-3000-', sequence)
            groups = score_rows(score)
            self.assertEqual(len(groups), 2)
            self.assertIn('Khóa Sol', groups[0][0])
            self.assertIn('Khóa Fa', groups[1][0])
            self.assertTrue(any('Dấu lặng' in row for row in groups[0][1]))
            self.assertIn('<svg', render_score(path))

    def test_import_reader_items(self):
        items = score_to_import_items(self.make_score())
        self.assertEqual(len(items), 5)
        self.assertEqual(items[0]['notes'], [60])
        bass = next(item for item in items if item['clef'] == 'bass')
        self.assertEqual(bass['lh_notes'], [48])
        self.assertEqual(items[0]['start_ms'], bass['start_ms'])
        self.assertEqual(chord_start := next(item['start_ms'] for item in items if len(item['notes']) == 2), 1000)
        self.assertEqual(bass['preview_ms'], 3000)
        chord_item = next(item for item in items if len(item['notes']) == 2)
        self.assertEqual(chord_item['preview_ms'], 1000)
        self.assertEqual(chord_item['score_position'], (1, 3.0))
        self.assertEqual(items[-1]['rest_clef'], 'treble')

    def test_dense_polyphonic_mxl_keeps_every_note(self):
        score = stream.Score()
        for clef_type, pitches in ((clef.TrebleClef, ['C4', 'E4', 'G4', 'C5']),
                                   (clef.BassClef, ['C3', 'G3', 'C4'])):
            part = stream.Part()
            part.append(clef_type())
            part.append(meter.TimeSignature('4/4'))
            part.append(tempo.MetronomeMark(number=120))
            first = stream.Voice()
            first.insert(0, chord.Chord(pitches, quarterLength=4))
            second = stream.Voice()
            second.insert(0, note.Note('D4', quarterLength=1))
            second.insert(1, chord.Chord(['F4', 'A4'], quarterLength=1))
            part.insert(0, first)
            part.insert(0, second)
            score.append(part)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / 'dense.mxl'
            score.write('mxl', fp=path)
            loaded = load_score(path)
            items = score_to_import_items(loaded)
            expected = sum(len(element.pitches) for element in loaded.recurse().notes)
            self.assertEqual(sum(len(item['notes']) + len(item['lh_notes']) for item in items), expected)
            self.assertEqual(len(score_to_sequence(loaded).split()), expected)
            at_start = [item for item in items if item['start_ms'] == 0]
            self.assertEqual(sum(len(item['notes']) + len(item['lh_notes']) for item in at_start), 9)

    def test_repeats(self):
        from music21 import bar
        score = self.make_score()
        for part in score.parts:
            part.measure(1).leftBarline = bar.Repeat(direction='start')
            part.measure(1).rightBarline = bar.Repeat(direction='end', times=2)
        self.assertEqual(score_to_sequence(score).count('C4@'), 2)


if __name__ == '__main__':
    unittest.main()
