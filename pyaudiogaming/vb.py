# -*- coding: utf-8 -*-
#virtual box multifunctional
# copyright 2025 belong ihcyna (Labubu)<phucnggo29@gmail.com>.

import pygame
from .sound_pool import playsingle
from .utils import get_window

INPUT_CONFIG={
	"callback-default": None, # will replace this as default value callback in frame of input box or form box, if value of user put when calling input or form is None. Note, if this value is None it will pass
	"read char": True,
	"read word": True,
	"permissions": [
		-1, # will Allows everything as read copy, edit, write, paste, bla bla
		0, # can write
		1, # can delete
		2, # can read
		3, # can capital letters
		4, # can non-latin
		5, # can space
		6, # can new line
		7, # can symbols
		8, # can letters
		9, # can numbers
		10, # can undo
		11, # can redo
		12, 13, 14, # can cut if 1th and 13th permissions are allowd. can copy. can paste.
	],
	"blank-sound": None,
	"write-sound": None,
	"capital write-sound": None,
	"delete-sound": None,
	"space-sound": None,
	"new line-sound": None,
	"open-sound": None,
	"confirm-sound": None,
	"exit-sound": None,
	"edge text-sound": None,
	"move text-sound": None,
	"move line-sound": None,
	"undo-sound": None,
	"redo-sound": None,
	"cut-sound": None,
	"copy-sound": None,
	"paste-sound": None,
	"cannot write-sound": None,
	"cannot capital write-sound": None,
	"cannot read-sound": None,
	"cannot delete-sound": None,
	"cannot undo-sound": None,
	"cannot redo-sound": None,
	"cannot cut-sound": None,
	"cannot copy-sound": None,
	"cannot paste-sound": None,
	"blank-text": "blank",
	"space-text": "%s space",
	"new line-text": "line feed",
	"capital-text": "CAPITAL %s",
	"delete-text": "%s deleting",
	"unselected-text": "Unselected",
	"select all-text": "%s selected",
	"select max-text": "%d characters",
	"select max all-text": "all",
	"select max all": -1, # default -1 will say 500 characters selected when the length of text is than 500 characters, 0 is just say all selected, 1 or more will say max characters when selected,
	"select all-sound": None,
	"cannot write-text": "",
	"cannot capital write-text": "",
	"cannot read-text": "star",
	"cannot delete-text": "",
	"cannot undo-text": "",
	"cannot redo-text": "",
	"cannot cut-text": "No cutting allowed here",
	"cannot copy-text": "No copying allowed here",
	"cannot paste-text": "No pasting allowed here",
}

def message(m, callback=None, open=None, move=None, close=None, window=None):
	if not window: window=get_window()
	window.say(m)
	if not open:
		playsingle(open)
	while True:
		window.frameUpdate()
		if window.keyPressed("left") or window.keyPressed("right") or window.keyPressed("up") or window.keyPressed("down"):
			if move: playsingle(move)
			window.say(m)
		if window.keyPressed("enter") or window.keyPressed("exit"):
			if close: playsingle(close)
			break

def get_conput(name, key, fallback=None):
	# returned config input text
	try:
		return INPUT_CONFIG.get(f"{key}-{name}", fallback) if key != "" else {k: v for k,v in INPUT_CONFIG.items() if f"-{name}" in k}
	except: return fallback

def set_conput(data, fallback={}):
	global INPUT_CONFIG
	try:
		for a, b in data.items():
			INPUT_CONFIG[a]=b
		return INPUT_CONFIG
	except: return fallback

