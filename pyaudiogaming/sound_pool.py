# -*- coding: utf-8 -*-
#sound system multifunctional
# copyright 2026 belong ihcyna (Labubu)<phucnggo29@gmail.com>.
#some of idea from other elsewhere

import time
import math
import threading
import ctypes
from . import system, sound_lib, utils, buffer
from .sound_lib.instrument import SoundFont, MIDIStream, MIDIFileStream
from .sound_lib.recording import *
from .sound_lib.encoder import *
from .sound_fx import *
from .soft import get_openal_audio, initialize_openal_audio

def output(period=10, bbuffer=500, ThreeD=False, sample_rate=44100):
	# initialize output device

	sound_lib.main.BASS_SetConfig(sound_lib.main.BASS_CONFIG_UPDATEPERIOD, period)
	sound_lib.main.BASS_SetConfig(sound_lib.main.BASS_CONFIG_BUFFER, bbuffer)
	o = sound_lib.output.Output()
	buffer.hAudiobuffers["output"] = o
	buffer.hfxbuffers["basic"] = Basic()
	if ThreeD:
		try:
			import phonon
			phonon.phonon_audio_settings.samplingRate = sample_rate
			phonon.initialize_phonon()
			buffer.soft = phonon # Đặt phonon làm 3D engine
		except Exception as e:
			# Fallback về OpenAL nếu tải Phonon thất bại
			if initialize_openal_audio(sample_rate=sample_rate):
				buffer.soft = get_openal_audio()
	return o

def input():
# initialize input device
	i=sound_lib.input.Input()
	buffer.hAudiobuffers["input"] = i
	return i

