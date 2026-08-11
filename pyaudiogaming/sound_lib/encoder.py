import ctypes
from .external import pybass, pybassmix, pybassenc
from .main import bass_call, bass_call_0, FlagObject
from pyaudiogaming import utils
from pyaudiogaming.utils import convert_to_unicode

class Encoder(FlagObject):

	def setup_flag_mapping(self):
		self.flag_mapping = {
			'pcm': pybassenc.BASS_ENCODE_PCM,
			'no_header': pybassenc.BASS_ENCODE_NOHEAD,
			'rf64': pybassenc.BASS_ENCODE_RF64,
			'big_endian': pybassenc.BASS_ENCODE_BIGEND,
			'fp_8bit': pybassenc.BASS_ENCODE_FP_8BIT,
			'fp_16bit': pybassenc.BASS_ENCODE_FP_16BIT,
			'fp_24bit': pybassenc.BASS_ENCODE_FP_24BIT,
			'fp_32bit': pybassenc.BASS_ENCODE_FP_32BIT,
			'queue': pybassenc.BASS_ENCODE_QUEUE,
			'limit': pybassenc.BASS_ENCODE_LIMIT,
			'no_limit': pybassenc.BASS_ENCODE_CAST_NOLIMIT,
			'pause': pybassenc.BASS_ENCODE_PAUSE,
			'autofree': pybassenc.BASS_ENCODE_AUTOFREE,
			'unicode': pybass.BASS_UNICODE,
		}

	def __init__(self, source, filename, pcm=True, no_header=False, rf64=False, big_endian=False, fp_8bit=False, fp_16bit=False, fp_24bit=False, fp_32bit=False, queue=True, limit=False, no_limit=False, pause=False, autofree=False, callback=None, user=None, unicode=True, flags=0):
		confile = utils.convert_to_unicode(filename)
		if confile == filename:
			unicode=False
			filename=confile

		self.setup_flag_mapping()
		flags = self.flags_for(pcm=pcm, no_header=no_header, rf64=rf64, big_endian=big_endian, 
							   fp_8bit=fp_8bit, fp_16bit=fp_16bit, fp_24bit=fp_24bit, 
							   fp_32bit=fp_32bit, queue=queue, limit=limit, 
							   no_limit=no_limit, pause=pause, autofree=autofree, unicode=unicode)
		
		self.source = source
		source_handle = source.handle if hasattr(source, 'handle') else source
		if callback is None:
			def empty_callback(handle, channel, buffer, length, user):
				pass
			self.callback = pybassenc.ENCODEPROC(empty_callback)
		else:
			self.callback = pybassenc.ENCODEPROC(callback)
		print(filename)
		self.handle = bass_call(pybassenc.BASS_Encode_Start, source_handle, filename, flags, self.callback, None)

	@property
	def paused(self):
		return bass_call_0(pybassenc.BASS_Encode_IsActive, self.handle) == pybass.BASS_ACTIVE_PAUSED

	@paused.setter
	def paused(self, paused):
		return bass_call(pybassenc.BASS_Encode_SetPaused, self.handle, paused)
	
	def is_stopped(self):
		return bass_call(pybassenc.BASS_Encode_IsActive, self.handle) == pybass.BASS_ACTIVE_STOPPED

	def stop(self):
		return bass_call(pybassenc.BASS_Encode_Stop, self.handle)

class BroadcastEncoder(Encoder):

	def __init__(self, source, server, password, content, name=None, url=None, genre=None, description=None, headers=None, bitrate=0, public=False):
		contents = {
			'mp3': pybassenc.BASS_ENCODE_TYPE_MP3,
			'ogg': pybassenc.BASS_ENCODE_TYPE_OGG,
			'aac': pybassenc.BASS_ENCODE_TYPE_AAC
		}
		if content in contents:
			content = contents[content]
		
		# Sửa lỗi logic: Gắn trực tiếp vào channel nguồn thay vì encoder nguồn
		self.source = source
		source_handle = source.handle if hasattr(source, 'handle') else source
		self.server = server.encode('utf-8') if isinstance(server, str) else server
		self.password = password.encode('utf-8') if isinstance(password, str) else password
		
		# Khởi tạo encoder cơ bản trước (sử dụng cờ giới hạn tốc độ thời gian thực cho livestream)
		super(BroadcastEncoder, self).__init__(source, None, limit=True, pause=False, pcm=True)
		
		self.status = bass_call(pybassenc.BASS_Encode_CastInit, self.handle, self.server, self.password, content.encode('utf-8') if isinstance(content, str) else content, name.encode('utf-8') if name else None, url.encode('utf-8') if url else None, genre.encode('utf-8') if genre else None, description.encode('utf-8') if description else None, headers.encode('utf-8') if headers else None, bitrate, public)

	def set_title(self, title=None, url=None):
		return bass_call(pybassenc.BASS_Encode_CastSetTitle, self.handle, title.encode('utf-8') if title else None, url.encode('utf-8') if url else None)

	def get_stats(self, type, password=None):
		types = {
			'shoutcast': pybassenc.BASS_ENCODE_STATS_SHOUT,
			'icecast': pybassenc.BASS_ENCODE_STATS_ICE,
			'icecast_server': pybassenc.BASS_ENCODE_STATS_ICESERV,
		}
		if type in types:
			type = types[type]
		if password is None:
			password = self.password  
		return bass_call(pybassenc.BASS_Encode_CastGetStats, self.handle, type, password)


class ServerEncoder(Encoder):
	"""Bổ sung tính năng tạo Local Streaming Server từ luồng Audio"""
	def __init__(self, source, port="8000", buffer_len=5000, burst=2000, no_http=False, callback=None, user=None):
		super(ServerEncoder, self).__init__(source, None, pause=False, pcm=True)
		flags = 1 if no_http else 0
		if callback is None:
			callback = lambda *a: True
		self.client_callback = pybassenc.ENCODECLIENTPROC(callback)
		bass_call(pybassenc.BASS_Encode_ServerInit, self.handle, port.encode('utf-8'), buffer_len, burst, flags, self.client_callback, user)