import pyaudiogaming.menu as menu
import core
from pyaudiogaming import vb
from pyaudiogaming.inputBox import kbt

def run():
	import pyaudiogaming.system as system
	inputs, outputs, =core.input.get_device_names(), core.output.get_device_names()
	dec_index=0
	m = menu.menu()
	m.init(core.getW(), "Settings Menu")
	m.append("Input device: %s"%core.input.find_device_by_id(core.input.device))
	m.append("Output device: %s"%core.output.find_device_by_id(core.output.device))
	m.append("piano musical data path is %s"%core.config["piano musical toolkit"])
	m.append("guitar musical data path is %s"%core.config["guitar musical toolkit"])
	m.append("Id guitar tools: %d"%core.config["guitar tools"])
	m.append("back")
	m.open()
	w=core.getW()
	while True:
		w.frameUpdate()
		if w.keyPressed("f5"):
			dec_index, inputs, outputs, =0, core.input.get_device_names(), core.output.get_device_names()
			w.say(f"{len(inputs), len(outputs)}")
		s=m.getCursorPos()
		if w.keyPressed("left") and s<2:
			dec_index-=1
			if dec_index <0: dec_index =len(inputs)-1 if s==0 else len(outputs)-1
			if s==0:
				core.input.device = inputs[dec_index]
				m.modify(s, "input device: %s"%inputs[dec_index])
				w.say(core.input.find_device_by_id(core.input.device))
			else:
				core.output.device = outputs[dec_index]
				m.modify(s, "Output device: %s"%outputs[dec_index])
				w.say(core.output.find_device_by_id(core.output.device))
			core.save()
		if w.keyPressed("right") and s<2:
			dec_index+=1
			if s==0:
				if dec_index >=len(inputs): dec_index=0
				core.input.device = inputs[dec_index]
				m.modify(s, "input device: %s"%inputs[dec_index])
				w.say(core.input.find_device_by_id(core.input.device))
			else:
				if dec_index >=len(outputs): dec_index=0
				core.output.device = outputs[dec_index]
				m.modify(s, "Output device: %s"%outputs[dec_index])
				w.say(core.output.find_device_by_id(core.output.device))
			core.save()
		s = m.frameUpdate()
		if s is None: continue
		if s == -1 or s == len(m.items)-1: break
		if s==2:
			fname = kbt(None, "Select piano musical toolkit file data", "", file_dialog=True)
			if not fname: continue
			core.config["piano musical toolkit"] =fname
			m.modify(s,"piano musical data path is %s"%core.config["piano musical toolkit"])
			core.save()
		if s==3:
			fname = kbt(None, "Select guitar musical toolkit file data", "", file_dialog=True)
			if not fname: continue
			core.config["guitar musical toolkit"] =fname
			m.modify(s,"guitar musical data path is %s"%core.config["piano musical toolkit"])
			core.save()
		if s ==4:
			numbers=kbt(None, "Please enter id tools you want to use!", "")
			if numbers is None: continue
			core.config["guitar tools"]=int(numbers)
			core.save()
			m.modify(s, "Id guitar tools: %d"%core.config["guitar tools"])