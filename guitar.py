import core
from pyaudiogaming.sound_pool import musical
from pyaudiogaming.timer import Timer
import setting
import random

MIDI_EVENT_NOTE = 1
MIDI_EVENT_PROGRAM = 2

NOTE_NAMES = {
    48: "C", 49: "C sharp", 50: "D", 51: "D sharp", 52: "E", 
    53: "F", 54: "F sharp", 55: "G", 56: "G sharp", 57: "A", 
    58: "A sharp", 59: "B", 60: "C"
}

CHORD_TYPES = [
    ("Major",   [0, 4, 7, 12, 16, 19]),      
    ("Minor",   [0, 3, 7, 12, 15, 19]),      
    ("7",       [0, 4, 7, 10, 14, 17]),      
    ("Minor 7", [0, 3, 7, 10, 15, 19]),      
    ("Major 7", [0, 4, 7, 11, 14, 19]),      
    ("Sus 4",   [0, 5, 7, 12, 17, 19]),      
    ("Sus 2",   [0, 2, 7, 12, 14, 19]),      
    ("6",       [0, 4, 7, 9, 12, 16]),       
    ("Minor 6", [0, 3, 7, 9, 12, 15]),       
    ("Add 9",   [0, 4, 7, 12, 14, 19]),      
    ("Minor 9", [0, 3, 7, 10, 14, 19]),      
    ("Major 9", [0, 4, 7, 11, 14, 19]),      
    ("Diminished", [0, 3, 6, 9, 12, 15]),       
    ("Augmented",  [0, 4, 8, 12, 16, 20])       
]

ROOT_KEYS = {
    "z": 48, "x": 50, "c": 52, "v": 53,
    "m": 55, "comma": 57, "dot": 59, "slash": 60
}

STRING_KEYS = {
    "a": 0, "s": 1, "d": 2,          
    "k": 3, "l": 4, "semicolon": 5    
}

HOTKEY_NAMES = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "zero"]

def get_chord_name_str(root, type_idx):
    root_str = NOTE_NAMES.get(root, "Unknown")
    type_str = CHORD_TYPES[type_idx][0]
    return f"{root_str} {type_str}"

STRUM_BANKS = [
    ("Basic Strumming", {
        "q": ([(0, 110), (1, 102), (2, 94), (3, 86), (4, 78), (5, 70)], 25),   
        "w": ([(5, 100), (4, 90), (3, 80), (2, 70), (1, 60), (0, 50)], 25),    
        "e": ([(0, 100), (1, 100), (2, 100), (3, 100), (4, 100), (5, 100)], 90), 
        "r": ([(5, 95), (4, 95), (3, 95), (2, 95), (1, 95), (0, 95)], 90),     
        "t": ([(0, 115), (1, 105), (2, 95)], 20),                              
        "y": ([(3, 105), (4, 95), (5, 85)], 20),                               
        "u": ([(5, 100), (4, 90), (3, 80)], 20),                               
        "i": ([(0, 90), (1, 100), (2, 110)], 20),                              
        "o": ([(0, 100), (1, 100), (2, 100), (3, 100), (4, 100), (5, 100)], 140),
        "p": ([(5, 95), (4, 95), (3, 95), (2, 95), (1, 95), (0, 95)], 140),
    }),
    ("Fingerstyle and Solo", {
        "q": ([(0, 110)], 0), 
        "w": ([(1, 110)], 0), 
        "e": ([(2, 110)], 0), 
        "r": ([(3, 100)], 0), 
        "t": ([(4, 100)], 0), 
        "y": ([(5, 100)], 0), 
        "u": ([(3, 100), (4, 100), (5, 100)], 5), 
        "i": ([(0, 110), (3, 100), (4, 100), (5, 100)], 5), 
        "o": ([(-1, 110)], 0), 
        "p": ([(-2, 0)], 0),   
    }),
    ("Rock and Power Chords", {
        "q": ([(0, 120), (1, 120), (2, 115)], 15), 
        "w": ([(2, 115), (1, 120), (0, 120)], 15), 
        "e": ([(0, 115), (1, 115), (2, 115), (-2, 0)], 20), 
        "r": ([(0, 125)], 0), 
        "t": ([(0, 110), (1, 110), (2, 110), (3, 110), (4, 110), (5, 110)], 12), 
        "y": ([(5, 110), (4, 110), (3, 110), (2, 110), (1, 110), (0, 110)], 12), 
        "u": ([(3, 110), (4, 110), (5, 110)], 15), 
        "i": ([(5, 110), (4, 110), (3, 110)], 15), 
        "o": ([(-1, 127)], 0), 
        "p": ([(0, 70), (1, 70), (2, 70)], 15), 
    })
]

