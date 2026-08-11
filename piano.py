import core
from pyaudiogaming.sound_pool import musical
import setting

MIDI_EVENT_NOTE = 1

PIANO_KEYS = {
	"a": 60, "w": 61, "s": 62, "e": 63, "d": 64, 
	"f": 65, "t": 66, "g": 67, "y": 68, "h": 69, 
	"u": 70, "j": 71, "k": 72, "o": 73, "p": 75, "l": 74, "semicolon": 76
}

def run():
	w = core.getW()
	piano = musical()
	piano.create_empty_stream(channels=16)

	mfont = piano.load_font(core.config["piano musical toolkit"])
	piano.set_fonts(mfont) 
	piano.play()

	# active_notes giờ sẽ lưu theo cấu trúc: {phím: [danh sách các nốt đang phát của phím đó]}
	active_notes = {}
	octave_shift = 0
	page_up_pressed = False
	page_down_pressed = False
	import recorder
	while 1:
		w.frameUpdate() 
		recorder.mainloop(piano, w)
		if w.keyPressed("exit"): break
		
		# [Giữ nguyên logic kiểm tra quãng tám của ông...]
		if w.keyPressed("page_up"):
			if not page_up_pressed: octave_shift += 12; page_up_pressed = True
		else: page_up_pressed = False
		if w.keyPressed("lalt"):
			if not page_down_pressed: octave_shift -= 12; page_down_pressed = True
		else: page_down_pressed = False
		if w.keyPressed("ralt"):
			if not page_up_pressed: octave_shift += 12; page_up_pressed = True
		else: page_up_pressed = False
		if w.keyPressed("f1"): setting.run() 
			
		# Vòng lặp duyệt phím đàn
		for key, base_note in PIANO_KEYS.items():
			current_note = base_note + octave_shift
			upper_note = current_note + 12
			lower_note = current_note - 12
			
			if w.keyPressing(key):
				if key not in active_notes:
					notes_to_play = [current_note]
					if w.keyPressing("lshift"): notes_to_play.append(lower_note)
					if w.keyPressing("rshift"): notes_to_play.append(upper_note)
					
					for n in notes_to_play:
						piano.send_event(chan=0, event=MIDI_EVENT_NOTE, param=n | (100 << 8))
					active_notes[key] = notes_to_play
			
			elif key in active_notes:
				# Chỉ nhả những nốt mà phím này đã phát
				for n in active_notes[key]:
					piano.send_event(chan=0, event=MIDI_EVENT_NOTE, param=n | (0 << 8))
				del active_notes[key]
