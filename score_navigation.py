"""Read a vertical slice of notation without changing its timing or pitches."""


def lane(item):
    return (item.get('staff_id'), item.get('voice_id'))


def vertical_notes(items, anchor):
    rows = []
    for index, item in enumerate(items):
        if 'score_offset' not in item:
            continue
        start = item['score_offset']
        duration = item.get('score_duration', item.get('beats', 0))
        if not (abs(start - anchor) < 1e-8 or start < anchor < start + duration - 1e-8):
            continue
        pitches = sorted(set(item.get('notes', []) + item.get('lh_notes', [])), reverse=True)
        voice = str(item.get('voice_id', '1'))
        voice_order = (0, int(voice)) if voice.isdigit() else (1, voice)
        for pitch in pitches or [None]:
            rows.append(((item.get('staff_order', 0), voice_order, -(pitch or 0), start, index),
                         index, pitch))
    return [(index, pitch) for _, index, pitch in sorted(rows)]
