"""MusicXML playback conversion and an accessible, engraved score reader."""
import html
import os
from pathlib import Path
import sys
import tempfile

# A project-local install is useful on machines without writable site-packages.
_deps = Path(__file__).resolve().parent / '.mxl_deps'
if _deps.is_dir():
    sys.path.append(str(_deps))


def load_score(path):
    from music21 import converter
    score = converter.parse(str(path))
    if not score.parts:
        raise ValueError('The file has no musical parts')
    return score


def score_to_sequence(score):
    """Use the score-wide tempo map, preserving polyphony and tied durations."""
    performed = score.expandRepeats()
    performed = performed.stripTies()
    tokens = []
    for entry in performed.flatten().secondsMap:
        element = entry['element']
        if not getattr(element, 'isNote', False) and not getattr(element, 'isChord', False):
            continue
        start = round(entry['offsetSeconds'] * 1000)
        duration = max(10, round(entry['durationSeconds'] * 1000))
        velocity = element.volume.velocity
        velocity = max(1, min(127, velocity if velocity is not None else 90))
        for pitch in element.pitches:
            midi = pitch.midi
            name = ('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')[midi % 12]
            tokens.append((start, f'{name}{midi // 12 - 1}@{start}-{duration}-{velocity}'))
    return ' '.join(token for _, token in sorted(tokens, key=lambda value: value[0]))


def score_to_import_items(score):
    """Build editable reader steps from notation, with score-wide preview timing."""
    from music21 import clef
    performed = score.expandRepeats()
    timing = {id(entry['element']): entry for entry in performed.flatten().secondsMap}
    events = []
    for part_index, part in enumerate(performed.parts):
        for element in part.recurse().notesAndRests:
            duration = element.duration
            if duration.quarterLength <= 0:
                continue
            current = element.getContextByClass(clef.Clef)
            clef_name = {'G': 'treble', 'F': 'bass', 'C': 'alto'}.get(
                getattr(current, 'sign', 'G'), 'treble')
            pitches = [] if element.isRest else [p.midi for p in element.pitches]
            entry = timing[id(element)]
            offset = float(element.getOffsetInHierarchy(performed))
            item = {
                'clef': clef_name,
                'notes': pitches if clef_name != 'bass' else [],
                'lh_notes': pitches if clef_name == 'bass' else [],
                'beats': float(duration.quarterLength),
                'dur_name': duration.type,
                'score_duration': float(duration.quarterLength),
                'dotted': bool(duration.dots),
                'triplet': bool(duration.tuplets),
                'pedal': False, 'style_idx': 1,
                'start_ms': round(entry['offsetSeconds'] * 1000),
                'velocity': getattr(getattr(element, 'volume', None), 'velocity', None) or 90,
                'preview_ms': max(10, round(entry['durationSeconds'] * 1000)),
                'score_position': (element.measureNumber or 1, float(element.beat)),
            }
            if element.isRest:
                item['rest_clef'] = clef_name
            if getattr(element, 'tie', None):
                item['dur_name'] += ', tie ' + element.tie.type
            events.append((offset, part_index, item))
    return [item for _, _, item in sorted(events, key=lambda row: row[:2])]


def score_rows(score):
    from music21 import clef
    groups = {}
    for index, part in enumerate(score.parts):
        for element in part.recurse().notesAndRests:
            current = element.getContextByClass(clef.Clef)
            sign = getattr(current, 'sign', 'G')
            name = {'G': 'Khóa Sol', 'F': 'Khóa Fa', 'C': 'Khóa Đô'}.get(sign, str(sign))
            label = f'{part.partName or "Part " + str(index + 1)} — {name}'
            key = (index, sign, getattr(current, 'line', 2))
            if key not in groups:
                groups[key] = (label, [])
            pitches = 'Dấu lặng' if element.isRest else ', '.join(p.nameWithOctave for p in element.pitches)
            duration = element.duration
            details = f'{duration.type}, {float(duration.quarterLength):g} phách'
            if duration.dots:
                details += f', {duration.dots} chấm dôi'
            if duration.tuplets:
                details += ', liên âm'
            if getattr(element, 'tie', None):
                details += f', nối {element.tie.type}'
            text = f'Ô nhịp {element.measureNumber}, phách {element.beat:g}: {pitches}, {details}'
            groups[key][1].append(text)
    return list(groups.values())


