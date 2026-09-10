import pyaudiogaming.menu as menu
import core
from pyaudiogaming import vb
from pyaudiogaming.inputBox import kbt

def run():
	import pyaudiogaming.system as system
	inputs, outputs = core.input.get_device_names(), core.output.get_device_names()
	dec_index = 0
	m = menu.menu()
	m.init(core.getW(), "Settings Menu")
	m.append("Input device: %s" % core.input.find_device_by_id(core.input.device))
	m.append("Output device: %s" % core.output.find_device_by_id(core.output.device))
	
	path_keys = [
		"piano musical toolkit", "guitar musical toolkit", "drum musical toolkit",
		"bass musical toolkit", "electronic drum musical toolkit", "strings musical toolkit",
		"synth musical toolkit", "flute musical toolkit"
	]
	id_keys = [
		"guitar tools", "bass tools", "electronic drum", "strings", "synth", "flute"
	]
	
	for pk in path_keys:
		name = pk.replace(" musical toolkit", "")
		m.append(f"{name} musical data path is {core.config[pk]}")
		
	for ik in id_keys:
		m.append(f"Id {ik}: {core.config[ik]}")
		
	m.append("back")
	m.open()
	w = core.getW()
	
	path_start = 2
	id_start = path_start + len(path_keys)
	
	while True:
		w.frameUpdate()
		if w.keyPressed("f5"):
			dec_index, inputs, outputs = 0, core.input.get_device_names(), core.output.get_device_names()
			w.say(f"{len(inputs)}, {len(outputs)}")
		s = m.getCursorPos()
		if w.keyPressed("left") and s < 2:
			dec_index -= 1
			if dec_index < 0: dec_index = len(inputs)-1 if s == 0 else len(outputs)-1
			if s == 0:
				core.input.device = inputs[dec_index]
				m.modify(s, "Input device: %s" % inputs[dec_index])
				w.say(core.input.find_device_by_id(core.input.device))
			else:
				core.output.device = outputs[dec_index]
				m.modify(s, "Output device: %s" % outputs[dec_index])
				w.say(core.output.find_device_by_id(core.output.device))
			core.save()
		if w.keyPressed("right") and s < 2:
			dec_index += 1
			if s == 0:
				if dec_index >= len(inputs): dec_index = 0
				core.input.device = inputs[dec_index]
				m.modify(s, "Input device: %s" % inputs[dec_index])
				w.say(core.input.find_device_by_id(core.input.device))
			else:
				if dec_index >= len(outputs): dec_index = 0
				core.output.device = outputs[dec_index]
				m.modify(s, "Output device: %s" % outputs[dec_index])
				w.say(core.output.find_device_by_id(core.output.device))
			core.save()
		s = m.frameUpdate()
		if s is None: continue
		if s == -1 or s == len(m.items) - 1: break
		
		if path_start <= s < id_start:
			idx = s - path_start
			pk = path_keys[idx]
			name = pk.replace(" musical toolkit", "")
			fname = kbt(None, f"Select {name} musical toolkit file data", "", file_dialog=True)
			if not fname: continue
			core.config[pk] = fname
			m.modify(s, f"{name} musical data path is {core.config[pk]}")
			core.save()
			
		elif id_start <= s < id_start + len(id_keys):
			idx = s - id_start
			ik = id_keys[idx]
			numbers = kbt(None, f"Please enter id tools you want to use for {ik}!", "")
			if numbers is None: continue
			try:
				core.config[ik] = int(numbers)
				core.save()
				m.modify(s, f"Id {ik}: {core.config[ik]}")
			except ValueError:
				continue