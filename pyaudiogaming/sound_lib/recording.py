from __future__ import absolute_import
from .channel import Channel
from .external.pybass import *
from ctypes import string_at
from .main import bass_call, bass_call_0

class Recording(Channel):

	def __init__(self, frequency=44100, channels=2, flags=0, proc=None, user=None):
		if not proc:
			proc = lambda handle, buffer, length, user: True
		self.callback = RECORDPROC(proc)
		self._frequency = frequency
		self._channels = channels
		self._flags = flags
		self.handle = bass_call(BASS_RecordStart, frequency, channels, flags, self.callback, user)
		super(Recording, self).__init__(self.handle)

	def free(self):
		return bass_call(BASS_ChannelStop, self.handle)
