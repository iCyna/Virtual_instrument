import tempfile
import unittest
import importlib.util
from pathlib import Path

from multiformat import load_score, score_to_import_items, render_score, score_rows, score_to_sequence
from music21 import articulations, chord, clef, expressions, key, meter, note, spanner, stream, tempo, tie


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

    def test_mxl_roundtrip_playback(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / 'score.mxl'
            self.make_score().write('mxl', fp=path)
            score = load_score(path)
            sequence = score_to_sequence(score)
            self.assertIn('C4@0-1000-', sequence)
            self.assertEqual(sequence.count('C4@'), 1)
            self.assertIn('E4@1000-850-', sequence)
            self.assertIn('G4@1000-850-', sequence)
            self.assertIn('C3@0-2550-', sequence)
            groups = score_rows(score)
            self.assertEqual(len(groups), 2)
            self.assertIn('Khóa Sol', groups[0][0])
            self.assertIn('Khóa Fa', groups[1][0])
            self.assertTrue(any('Dấu lặng' in row for row in groups[0][1]))

    @unittest.skipUnless(importlib.util.find_spec('verovio'), 'verovio is not installed')
    def test_engraving(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / 'score.mxl'
            self.make_score().write('mxl', fp=path)
            self.assertIn('<svg', render_score(path))

    def test_import_reader_items(self):
        items = score_to_import_items(self.make_score())
        self.assertEqual(len(items), 5)
        self.assertEqual(items[0]['preview_ms'], 500)
        self.assertEqual(items[0]['playback_events'][0]['duration_ms'], 1000)
        self.assertEqual(items[2]['playback_events'], [])
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

    def ornament_score(self, ornament=None):
        score = stream.Score()
        part = stream.Part()
        measure = stream.Measure(number=1)
        measure.append(meter.TimeSignature('4/4'))
        measure.append(tempo.MetronomeMark(number=120))
        measure.append(key.KeySignature(1))
        first = note.Note('E4', quarterLength=1)
        if ornament:
            first.expressions.append(ornament)
        measure.append(first)
        measure.append(note.Note('G4', quarterLength=1))
        part.append(measure)
        score.append(part)
        return score

    def test_ornaments_play_in_both_import_paths(self):
        for ornament in (expressions.Trill(), expressions.Mordent(), expressions.Turn()):
            with self.subTest(ornament=type(ornament).__name__):
                score = self.ornament_score(ornament)
                sequence = score_to_sequence(score)
                items = score_to_import_items(score)
                self.assertGreater(len(sequence.split()), 2)
                self.assertEqual(len(items), 2)
                self.assertEqual(len(sequence.split()), sum(len(i['playback_events']) for i in items))
                self.assertEqual(items[-1]['start_ms'], 500)
                self.assertEqual(len(score.recurse().notes), 2)
                self.assertEqual(len(score.recurse().notes[0].expressions), 1)
        self.assertIn('F#4@', score_to_sequence(self.ornament_score(expressions.Trill())))

    def test_slur_connects_different_pitches_without_merging(self):
        score = self.ornament_score()
        score.parts[0].insert(0, spanner.Slur(list(score.recurse().notes)))
        items = score_to_import_items(score)
        self.assertEqual(len(items), 2)
        self.assertGreater(items[0]['playback_events'][0]['duration_ms'], 500)
        self.assertEqual(items[1]['start_ms'], 500)
        self.assertEqual(items[1]['preview_ms'], 500)

    def test_grace_note_borrows_time_without_shifting_next_beat(self):
        score = self.ornament_score()
        measure = score.parts[0].measure(1)
        measure.insert(0, note.Note('D4').getGrace())
        items = score_to_import_items(score)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]['notes'], [62])
        self.assertTrue(items[0]['grace'])
        self.assertGreater(items[0]['playback_events'][0]['duration_ms'], 10)
        self.assertEqual(items[1]['playback_events'][0]['offset_ms'], items[0]['playback_events'][0]['duration_ms'])
        self.assertEqual(items[-1]['start_ms'], 500)

    def test_partial_chord_tie_holds_only_the_tied_pitch(self):
        score = self.ornament_score()
        measure = score.parts[0].measure(1)
        for n in list(measure.notes):
            measure.remove(n)
        first = chord.Chord(['C4', 'E4'], quarterLength=1)
        second = chord.Chord(['C4', 'F4'], quarterLength=1)
        first.notes[0].tie = tie.Tie('start')
        second.notes[0].tie = tie.Tie('stop')
        measure.insert(0, first)
        measure.insert(1, second)
        sequence = score_to_sequence(score)
        self.assertEqual(sequence.count('C4@'), 1)
        self.assertIn('C4@0-1000-', sequence)
        self.assertIn('E4@0-425-', sequence)
        self.assertIn('F4@500-425-', sequence)
        items = score_to_import_items(score)
        self.assertEqual([i['notes'] for i in items], [[60, 64], [60, 65]])
        self.assertEqual(sum(len(e['notes']) for i in items for e in i['playback_events']), 3)

    def test_lower_staff_stays_separate_when_clef_changes(self):
        score = self.ornament_score()
        score.parts[0].measure(1).insert(0, clef.TrebleClef())
        lower = stream.PartStaff(id='Piano-Staff2')
        measure = stream.Measure(number=1)
        measure.insert(0, clef.TrebleClef())
        measure.insert(0, meter.TimeSignature('4/4'))
        measure.insert(0, note.Note('C4', quarterLength=1))
        measure.insert(1, clef.BassClef())
        measure.insert(1, note.Note('C3', quarterLength=1))
        lower.append(measure)
        score.append(lower)
        lower_items = [i for i in score_to_import_items(score) if i['clef'] == 'bass']
        self.assertEqual([i['lh_notes'] for i in lower_items], [[60], [48]])
        self.assertEqual([i['notation_clef'] for i in lower_items], ['treble', 'bass'])
        self.assertEqual([i['score_position'] for i in lower_items], [(1, 1.0), (1, 2.0)])

    def test_articulations_have_distinct_gates_without_changing_rhythm(self):
        expected = [(articulations.Staccatissimo(), 100),
                    (articulations.Staccato(), 200),
                    (articulations.Spiccato(), 150),
                    (articulations.DetachedLegato(), 325),
                    (articulations.Tenuto(), 500), (None, 425)]
        for mark, sounding_ms in expected:
            with self.subTest(mark=mark):
                score = self.ornament_score()
                if mark:
                    score.recurse().notes[0].articulations.append(mark)
                items = score_to_import_items(score)
                self.assertEqual(items[0]['beats'], 1)
                self.assertEqual(items[0]['preview_ms'], 500)
                self.assertEqual(items[1]['start_ms'], 500)
                self.assertEqual(items[0]['playback_events'][0]['duration_ms'], sounding_ms)
                self.assertIn(f'E4@0-{sounding_ms}-', score_to_sequence(score))

    def test_staccato_overrides_slur_and_is_visible_to_reader(self):
        score = self.ornament_score()
        first, second = list(score.recurse().notes)
        first.articulations.append(articulations.Staccato())
        score.parts[0].insert(0, spanner.Slur(first, second))
        items = score_to_import_items(score)
        self.assertEqual(items[0]['playback_events'][0]['duration_ms'], 200)
        self.assertIn('staccato', items[0]['notation_marks'])
        self.assertIn('luyến', items[0]['notation_marks'])

    def test_tied_chord_only_shortens_the_final_tied_segment(self):
        score = self.ornament_score()
        measure = score.parts[0].measure(1)
        for element in list(measure.notes):
            measure.remove(element)
        first = chord.Chord(['C4', 'E4'], quarterLength=1)
        second = chord.Chord(['C4', 'F4'], quarterLength=1)
        first.notes[0].tie = tie.Tie('start')
        second.notes[0].tie = tie.Tie('stop')
        second.articulations.append(articulations.Staccatissimo())
        measure.insert(0, first)
        measure.insert(1, second)
        sequence = score_to_sequence(score)
        self.assertEqual(sequence.count('C4@'), 1)
        self.assertIn('C4@0-600-', sequence)
        self.assertIn('F4@500-100-', sequence)
        self.assertIn('E4@0-425-', sequence)


if __name__ == '__main__':
    unittest.main()
