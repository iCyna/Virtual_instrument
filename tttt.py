from pyaudiogaming.sound_pool import *
output()
s=sound()
s.stream("t.wav", decode=True)
m=mixer()
m.create()
m.add(s)
m.play_looped()
while 1:pass