def render_score(path):
    import verovio
    toolkit = verovio.toolkit()
    toolkit.setOptions({'pageWidth': 1800, 'scale': 45, 'adjustPageHeight': True})
    if not toolkit.loadFile(str(path)):
        raise ValueError('Cannot engrave this MusicXML file')
    return '\n'.join(toolkit.renderToSVG(page) for page in range(1, toolkit.getPageCount() + 1))


def show_score_reader(app, path, score, engraved):
    """Native controls expose every note to NVDA/JAWS; WebView shows full notation."""
    import wx
    import wx.html2
    groups = score_rows(score)
    if not groups:
        raise ValueError('The score contains no notes or rests')
    with tempfile.TemporaryDirectory(prefix='instrument-score-') as folder:
        document = Path(folder) / 'score.html'
        document.write_text('<!doctype html><html><meta charset="utf-8"><title>'
                            + html.escape(os.path.basename(path))
                            + '</title><body>' + engraved + '</body></html>', encoding='utf-8')
        dialog = wx.Dialog(None, title='Bản nhạc — ' + os.path.basename(path),
                           size=(1100, 800), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        layout = wx.BoxSizer(wx.VERTICAL)
        layout.Add(wx.StaticText(dialog, label='Alt+Lên/Xuống: đổi khóa. Trái/Phải: đọc nốt. Escape: đóng.'), 0, wx.ALL, 8)
        choice = wx.Choice(dialog, choices=[group[0] for group in groups])
        choice.SetName('Khóa nhạc')
        choice.SetSelection(0)
        layout.Add(choice, 0, wx.EXPAND | wx.ALL, 5)
        notes = wx.ListBox(dialog, choices=groups[0][1], size=(-1, 160))
        notes.SetName('Các nốt trong khóa')
        layout.Add(notes, 0, wx.EXPAND | wx.ALL, 5)
        view = wx.html2.WebView.New(dialog)
        view.LoadURL(document.as_uri())
        layout.Add(view, 1, wx.EXPAND)
        close = wx.Button(dialog, wx.ID_CANCEL, 'Đóng')
        layout.Add(close, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        dialog.SetSizer(layout)

        def speak():
            index = notes.GetSelection()
            if index != wx.NOT_FOUND:
                app.announce(notes.GetString(index))

        def change_group(event=None):
            label, rows = groups[choice.GetSelection()]
            notes.Set(rows)
            notes.SetSelection(0)
            notes.SetFocus()
            app.announce(label + '. ' + rows[0])

        def key(event):
            code = event.GetKeyCode()
            if event.AltDown() and code in (wx.WXK_UP, wx.WXK_DOWN):
                delta = -1 if code == wx.WXK_UP else 1
                choice.SetSelection((choice.GetSelection() + delta) % len(groups))
                change_group()
            elif code in (wx.WXK_LEFT, wx.WXK_RIGHT):
                delta = -1 if code == wx.WXK_LEFT else 1
                index = max(0, min(notes.GetCount() - 1, notes.GetSelection() + delta))
                notes.SetSelection(index)
                notes.EnsureVisible(index)
                speak()
            elif code == wx.WXK_ESCAPE:
                dialog.EndModal(wx.ID_CANCEL)
            else:
                event.Skip()

        choice.Bind(wx.EVT_CHOICE, change_group)
        notes.Bind(wx.EVT_LISTBOX, lambda event: speak())
        dialog.Bind(wx.EVT_CHAR_HOOK, key)
        change_group()
        try:
            dialog.ShowModal()
        finally:
            dialog.Destroy()