RHYTHM_LIST = [
    ("Standard Ballad",   [('D', 400), ('D', 400), ('U', 200), ('U', 400), ('D', 200), ('U', 200)]),
    ("Pop Rock 16th",     [('D', 200), ('D', 200), ('U', 100), ('U', 200), ('D', 100), ('U', 100)]),
    ("Acoustic Surf",     [('B', 220), ('C', 220), ('U', 220), ('C', 220)]),
    ("Bossa Nova",        [('B', 450), ('C', 450), ('U', 225), ('C', 450), ('U', 225)]),
    ("Cha Cha Cha",       [('B', 400), ('B', 400), ('C', 200), ('U', 200), ('C', 400)]),
    ("Reggae Groove",     [('S', 300), ('U', 300), ('S', 300), ('U', 300)]),
    ("Country Boom Chick",[('B', 300), ('D', 300), ('B', 300), ('D', 300)]),
    ("Folk Fingerpicking",[('B', 250), ('D', 250), ('U', 250), ('D', 250), ('B', 250), ('U', 250), ('D', 250), ('U', 250)]),
    ("R and B Slow",      [('D', 600), ('D', 200), ('U', 200), ('C', 400), ('U', 200)]),
    ("Funk Syncopation",  [('D', 150), ('C', 150), ('U', 150), ('U', 150), ('C', 150), ('D', 150)]),
    ("Waltz 3 4",         [('B', 500), ('D', 500), ('D', 500)]),
    ("Boston Slow",       [('B', 600), ('C', 600), ('U', 300), ('D', 300)]),
    ("Slow Rock 6 8",     [('B', 333), ('D', 333), ('D', 333), ('B', 333), ('D', 333), ('D', 333)]),
    ("Hard Rock Drive",   [('D', 250), ('D', 250), ('D', 250), ('D', 250), ('D', 250), ('D', 250), ('D', 250), ('D', 250)]),
    ("Metal Gallop",      [('C', 200), ('C', 100), ('C', 100), ('C', 200), ('C', 100), ('C', 100)]) 
]

def set_program(guitar, chan, program_id):
    guitar.send_event(chan=chan, event=MIDI_EVENT_PROGRAM, param=program_id)

def play_note(guitar, chan, note, velocity=100):
    guitar.send_event(chan=chan, event=MIDI_EVENT_NOTE, param=note | (velocity << 8))

def stop_note(guitar, chan, note):
    guitar.send_event(chan=chan, event=MIDI_EVENT_NOTE, param=note | (0 << 8))