class SoundBase:
	def __init__(self):
		self.active_fx_handles = {}

	def setPaused(self, p):
		if self.paused == p:
			return
		if not self.playing and p:
			return
		self.paused = p
		if p:
			self.handle.pause()
		else:
			self.handle.play()
		# end pause or unpause
	# end setPaused

	def fadeout(self, fadetime, value=0, type="volume"):
		if self.handle and self.handle.is_playing:
			self.handle.slide_attribute(type, value, fadetime)

	def fadein(self, fadetime, value=100, type="volume"):
			if self.handle and self.handle.is_playing:
				self.handle.slide_attribute(type, float(value)/100, fadetime)

	def setfx(self, fx_key, priority=0):
		"""
		Applies a professional FX or hardware filter preset from the Basic studio engine.
		Automatically safely replaces and manages internal BASS allocation layers.
		"""
		if not self.handle:
			return False
			
		fx_engine = buffer.hfxbuffers.get("basic")
		if not fx_engine:
			return False

		# Determine if the fx_key points to a standard FX or a Hardware Filter Channel
		is_filter = False
		target = fx_engine.fxs.get(fx_key)
		if not target:
			target = fx_engine.filters.get(fx_key)
			is_filter = True
		if not target:
			return False

		# Clean up historical allocated duplication footprints belonging to this specific key
		if fx_key in self.active_fx_handles:
			try:
				self.handle.remove_fx(self.active_fx_handles[fx_key])
			except Exception:
				pass

		# Request native internal wrapper memory mapping configurations
		raw_native_handle = getattr(self.handle, "handle", None)
		if raw_native_handle is None:
			return False

		# Convert to raw primitive C integer cleanly without breaking object properties
		if hasattr(raw_native_handle, "value"):
			c_handle = ctypes.c_uint32(raw_native_handle.value)
		else:
			c_handle = ctypes.c_uint32(int(raw_native_handle))

		# Inject effect into the native active pipeline stream routing channel
		try:
			# --- BẢN SỬA LỖI: Tạo handle FX và lấy thông số từ target ---
			fx_alloc_handle = self.handle.set_fx(target["name"], priority)
			params_payload = target["param"]()
			
			# Gọi API để gán parameter vào stream
			self.handle.set_fx_setparam(fx_alloc_handle, params_payload)
			
			# Register active tracking trace record reference
			self.active_fx_handles[fx_key] = fx_alloc_handle
			return True
		except Exception as ex:
			print(ex)
			return False
	def remove_all_fx(self):
		"""Safely purges the processing stack channel pipeline architecture."""
		if not self.handle:
			return
		for fx_key, fx_handle in list(self.active_fx_handles.items()):
			try:
				self.handle.remove_fx(fx_handle)
			except Exception:
				pass
		self.active_fx_handles.clear()

	def get_data(self, frame_size=512, data_type="raw"):
		handle=None
		if self.dedata: handle=self.dedata
		else: handle=self.handle
		if not handle:
			return None
		if data_type == "raw":
			return handle.get_data(length=frame_size * 2)

		bytes_per_sample = 4 if "32" in data_type else 2
		total_bytes = frame_size * bytes_per_sample
		# BASS_DATA_FLOAT flag (0x40000000)
		flag = 0x40000000 if "32" in data_type else 0
		raw_buffer = handle.get_data(length=total_bytes | flag)
		
		if not raw_buffer: 
			return None

		if data_type == "float32":
			return ctypes.cast(raw_buffer, ctypes.POINTER(ctypes.c_float))[:frame_size]
		elif data_type == "int16":
			return ctypes.cast(raw_buffer, ctypes.POINTER(ctypes.c_int16))
		return raw_buffer

	def get_length(self):
		handle=self.dedata if self.dedata else self.handle
		if not handle: return -1
		return int(handle.length_in_seconds()*1000)

	@property
	def volume(self):
		if not self.handle:
			return False
		return self.handle.get_volume() * 100

	@volume.setter
	def volume(self, value):
		if not self.handle:
			return False
		self.handle.set_volume(float(value) / 100)

	@property
	def pitch(self):
		if not self.handle:
			return False
		return (self.handle.get_frequency() / self.freq) * 100

	@pitch.setter
	def pitch(self, value):
		if not self.handle:
			return False
		self.handle.set_frequency((float(value) / 100) * self.freq)

	@property
	def pan(self):
		if not self.handle:
			return False
		return self.handle.get_pan() * 100

	@pan.setter
	def pan(self, value):
		if not self.handle:
			return False
		self.handle.set_pan(float(value) / 100)

	@property
	def playing(self):
		if self.handle is None:
			return False
		try:
			s = self.handle.is_playing
		except Exception:
			return False
		return s

	@property
	def stopped(self):
		if not self.handle:
			return True
		return self.handle.is_stopped

	@property
	def stalled(self):
		if not self.handle:
			return False
		return self.handle.is_stalled

	def lock(self):
		if self.handle:
			return self.handle.lock()
		return False

	def unlock(self):
		if self.handle:
			return self.handle.unlock()
		return False

	def link(self, other):
		if not self.handle or not other:
			return False		
		if hasattr(other, "handle") and other.handle:
			target = other.handle.handle
		elif hasattr(other, "handle"):
			target = other.handle
		else:
			target = other
		try:
			self.handle.set_link(target)
			return True
		except Exception as e:
			return False

	def unlink(self, other):
		if not self.handle or not other:
			return False
			
		if hasattr(other, "handle") and other.handle:
			target_handle = other.handle.handle
		elif hasattr(other, "handle"):
			target_handle = other.handle
		else:
			target_handle = other			
		try:
			return self.handle.remove_link(target_handle)
		except:
			return False

	@property
	def position(self):
		if not self.handle:
			return 0
		try:
			# Channel bytes translated natively into raw float seconds, up-scaled to integer ms
			return int(self.handle.bytes_to_seconds(handle.get_position()) * 1000)
		except:
			return 0

	@position.setter
	def position(self, ms_value):
		if not self.handle:
			return
		try:
			seconds = float(ms_value) / 1000.0
			byte_target = self,handle.seconds_to_bytes(seconds)
			self.handle.set_position(byte_target)
		except:pass

	def seek(self, ms_value):
		self.position = ms_value

	def set3d(self,  listener_x,  listener_y,  listener_z,  source_x,  source_y,  source_z, rotation=0, head=180, pan_step=2.5,  volume_step=2.5, behind_pitch_decrease=0,  behind_volume_decrease=0, pitch_step=1,  pitch_range=92, pan_range=70, start_pan=0, start_volume=100, start_pitch=100, soft=False):
		self.math3d(listener_x,  listener_y,  listener_z,  source_x,  source_y,  source_z,  pan_step,  volume_step, behind_pitch_decrease,  behind_volume_decrease, pitch_step,  pitch_range, pan_range, start_pan, start_volume, start_pitch, soft=soft)

	def math3d(self,  listener_x,  listener_y,  listener_z,  source_x,  source_y,  source_z,  pan_step,  volume_step, behind_pitch_decrease,  behind_volume_decrease, pitch_step,  pitch_range, pan_range, start_pan, start_volume, start_pitch, soft,):
		delta_x = source_x - listener_x
		final_pan = start_pan + delta_x * pan_step

		delta_y = abs(source_y - listener_y)
		delta_z = abs(source_z - listener_z)
		final_volume = start_volume - (delta_y + delta_z * 0.5) * volume_step
		final_volume = max(min(final_volume, 100), 0)
		final_pitch = start_pitch

		is_behind = source_y < listener_y
		is_below = source_z < listener_z
		is_front = source_y > listener_y
		is_rising = source_z > listener_z

		if is_front and is_rising:
			final_pitch+= (pitch_step+behind_pitch_decrease)
			final_volume+=behind_volume_decrease

		elif is_behind or is_below:
			final_pitch-= (pitch_step+behind_pitch_decrease)
			final_volume-=behind_volume_decrease

		# Clamp pitch
		final_pitch = max(min(final_pitch, start_pitch+1), pitch_range)
		final_pan = max(min(final_pan, pan_range), -pan_range)
		if soft: self.set3dsoft(listener_x, listener_y, listener_z, source_x, source_y, source_z)
		self.volume = final_volume
		self.pitch = final_pitch
		self.pan = final_pan
		#except: pass

	def slide3d(self,  listener_x,  listener_y,  listener_z,  source_x,  source_y,  source_z, fatime, rotation=0, head=180, pan_step=2.5,  volume_step=2.5, behind_pitch_decrease=0,  behind_volume_decrease=0, pitch_step=1,  pitch_range=92, pan_range=75, start_pan=0, start_volume=100, start_pitch=100):
		self.math3dslide(listener_x,  listener_y,  listener_z,  source_x,  source_y,  source_z,  pan_step,  volume_step, behind_pitch_decrease,  behind_volume_decrease, pitch_step,  pitch_range, pan_range, start_pan, start_volume, start_pitch, fatime=fatime)

	def math3dslide(self,  listener_x,  listener_y,  listener_z,  source_x,  source_y,  source_z,  pan_step,  volume_step, behind_pitch_decrease,  behind_volume_decrease, pitch_step,  pitch_range, pan_range, start_pan, start_volume, start_pitch, fatime):
		delta_x = source_x - listener_x
		final_pan = start_pan + delta_x * pan_step  # trái là +, phải là -
		delta_y = abs(source_y - listener_y)
		delta_z = abs(source_z - listener_z)
		final_volume = start_volume - (delta_y + delta_z * 0.5) * volume_step
		final_volume = max(min(final_volume, 100), 0)
		final_pitch = start_pitch

		is_behind = source_y < listener_y
		is_below = source_z < listener_z
		is_front = source_y > listener_y
		is_rising = source_z > listener_z

		if is_front and is_rising:
			final_pitch+= (pitch_step+behind_pitch_decrease)
			final_volume+=behind_volume_decrease

		elif is_behind or is_below:
			final_pitch-= (pitch_step+behind_pitch_decrease)
			final_volume-=behind_volume_decrease

		# Clamp pitch
		final_pitch = max(min(final_pitch, start_pitch+1), pitch_range)
		final_pan = max(min(final_pan, pan_range), -pan_range)
		self.handle.slide_attribute("volume", float(final_volume) / 100, fatime)
		self.handle.slide_attribute("pan", float(final_pan) / 100, fatime)
		self.handle.slide_attribute("frequency", (float(final_pitch) / 100) * self.freq, fatime)
		#except: pass

