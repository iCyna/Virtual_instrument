import sys
import core
from pyaudiogaming.sound_pool import input, output
from pyaudiogaming import vb
def load(w):
	import pyaudiogaming.file as pf
	loads=core.config
	core.frame=w
	core.getW().fp=60
	core.getW().exit_callback=sys.exit
	f=pf.File(password="config key", encode=True, aes=True)
	if f.check("settings.tl"):
		loads =f.load("settings.tl", mode="rb+", type="json")
		for x,y in core.config.items():
			if x not in loads: loads[x]=y
	core.config=loads
	core.input = input()
	core.output = output(bbuffer=50)
	core.input.device, core.output.device, = core.config.get("input device", -1), core.config.get("output device", -1)

def mainmenu():
	import pyaudiogaming.menu as menu
	m=menu.menu()
	m.init(core.getW(), "Welcome you to main menu., please select...")
	for name in core.menus:
		m.append(name)
	m.open()
	while 1:
		core.getW().frameUpdate()
		s=m.frameUpdate()
		if s is None: continue
		if s == -1: break
		if s>=0:
			#try:
			core.menus[list(core.menus.keys())[s]].run()
			#except Exception as e:
			#	vb.message(str(e))