import core
from pyaudiogaming.sound_pool import musical
import setting
import recorder

MIDI_EVENT_NOTE = 1

# Ánh xạ phím bấm sang mã nốt MIDI cho Bộ gõ / Trống / Kèn
# Dòng phím số 1-8: Kèn / Nhạc cụ có cao độ (phát trên chan=0)
# Các phím chữ: Bộ gõ & Trống (phát trên chan=9 - MIDI Drum Channel)
PERCUSSION_KEYS = {
    # === KÈN / CÒI (Phát theo tone cao độ) ===
    "one": (60, "brass"), # Kèn Cùng (C4)
    "two": (62, "brass"), # D4
    "three": (64, "brass"), # E4
    "four": (65, "brass"), # F4
    "five": (67, "brass"), # G4
    "six": (69, "brass"), # A4
    "seven": (71, "brass"), # B4
    "eight": (72, "brass"), # C5

    # === BỘ TRỐNG (Drum Kit - Chan 9) ===
    "space": (36, "drum"),  # Trống cái (Bass Drum / Kick)
    "a": (38, "drum"),      # Trống Snare
    "s": (40, "drum"),      # Trống Snare phụ
    "d": (41, "drum"),      # Trống Tom thấp (Low Tom)
    "f": (45, "drum"),      # Trống Tom trung (Mid Tom)
    "g": (50, "drum"),      # Trống Tom cao (High Tom)

    # === XÈNG / CHIÊNG / CHẢM CHỌE (Cymbals & Gongs - Chan 9) ===
    "h": (49, "drum"),      # Chiêng / Chũm chọe to (Crash Cymbal)
    "j": (57, "drum"),      # Chiêng / Chũm chọe 2 (Crash Cymbal 2)
    "k": (51, "drum"),      # Chũm chọe nhịp (Ride Cymbal)
    "l": (55, "drum"),      # Chiêng Tàu / Splash Cymbal

    # === BỘ HIỆU ỨNG GÕ (Percussion / Hi-Hat - Chan 9) ===
    "w": (42, "drum"),      # Hi-Hat đóng (Closed Hi-Hat)
    "e": (46, "drum"),      # Hi-Hat mở (Open Hi-Hat)
    "r": (44, "drum"),      # Pedal Hi-Hat
    "u": (54, "drum"),      # Leng keng / Chập chả (Tambourine)
    "i": (56, "drum"),      # Chuông bò / Mõ sắt (Cowbell)
    "o": (60, "drum"),      # Bongo cao
    "p": (61, "drum")       # Bongo thấp
}

def run():
    w = core.getW()
    drums = musical()
    drums.create_empty_stream(channels=16)

    # Load SoundFont bộ trống / kèn của bạn
    mfont = drums.load_font(core.config["drum musical toolkit"])
    drums.set_fonts(mfont) 
    drums.play()

    active_notes = {}
    octave_shift = 0
    page_up_pressed = False
    page_down_pressed = False

    while 1:
        w.frameUpdate() 
        recorder.mainloop(drums, w)
        if w.keyPressed("exit"): break
        
        # Điều chỉnh quãng tám (chỉ áp dụng cho Kèn/Brass)
        if w.keyPressed("page_up") or w.keyPressed("ralt"):
            if not page_up_pressed: 
                octave_shift += 12
                page_up_pressed = True
        else: 
            page_up_pressed = False

        if w.keyPressed("lalt"):
            if not page_down_pressed: 
                octave_shift -= 12
                page_down_pressed = True
        else: 
            page_down_pressed = False

        if w.keyPressed("f1"): 
            setting.run() 
            
        # Vòng lặp xử lý phím gõ
        for key, (base_note, inst_type) in PERCUSSION_KEYS.items():
            # Xác định kênh (Channel 9 cho Trống/Gõ, Channel 0 cho Kèn)
            channel = 9 if inst_type == "drum" else 0
            
            # Chỉ dịch quãng tám nếu là kèn, bộ gõ giữ nguyên nốt chuẩn MIDI
            current_note = (base_note + octave_shift) if inst_type == "brass" else base_note
            upper_note = current_note + 12
            lower_note = current_note - 12
            
            if w.keyPressing(key):
                if key not in active_notes:
                    notes_to_play = [current_note]
                    
                    # Giữ Shift để đánh kèm nốt phụ (chỉ áp dụng kèn hoặc muốn đánh kép)
                    if w.keyPressing("lshift"): notes_to_play.append(lower_note)
                    if w.keyPressing("rshift"): notes_to_play.append(upper_note)
                    
                    for n in notes_to_play:
                        drums.send_event(chan=channel, event=MIDI_EVENT_NOTE, param=n | (100 << 8))
                    active_notes[key] = (channel, notes_to_play)
            
            elif key in active_notes:
                saved_chan, notes_list = active_notes[key]
                for n in notes_list:
                    drums.send_event(chan=saved_chan, event=MIDI_EVENT_NOTE, param=n | (0 << 8))
                del active_notes[key]