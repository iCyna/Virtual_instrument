# init app
from pyaudiogaming.window import *
from pyaudiogaming.sound_pool import output
w=Window()
w.init(654, 543, "instrument-virtual gaming toolkit")
w.say("welcome you to mobile")
w.wait(5000)
output()
while 1:
	w.frameUpdate()