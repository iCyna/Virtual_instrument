from pyaudiogaming import window,sound_pool
from pyaudiogaming.sound_lib.effects import tempo

sound_pool.output()
w=window.Window()
w.init(400,300, "test")
w.say("đang khởi động")
#h=sound_pool.sound();h.stream("e:\\data\\client\\sounds\\copter_engine_loop.ogg", mono=True);h.play_looped()
h=sound_pool.sound();h.stream("e:\\data\\client\\sounds\\helecopter_voice.ogg", mono=True);h.play_looped()
x,y,z=0,0,0
sound_volume_step=2
sound_pitch_step=1.6
sound_pan_step=5.4
sound_behind_pitch_decrease=0
sound_behind_volume_decrease=26

while 1:
	w.frameUpdate()
	h.set3d(0,0,0, x,y,z, volume_step=sound_volume_step, pitch_step=sound_pitch_step, pan_step=sound_pan_step, behind_pitch_decrease=sound_behind_pitch_decrease, behind_volume_decrease=sound_behind_volume_decrease)
	if w.keyPressed("space"): w.say("hello")
	if w.keyPressed("left"): x-=1
	if w.keyPressed("right"): x+=1
	if w.keyPressed("down"): y-=1
	if w.keyPressed("up"): y+=1