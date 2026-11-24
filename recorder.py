import core
from pyaudiogaming.sound_pool import record
from pyaudiogaming import system, utils
from pyaudiogaming.sound_modules import pybassenc


def record_instrument(channel, filename):
	"""Encode the existing instrument channel without taking ownership of it."""
	recorder = record()
	try:
		recorder.encoder = pybassenc.BASS_Encode_Start(
			channel, filename, pybassenc.BASS_ENCODE_PCM | pybassenc.BASS_ENCODE_NOHEAD | 0x80000000,
			pybassenc.ENCODEPROC(), None)
		if not recorder.encoder:
			raise RuntimeError('Could not start instrument recording')
		return recorder
	except Exception:
		recorder.close()
		raise
def mainloop(p, w):
	if w.keyPressed("tab"):
		if not core.recording:
			core.recording =True
			if core.recorder: core.recorder.close();core.recorder = None
			core.recorder = record_instrument(p.handle, system.match("collections", f"{utils.token()}.pcm"))
		else:
			if core.recorder: core.recorder.close();core.recorder=None
			core.recording=False
		w.say("Starting recording" if core.recording else "Stopped recording")