class record(SoundBase):
	def __init__(self):
		super().__init__()
		self.sound_token = utils.token(max=25)
		self.encoder_token=utils.token(max=25)
		buffer.hrecordthreadbuffers[self.sound_token] = self
		self.handle = None
		self.encoder = None
		self._paused = False
		self._sample_data = bytearray()
		self._mode = "w"
		self._internal_proc = None # Save callback reference to avoid memory cleanup (GC)

	def stream(self, filename="", frequency=44100, channels=2, mode="w", callback=None):
		"""
		Start record with 3 modes
		- "w" (write): Record directly to file (use filename).
		- "c" (callback): Push raw audio data into the callback function.
		- "s" (sample): Cast raw audio data in memory, retrieve with get_sample_data().
		"""
		self.close()
		self._mode = mode
		self._sample_data = bytearray()
		record_proc = None

		if mode in ("c", "s"):
			def _internal_callback(handle, buffer_ptr, length, user):
				if length > 0:
					# Get raw data in bytes from C pointer
					data = ctypes.string_at(buffer_ptr, length)
					if self._mode == "s":
						self._sample_data.extend(data)
					elif self._mode == "c" and callback:
						# If the user's callback returns False, stop recording
						if callback(data) is False:
							return False
				return True
			self._internal_proc = _internal_callback
			record_proc = self._internal_proc

		# InitRecording
		if record_proc:
			self.handle = Recording(frequency=frequency, channels=channels, proc=record_proc)
		else:
			self.handle = Recording(frequency=frequency, channels=channels)
		self.handle.play()

		# Use Encoder if 'w' file writing mode
		if filename and mode =="w":
			self.encoder = self.drawn(self.handle, filename)
		self._paused = False

	def get_sample(self):
		"""Returns the captured audio data (for mode 's')"""
		return bytes(self._sample_data)

	def clear_sample(self):
		"""Clear data buffer"""
		self._sample_data = bytearray()

	def drawn(self, h, filename):
		# drawn and record a hchannel to file
		e=Encoder(h, system.match(system.embedded_data_path(), "..", filename))
		self.encoder_token=utils.token(max=36)
		buffer.hrecordthreadbuffers[self.encoder_token] = e
		return e

	def stop(self):
		if self.encoder:
			self.encoder.stop()
			self.encoder = None
		if self.handle:
			self.handle.stop()
			self.handle.free()
			self.handle = None

	def close(self):
		try:
			self.stop()
			if self.sound_token in buffer.hrecordthreadbuffers:
				del buffer.hrecordthreadbuffers[self.sound_token]
			if self.encoder_token in buffer.hrecordthreadbuffers:
				del buffer.hrecordthreadbuffers[self.encoder_token]
		except:pass

