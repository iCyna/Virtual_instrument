from __future__ import absolute_import
import platform
import sys
import ctypes
from .channel import Channel
from .main import bass_call, bass_call_0
from .external.pybass import *
from .external.pybassmidi import * # Import các hàm và hằng số từ file pybassmidi của bạn

try:
	convert_to_unicode = unicode
except NameError:
	convert_to_unicode = str


class BaseMIDIStream(Channel):
	"""Lớp cơ sở cho các luồng MIDI, kế thừa từ Channel để có đầy đủ các tính năng điều khiển âm thanh."""

	def free(self):
		# Sử dụng BASS_StreamFree tương tự như BaseStream vì luồng MIDI thực chất vẫn là một HSTREAM
		return bass_call(BASS_StreamFree, self.handle)

	def setup_flag_mapping(self):
		super(BaseMIDIStream, self).setup_flag_mapping()
		# Cập nhật thêm các flag đặc trưng nếu cần (ví dụ: unicode)
		self.flag_mapping.update({
			'unicode': BASS_UNICODE
		})

	def set_fonts(self, fonts_list, global_font=False):
		"""
		Thiết lập Soundfonts cho luồng MIDI hoặc cho toàn hệ thống.
		Nếu global_font=True, Font sẽ được nạp cấu hình toàn cục để có thể preload samples.
		"""
		count = len(fonts_list)
		font_array = (BASS_MIDI_FONT * count)()
		for i, font_data in enumerate(fonts_list):
			if isinstance(font_data, dict):
				font_array[i].font = font_data.get('font')
				font_array[i].preset = font_data.get('preset', -1)
				font_array[i].bank = font_data.get('bank', 0)
			else:
				font_array[i].font = font_data[0]
				font_array[i].preset = font_data[1] if len(font_data) > 1 else -1
				font_array[i].bank = font_data[2] if len(font_data) > 2 else 0
		
		if global_font:
			# Nạp Font hệ thống toàn cục để mở khóa tính năng StreamLoadSamples
			return bass_call(BASS_MIDI_FontSetFonts, font_array, count)
		else:
			return bass_call(BASS_MIDI_StreamSetFonts, self.handle, font_array, count)

	def load_samples(self, preset=0, bank=0):
		return bass_call(BASS_MIDI_StreamLoadSamples, 0, preset, bank)

	def send_event(self, chan, event, param):
		"""Gửi một sự kiện MIDI thời gian thực (ví dụ: Note On, Note Off, Change Program...)."""
		return bass_call(BASS_MIDI_StreamEvent, self.handle, chan, event, param)


class MIDIStream(BaseMIDIStream):
	"""Tạo một luồng MIDI trống để chơi các sự kiện thời gian thực (Real-time MIDI events)."""

	def __init__(self, channels=16, flags=0, freq=44100, three_d=False, autofree=False, decode=False):
		self.setup_flag_mapping()
		# Kết hợp các flags chuẩn từ lớp Channel
		flags = flags | self.flags_for(three_d=three_d, autofree=autofree, decode=decode)
		
		# Gọi hàm khởi tạo luồng MIDI từ pybassmidi
		handle = bass_call(BASS_MIDI_StreamCreate, channels, flags, freq)
		super(MIDIStream, self).__init__(handle)


class MIDIFileStream(BaseMIDIStream):
	"""Tạo một luồng phát nhạc từ file MIDI (.mid)."""

	def __init__(self, mem=False, file=None, offset=0, length=0, flags=0, freq=44100, three_d=False, autofree=False, decode=False, unicode=True):
		if platform.system() == 'Darwin':
			unicode = False
			if file and isinstance(file, str):
				file = file.encode(sys.getfilesystemencoding())
		
		self.setup_flag_mapping()
		# Bổ sung thêm các flag cấu hình riêng cho MIDI nếu người dùng truyền qua kwargs (ví dụ: mono)
		flags = flags | self.flags_for(three_d=three_d, autofree=autofree, decode=decode, unicode=unicode)
		
		if unicode and isinstance(file, str):
			file = convert_to_unicode(file)
		self.file = file

		# Khởi tạo stream từ file sử dụng hàm của BASSMIDI
		handle = bass_call(BASS_MIDI_StreamCreateFile, mem, file, offset, length, flags, freq)
		super(MIDIFileStream, self).__init__(handle)


class SoundFont(object):
	def __init__(self, file_path, flags=0x20000):
		if isinstance(file_path, bytes):
			file_path = file_path.decode(sys.getfilesystemencoding())
		elif not isinstance(file_path, str):
			file_path = str(file_path)

		self.file_path = file_path
		BASS_UNICODE = 0x80000000
		flags =flags| BASS_UNICODE
		self.file_path = ctypes.c_wchar_p(file_path)
		self.handle = bass_call(BASS_MIDI_FontInit, self.file_path, flags)

	def load_samples(self, preset=-1, bank=-1):
		if hasattr(self, 'handle') and self.handle:
			return bass_call(BASS_MIDI_StreamLoadSamples, self.handle, preset, bank)
		return False

	def free(self):
		if hasattr(self, 'handle') and self.handle:
			res = bass_call(BASS_MIDI_FontFree, self.handle)
			self.handle = None
			return res
		return False

	def set_volume(self, volume):
		return bass_call(BASS_MIDI_FontSetVolume, self.handle, float(volume))

	def get_volume(self):
		return bass_call(BASS_MIDI_FontGetVolume, self.handle)

	def __del__(self):
		try:
			self.free()
		except:
			pass