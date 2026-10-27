# init app
from pyaudiogaming.window import *
from pyaudiogaming.sound_pool import *
w=Window()
w.init(654, 543, "instrument-virtual gaming toolkit")
w.say("welcome you to mobile")
w.wait(5000)
output(ThreeD=True)
s=sound()
s.stream("t.wav", ThreeD=True)
s.set3d(0,10,0,0,0,0)
s.play_looped()
while 1:
	w.frameUpdate()