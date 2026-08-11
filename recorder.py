import core
from pyaudiogaming.sound_pool import record
from pyaudiogaming import system, utils
def mainloop(p, w):
	if w.keyPressed("tab"):
		if not core.recording:
			core.recording =True
			if core.recorder: core.recorder.close();core.recorder = None
			core.recorder = record()
			core.recorder.drawn(p.handle, system.match("collections", f"{utils.token()}.pcm"))
		else:
			if core.recorder: core.recorder.close();core.recorder=None
			core.recording=False
		w.say("Starting recording" if core.recording else "Stopped recording")