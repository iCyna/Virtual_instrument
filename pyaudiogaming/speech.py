# -*- coding: utf-8 -*-
# speech wrapper functions
# copyright 2026 belong ihcyna (Labubu)<phucnggo29@gmail.com>.

from .accessible_output2.outputs.auto import *

class Speech:
	def __init__(self):
		self.speech=Auto()
		self.speech_history = []
		self.history_index = -1

	def say(self, text, i=True, split=False):
		"""tts speech"""
		self.speech.silence()
		saying = False
		string = text
		if isinstance(text, str): 
			saying = True
		elif isinstance(text, list) and split:
			for string in text:
				if string is None or string == "": continue
				string = str(string)
				self.speech.output(string, interrupt=i)
				self.speech_history.append(string)
				self.history_index = len(self.speech_history)
			return
		elif isinstance(text, list) and not split:
			string = ""
			for text in text: string += text
			saying = True

		if saying and string is not None and string != "":
			string = str(string)
			self.speech.output(string, interrupt=i)
			self.speech_history.append(string)
			self.history_index = len(self.speech_history)

	def saync(self, string, i=True):
		"""tts speech no log"""
		self.speech.silence()
		self.speech.output(str(string), interrupt=i)

	def get_speech_volume(self): return self.speech.get_volume()
	def set_speech_volume(self, value): return self.speech.set_volume(value)
	def get_speech_pitch(self): return self.speech.get_pitch()
	def set_speech_pitch(self, value): return self.speech.set_pitch(value)
	def get_speech_rate(self): return self.speech.get_rate()
	def set_speech_rate(self, value): return self.speech.set_volume(value)
	def get_speech_voice(self): return self.speech.get_voice()
	def set_speech_voice(self, type): return self.speech.set_voice()

def say(text, i=True, split=False, log=True):
	title="say"
	if not log: title="saync"
	from . import buffer
	if not buffer.hspeechwraper: buffer.hspeechwraper =Speech()
	getattr(buffer.hspeechwrapper, title)(text, i=i, split=split)