class musical(SoundBase):
	def __init__(self):
		super().__init__()
		self.sound_token = utils.token(max=25)
		buffer.hSound_poolbuffers[self.sound_token] = self
		self.handle = None
		self.freq = 44100
		self.paused = False
		self.boolfadein = False
		self.fonts_storage = []

	def load_font(self, font_path, flags=0):
		font_path = system.match(system.embedded_data_path(), "..", font_path)
		sf = SoundFont(font_path, flags=flags)
		self.fonts_storage.append(sf) 
		return sf

	def create_empty_stream(self, channels=16):
		if self.handle:
			self.close()
		self.handle = MIDIStream(channels=channels, decode=False)
		self.freq = int(self.handle.get_frequency())

	def stream(self, filename, mono=False):
		if self.handle:
			self.close()
		self.handle = MIDIFileStream(file=filename, mono=mono, decode=False)
		self.freq = int(handle.get_frequency())
		
		if self.handle: 
			return int(self.handle.bytes_to_seconds(handle.get_length()) * 1000)

	def set_fonts(self, fonts_config):
		if not self.handle or not hasattr(self.handle, 'set_fonts'):
			return False
		if isinstance(fonts_config, SoundFont):
			return self.handle.set_fonts([(fonts_config.handle, -1, 0)])
		return self.handle.set_fonts(fonts_config)

	def send_event(self, chan, event, param):
		if self.handle and hasattr(self.handle, 'send_event'):
			return self.handle.send_event(chan, event, param)
		return False

	def load_samples(self):
		if self.handle and hasattr(self.handle, 'load_samples'):
			return self.handle.load_samples(0, 0)
		return False

	def setPaused(self, p):
		if self.paused == p:
			return
		if not self.playing and p:
			return
		self.paused = p
		if p:
			self.handle.pause()
		else:
			self.handle.play()

	def play_wait(self):
		self.handle.looping = False
		if self.boolfadein: 
			self.handle.set_volume(0)
		self.handle.play_blocking()

	def play_looped(self):
		if self.boolfadein: 
			self.handle.set_volume(0)
		self.handle.looping = True
		self.handle.play()

	def fadeout(self, fadetime, value=0, type="volume"):
		if self.handle and self.handle.is_playing:
			self.handle.slide_attribute(type, value, fadetime)

	def fadein(self, fadetime, value=100, type="volume"):
		if self.handle and self.handle.is_playing:
			self.handle.slide_attribute(type, float(value) / 100, fadetime)

	def setfx(self, type, priority=0):
		self.handle.handle = ctypes.c_uint32(self.handle.handle)
		b = buffer.hfxbuffers["basic"].fxs
		fx_handle = self.handle.set_fx(b[type]["name"], priority=priority)
		params = b[type]["param"]()
		self.handle.set_fx_setparam(fx_handle, params)

	def get_data(self, frame_size=512, data_type="raw"):
		if not self.handle:
			return None
		if data_type == "raw":
			return self.handle.get_data(length=frame_size * 2)

		bytes_per_sample = 4 if "32" in data_type else 2
		total_bytes = frame_size * bytes_per_sample
		flag = 0x40000000 if "32" in data_type else 0
		raw_buffer = self.handle.get_data(length=total_bytes | flag)
		
		if not raw_buffer: 
			return None

		if data_type == "float32":
			return ctypes.cast(raw_buffer, ctypes.POINTER(ctypes.c_float))[:frame_size]
		elif data_type == "int16":
			return ctypes.cast(raw_buffer, ctypes.POINTER(ctypes.c_int16))
		return raw_buffer

	def get_length(self):
		if not self.handle: 
			return -1
		return int(self.handle.length_in_seconds() * 1000)

	@property
	def volume(self):
		if not self.handle:
			return False
		return self.handle.get_volume() * 100

	@volume.setter
	def volume(self, value):
		if not self.handle:
			return False
		self.handle.set_volume(float(value) / 100)

	@property
	def pitch(self):
		if not self.handle:
			return False
		return (self.handle.get_frequency() / self.freq) * 100

	@pitch.setter
	def pitch(self, value):
		if not self.handle:
			return False
		self.handle.set_frequency((float(value) / 100) * self.freq)

	@property
	def pan(self):
		if not self.handle:
			return False
		return self.handle.get_pan() * 100

	@pan.setter
	def pan(self, value):
		if not self.handle:
			return False
		self.handle.set_pan(float(value) / 100)

	@property
	def playing(self):
		if self.handle is None:
			return False
		try:
			s = self.handle.is_playing
		except Exception:
			return False
		return s

	def stop(self):
		if self.handle and self.handle.is_playing:
			self.handle.stop()
			self.handle.set_position(0)

	def play(self):
		if self.handle:
			self.handle.play()

	def close(self):
		try:
			if self.handle and self.playing:
				self.handle.stop()
			if self.handle: 
				self.handle.free()
				self.handle = None

			# Free all SoundFonts associated with this music stream
			for sf in self.fonts_storage:
				sf.free()
			self.fonts_storage = []

			if self.sound_token in buffer.hmidibuffers:
				del buffer.hmidibuffers[self.sound_token]
		except Exception: 
			pass