def input(title="", text="", callback=None, password=False, get_data=True, new_config={}):
	from .buffer import frame as bf
	bf.say(title)
	lines = text.split("\n") if text else [""]
	config=INPUT_CONFIG.copy()
	if new_config:
		for a, b in new_config.items():
			config[a]=b
	if password:
		per=[-1,2,4,5,6,12,13,14]
		config["permissions"] =[i for i in config["permissions"] if i not in per]
	x=0
	y=0
	startx, endx=-1,-1
	starty, endy=-1,-1
	pygame.key.start_text_input()
	editing = ""
	pms=config["permissions"]
	def check_perm(char):
		if -1 in pms: return True
		if 0 not in pms: return False # Không có quyền write chung
		
		is_space = (char == " ")
		is_num = char.isdigit()
		is_alpha = char.isalpha()
		is_upper = char.isupper()
		is_latin = char.isascii() and is_alpha # A-Z, a-z
		is_non_latin = not char.isascii() and is_alpha # Tiếng Việt có dấu, chữ Hán, Nhật...
		if is_space and 5 not in pms: return False
		if is_num and 9 not in pms: return False
		
		if is_alpha:
			if 8 not in pms: return False
			if is_upper and 3 not in pms: return False
			if is_non_latin and 4 not in pms: return False
			
		if not is_space and not is_num and not is_alpha:
			if 7 not in pms: return False # Ký tự đặc biệt (symbols)
			
		return True

	def play(snd_key, txt_key, *args):
		if config.get(snd_key):
			playsingle(config[snd_key])
		elif config.get(txt_key):
			txt = config[txt_key]
			if args: txt = txt % args
			if txt != "": bf.say(txt)
	while True:
		bf.frameUpdate()
		if bf.keyPressed("backspace"):
			if x > 0:
				# Xóa chữ bên trái con trỏ (x-1)
				play("delete-sound", "delete-text", lines[y][x-1])
			elif y > 0:
				play("delete-sound", "delete-text", config["new line-text"])
			else:
				play("edge text-sound", None)
		for event in pygame.event.get():
			if event.type == pygame.TEXTEDITING:
				editing = event.text

			elif event.type == pygame.TEXTINPUT:
				valid_text = ""
				for char in event.text:
					if check_perm(char):
						valid_text += char
					else:
						play("cannot write-sound", "cannot write-text")
				if valid_text:
					lines[y] = lines[y][:x] + valid_text + lines[y][x:]
					x += len(valid_text)
					editing = ""
					if valid_text.isupper() and len(valid_text) == 1:
						play("capital write-sound", "capital-text", valid_text)
						if config.get("read char"): 
							bf.say(valid_text)
					elif valid_text == " ":
						if config.get("read word"):
							text_before_space = lines[y][:x-1]
							words = text_before_space.split()
							if words:
								play("space-sound", "space-text", words[-1])
					else:
						play("write-sound", None)
						if config.get("read char"): 
							bf.say(valid_text)

			elif event.type == pygame.KEYDOWN:
				if event.key == pygame.K_BACKSPACE:
					if x > 0:
						lines[y] = lines[y][:x-1] + lines[y][x:]
						x -= 1
					elif y > 0:
						x = len(lines[y-1])
						lines[y-1] += lines[y]
						lines.pop(y)
						y -= 1

		if bf.keyPressed("enter"):
			if (bf.keyPressing("lshift") or bf.keyPressing("rshift")) and get_data:
				if -1 in pms or (0 in pms and 6 in pms):
					right_part = lines[y][x:]
					lines[y] = lines[y][:x]
					lines.insert(y+1, right_part)
					y += 1
					x = 0
					play("new line-sound", None)
					if not lines[y]: bf.say(config.get("blank-text", "blank"))
				else:
					play("cannot write-sound", "cannot write-text")
			elif get_data:
				pygame.key.stop_text_input()
				return "\n".join(lines)

		if bf.keyPressing("left", 200):
			if x > 0:
				x -= 1
				play("move text-sound", None)
				bf.say(lines[y][x])
			elif y > 0:
				y -= 1
				x = len(lines[y])
				play("move text-sound", None) # Vẫn dùng text-sound vì đang đi ngang
				bf.say(config.get("new line-text", "line feed"))
			else:
				play("edge text-sound", None)
				if lines[y] and x < len(lines[y]): 
					bf.say(lines[y][x]) # Đọc lại ký tự đầu tiên
				else: 
					bf.say(config.get("blank-text", "blank"))

		if bf.keyPressing("right", 200):
			if x < len(lines[y]):
				x += 1
				play("move text-sound", None)
				bf.say(lines[y][x-1])
			elif y < len(lines) - 1:
				y += 1
				x = 0
				play("move text-sound", None)
				bf.say(config.get("new line-text", "line feed"))
			else:
				play("edge text-sound", None)
				if lines[y] and x > 0: 
					bf.say(lines[y][x-1]) # Đọc lại ký tự cuối cùng
				else: 
					bf.say(config.get("blank-text", "blank"))

		if bf.keyPressing("up", 200):
			if y > 0:
				y -= 1
				x = min(x, len(lines[y]))
				play("move line-sound", None)
				if lines[y]: bf.say(lines[y])
				else: bf.say(config.get("blank-text", "blank"))
			else:
				play("edge text-sound", None)
				bf.say(lines[y] if lines[y] else config.get("blank-text", "blank"))

		if bf.keyPressing("down", 200):
			if y < len(lines) - 1:
				y += 1
				x = min(x, len(lines[y]))
				play("move line-sound", None)
				if lines[y]: bf.say(lines[y])
				else: bf.say(config.get("blank-text", "blank"))
			else:
				play("edge text-sound", None)
				bf.say(lines[y] if lines[y] else config.get("blank-text", "blank"))

		# --- Phím chức năng ngoài ---
		if bf.keyPressed("exit"): 
			pygame.key.stop_text_input()
			return None
		if bf.keyPressed("lalt"): bf.say(lines)