def run():
    w = core.getW()
    guitar = musical()
    guitar.create_empty_stream(channels=16)

    mfont = guitar.load_font(core.config["guitar musical toolkit"])
    guitar.set_fonts(mfont) 
    guitar.play()

    guitar_program = core.config.get("guitar tools", 3)
    set_program(guitar, chan=0, program_id=guitar_program)

    current_root = 48         
    current_type_idx = 0      
    
    hotkey_slots = [None] * 10
    current_slot_idx = 0

    active_strings = {}

    current_strum_bank_idx = 0
    active_strum_seq = []
    strum_step = 0
    strum_delay = 0
    strum_timer = Timer()

    current_rhythm_idx = 0
    active_rhythm_seq = []
    rhythm_step = 0
    rhythm_delay = 0
    rhythm_timer = Timer()

    is_palm_muting = False
    mute_timer = Timer()

    def get_current_chord_notes():
        intervals = CHORD_TYPES[current_type_idx][1]
        return [current_root + offset for offset in intervals]

    w.say("Guitar ready. " + get_chord_name_str(current_root, current_type_idx))

    while 1:
        w.frameUpdate() 
        if w.keyPressed("exit"): break

        for key, root_note in ROOT_KEYS.items():
            if w.keyPressed(key):
                current_root = root_note
                w.say(get_chord_name_str(current_root, current_type_idx))

        if w.keyPressed("n"):
            current_type_idx = (current_type_idx + 1) % len(CHORD_TYPES)
            w.say(get_chord_name_str(current_root, current_type_idx))
            
        if w.keyPressed("b"):
            current_type_idx = (current_type_idx - 1) % len(CHORD_TYPES)
            w.say(get_chord_name_str(current_root, current_type_idx))

        if w.keyPressed("j"):
            current_slot_idx = (current_slot_idx + 1) % 10
            if hotkey_slots[current_slot_idx]:
                current_root, current_type_idx = hotkey_slots[current_slot_idx]
                w.say(f"Slot {current_slot_idx}: " + get_chord_name_str(current_root, current_type_idx))
            else:
                w.say(f"Slot {current_slot_idx} is empty")
                
        if w.keyPressed("f"):
            current_slot_idx = (current_slot_idx - 1) % 10
            if hotkey_slots[current_slot_idx]:
                current_root, current_type_idx = hotkey_slots[current_slot_idx]
                w.say(f"Slot {current_slot_idx}: " + get_chord_name_str(current_root, current_type_idx))
            else:
                w.say(f"Slot {current_slot_idx} is empty")

        for idx, key_name in enumerate(HOTKEY_NAMES):
            if w.keyPressed(key_name):
                if w.keyPressing("lshift") or w.keyPressing("rshift"):
                    hotkey_slots[idx] = (current_root, current_type_idx)
                    w.say(f"Saved to slot {idx}: " + get_chord_name_str(current_root, current_type_idx))
                else:
                    if hotkey_slots[idx]:
                        current_root, current_type_idx = hotkey_slots[idx]
                        current_slot_idx = idx
                        w.say(f"Loaded slot {idx}: " + get_chord_name_str(current_root, current_type_idx))
                    else:
                        w.say("Empty slot")

        if w.keyPressed("up"):
            current_rhythm_idx = (current_rhythm_idx + 1) % len(RHYTHM_LIST)
            w.say(RHYTHM_LIST[current_rhythm_idx][0])

        if w.keyPressed("down"):
            current_rhythm_idx = (current_rhythm_idx - 1) % len(RHYTHM_LIST)
            w.say(RHYTHM_LIST[current_rhythm_idx][0])

        if w.keyPressed("space"):
            if active_rhythm_seq:
                active_rhythm_seq = []
                active_strum_seq = []
                for n in range(30, 90): stop_note(guitar, chan=0, note=n)
                w.say("Stop rhythm")
            else:
                active_rhythm_seq = RHYTHM_LIST[current_rhythm_idx][1]
                rhythm_step = 0
                rhythm_delay = 0
                rhythm_timer.restart()
                w.say("Play rhythm")

        if active_rhythm_seq and rhythm_step < len(active_rhythm_seq):
            humanized_delay = rhythm_delay + random.randint(-15, 15)

            if rhythm_step == 0 or rhythm_timer.elapsed >= humanized_delay:
                stroke_type, next_delay = active_rhythm_seq[rhythm_step]
                
                if stroke_type == 'D':
                    active_strum_seq, strum_delay = STRUM_BANKS[0][1]["q"]
                elif stroke_type == 'U':
                    active_strum_seq, strum_delay = STRUM_BANKS[0][1]["w"]
                elif stroke_type == 'B':
                    active_strum_seq, strum_delay = STRUM_BANKS[0][1]["t"]
                elif stroke_type == 'C':
                    active_strum_seq, strum_delay = STRUM_BANKS[0][1]["q"]
                    is_palm_muting = True
                    mute_timer.restart() 
                elif stroke_type == 'S':
                    play_note(guitar, chan=9, note=38, velocity=110)
                    active_strum_seq = [] 
                
                if active_strum_seq:
                    strum_step = 0
                    strum_timer.restart()
                
                rhythm_delay = next_delay
                rhythm_step += 1
                
                if rhythm_step >= len(active_rhythm_seq): 
                    rhythm_step = 0
                    
                rhythm_timer.restart()

        if w.keyPressed("right"):
            current_strum_bank_idx = (current_strum_bank_idx + 1) % len(STRUM_BANKS)
            w.say("Strum Bank: " + STRUM_BANKS[current_strum_bank_idx][0])
            
        if w.keyPressed("left"):
            current_strum_bank_idx = (current_strum_bank_idx - 1) % len(STRUM_BANKS)
            w.say("Strum Bank: " + STRUM_BANKS[current_strum_bank_idx][0])

        current_strum_patterns = STRUM_BANKS[current_strum_bank_idx][1]

        for strum_key, pattern_data in current_strum_patterns.items():
            if w.keyPressed(strum_key):
                if active_rhythm_seq:
                    active_rhythm_seq = [] 
                    w.say("Stop rhythm") 
                
                if w.keyPressing("lshift") or w.keyPressing("rshift"):
                    active_strum_seq, strum_delay = pattern_data
                    is_palm_muting = True
                    mute_timer.restart()
                elif w.keyPressing("lalt"):
                    play_note(guitar, chan=9, note=38, velocity=110)
                    active_strum_seq = []
                else:
                    active_strum_seq, strum_delay = pattern_data
                    is_palm_muting = False
                
                if active_strum_seq:
                    strum_step = 0
                    strum_timer.restart()

        chord_notes = get_current_chord_notes()

        for key, string_idx in STRING_KEYS.items():
            note_to_play = chord_notes[string_idx]

            if w.keyPressing(key):
                if key not in active_strings:
                    vel = random.randint(90, 105)
                    play_note(guitar, chan=0, note=note_to_play, velocity=vel)
                    active_strings[key] = note_to_play
            elif key in active_strings:
                stop_note(guitar, chan=0, note=active_strings[key])
                del active_strings[key]

        if active_strum_seq and strum_step < len(active_strum_seq):
            if strum_step == 0 or strum_timer.elapsed >= strum_delay:
                string_idx, base_vel = active_strum_seq[strum_step]
                
                if string_idx == -1:
                    play_note(guitar, chan=9, note=38, velocity=base_vel)
                elif string_idx == -2:
                    for n in get_current_chord_notes():
                        stop_note(guitar, chan=0, note=n)
                else:
                    current_realtime_chord = get_current_chord_notes()
                    note_to_play = current_realtime_chord[string_idx]
                    final_vel = max(10, min(127, base_vel + random.randint(-5, 5)))
                    play_note(guitar, chan=0, note=note_to_play, velocity=final_vel)
                
                strum_step += 1
                strum_timer.restart()

        if is_palm_muting and strum_step >= len(active_strum_seq):
            if mute_timer.elapsed > 45: 
                for n in get_current_chord_notes():
                    stop_note(guitar, chan=0, note=n)
                is_palm_muting = False

        if w.keyPressed("lcontrol") or w.keyPressed("rcontrol"):
            if active_rhythm_seq:
                active_rhythm_seq = []
                w.say("Stop rhythm")
            for n in range(30, 90):
                stop_note(guitar, chan=0, note=n)