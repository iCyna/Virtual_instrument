from __future__ import absolute_import
import platform
import sys
from .channel import Channel
from .main import bass_call, bass_call_0, FlagObject
from .external.pybass import *
from pyaudiogaming import utils


class Sample(FlagObject):
	def __init__(self, file, mem=False, length=0, flags=BASS_SAMPLE_SOFTWARE|BASS_SAMPLE_OVER_VOL|BASS_SAMPLE_OVER_POS|BASS_SAMPLE_OVER_DIST, unicode=True, mono=False):
		confile = utils.convert_to_unicode(file)
		if confile == file:
			unicode=False
			file=confile
		self.file = file
		self.setup_flag_mapping()
		flags = flags | self.flags_for(unicode=unicode)
		if mono: flags =flags|BASS_SAMPLE_MONO
		self.handle = bass_call(BASS_SampleLoad, mem, file, 0, length, 128, flags)

	def __del__(self):
		if self.handle: self.free()

	def free(self):
		#bass_call(BASS_SampleFree, self.handle)
		self.handle=None

	def setup_flag_mapping(self):
		super(Sample, self).setup_flag_mapping()
		self.flag_mapping.update({
			'unicode': BASS_UNICODE
		})

# Trong file sample.py

class SampleBasedChannel(Channel):
    def __init__(self, hsample=None):
        """Creates a sample-based channel from a sample handle."""
        if hsample is None or hsample.handle is None:
            raise Exception("Sample handle is invalid before getting channel")

        handle = bass_call(BASS_SampleGetChannel, hsample.handle, False)

        super(SampleBasedChannel, self).__init__(handle)

    def __free__(self):
        pass