class sound(SoundBase):
	def __init__(self):
		super().__init__()
		self.sound_token = utils.token(max=25)
		buffer.hSound_poolbuffers[self.sound_token] = self
		self.handle = None
		self.dedata=None
		self._3d = 	None
		self.freq = 44100
		self.paused = False
		self.boolfadein = False

	def stream(self,filename, draw=False, mono=False, ThreeD=False, decode=False, autofree=False):
		if self.handle:
			self.close()
		if ThreeD: mono=True
		if draw:
			handle = sound_lib.stream.PushStream()
		else:
			if filename in buffer.hstreambuffers:
				handle = sound_lib.stream.FileStream(mem=True, file=buffer.hstreambuffers[filename]["buffer"], length=buffer.hstreambuffers[filename]["len"], mono=mono, decode=decode, autofree=autofree)
			else:
				if not utils.is_url(filename):
					handle = sound_lib.stream.FileStream(file=filename, mono=mono, decode=decode, autofree=autofree)
				else: handle = sound_lib.stream.URLStream(url=filename, mono=mono, decode=decode, autofree=autofree)
		if ThreeD: self.dedata=handle
		else: self.handle=handle
		self.freq = int(handle.get_frequency())
		try:
			if handle: return int(handle.bytes_to_seconds(handle.get_length())*1000)
		except: return 0

	def push(self, data):
		try:
			if self.handle is None or not self.handle: return
			self.handle.push(data)
		except:pass

	def load(self, filename="", mono=False):
		if self.handle:
			self.close()
		if isinstance(filename, str):pass
		elif isinstance(filename, type(filename)):
			self.keep = self.handle = sound_lib.sample.SampleBasedChannel(filename)
			self.freq = self.handle.get_frequency();return
		if filename in buffer.hsamplebuffers:
			self.handle = sound_lib.sample.SampleBasedChannel(buffer.hsamplebuffers[filename]["buffer"])
		else:self.handle = sound_lib.sample.SampleBasedChannel(sound_lib.sample.Sample(filename, mono=mono))
		self.freq = self.handle.get_frequency()

	def vsample(self, sample=None):
		if self.handle:
			self.close()
		self.handle = sound_lib.sample.SampleBasedChannel(sample)
		self.freq = self.handle.get_frequency()

	def sample(self, filename):
		return sound_lib.sample.Sample(filename)

	def play_wait(self):
		self.handle.looping = False
		if self.boolfadein: self.handle.set_volume(0)
		self.handle.play_blocking()

	def play_looped(self):
		if self.boolfadein: self.handle.set_volume(0)
		if self.play3d(loop=True): return
		else:
			self.handle.looping = True
			self.handle.play()

	def set3dsoft(self, *coords, **kwargs):
		self._3d = coords

	def stop(self):
		if self.handle and self.handle.is_playing:
			self.handle.stop()
			self.handle.set_position(0)
		if self.dedata:
			self.dedata.set_position(0)

	def close(self):
		try:
			if self.handle and self.playing:
				self.handle.stop()
			if self.sound_token and hasattr(buffer, 'soft') and buffer.soft:
				if hasattr(buffer.soft, 'free_token'):
					buffer.soft.free_token(self.sound_token)
			if self.dedata: 
				self.dedata.free()
				self.dedata = None
			if self.handle: 
				self.handle.free()
				self.handle = None
			if self.sound_token in buffer.hSound_poolbuffers:
				del buffer.hSound_poolbuffers[self.sound_token]
		except Exception as e: 
			pass

	def _callback(self, handle, buffer_ptr, length, user):
		if length <= 0: return 0
		
		is_phonon = hasattr(buffer, 'soft') and buffer.soft and hasattr(buffer.soft, 'phonon_dsp')
		
		if is_phonon:
			frames = length // 8
			if frames <= 0: return 0
			
			source_handle = self.dedata if self.dedata else self.handle
			if not source_handle: return -2147483648
			raw_pcm = source_handle.get_data(length=(frames * 4) | 0x40000000)
		else:
			frames = length // 4
			if frames <= 0: return 0
			raw_pcm = self.get_data(frame_size=frames, data_type="raw")

		if not raw_pcm:
			if hasattr(buffer, 'soft') and buffer.soft and hasattr(buffer.soft, 'free_token'):
				buffer.soft.free_token(self.sound_token)
			return -2147483648 

		if not self._3d: return 0
		lx, ly, lz, sx, sy, sz = self._3d
		
		if is_phonon:
			# Phonon tính vị trí nguồn âm tương đối so với Listener
			rel_x = sx - lx
			rel_y = sy - ly
			rel_z = sz - lz
			audio_data = buffer.soft.phonon_dsp(raw_pcm, rel_x, rel_y, rel_z, 2.5, 1)
		else:
			audio_data = buffer.soft.process_sound(self.sound_token, raw_pcm, frames, self.freq, lx, ly, lz, sx, sy, sz)
			
		if audio_data:
			copy_length = min(length, len(audio_data))
			if copy_length > 0:
				ctypes.memmove(buffer_ptr, audio_data, copy_length)
				return copy_length
			
		return 0

	def play3d(self, loop=False):
		if self._3d:
			if not self.handle:
				from .sound_lib.stream import Stream as BaseStream
				is_phonon = hasattr(buffer, 'soft') and buffer.soft and hasattr(buffer.soft, 'phonon_dsp')
				flags = 256 if is_phonon else 0
				self.handle = BaseStream(freq=self.freq, chans=2, flags=flags, proc=self._callback)
			self.handle.looping = loop
			self.handle.play()
			return True
		return False
	def play(self):
		if self.play3d(): return
		else:
			self.handle.play()

def playsingle(filename, volume=100, pitch=100, pan=0, mono=False):
	# play sound o more easily
	if not filename: return
	s = sound()
	s.load(filename, mono=mono)
	s.volume = volume
	s.pitch = pitch
	s.pan=pan
	s.play()
	return s