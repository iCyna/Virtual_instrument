import random, time
t=time.time()
from pyaudiogaming.window import *
from pyaudiogaming.sound_pool import *
from pyaudiogaming.key import *
from pyaudiogaming import menu, buffer as bf
import os

w=Window()
w.init(10,10,"gold wave music")
w.say(str(time.time()-t))
o=output()
o.device=4
path="e:/skill"
l=os.listdir(path)
name = ""
fxx=""
index=20
s=sound()
s.load(path+"/"+l[index])
def fxmenu(style):
	m=menu.menu()
	m.init(w, "Please select fx or filter")
	for x in list(getattr(buffer.hfxbuffers["basic"], style)):
		m.append(x)
	m.open()
	while 1:
		w.frameUpdate()
		s=m.frameUpdate()
		if s is None: continue
		if s==-1: break
		if s>-1: return m.getString(s)

while True:
	w.frameUpdate()
	if index <0 or index >len(l)-1:pass
	if index >= 0 and index <len(l) and l[index] != name:
		w.say(l[index])
		if s and s.playing: s.stop()
		s=sound()
		try:
			s.stream(path+"/"+l[index], mono=True)
			#s.set_tone(0)
			s.setfx(fxx)
			#s.set3d(0,0,0,0,0,0)
			s.play()
		except:pass
		name=l[index]
	if w.keyPressing(k.up.value, t=180) and index >0: index -=1
	if w.keyPressing(k.down.value, t=180) and index < len(l): index +=1
	if w.keyPressed(k.space.value): s.slide3d(0,0,0,50, 0,0, 1000)
	if w.keyPressed("tab"):
		style="fxs"
		if w.keyPressing("lshift"): style="filters"
		trx=fxmenu(style)
		if trx:
			s.remove_all_fx()
			s.setfx(trx);w.say(f"applied {trx} effect");fxx=trx