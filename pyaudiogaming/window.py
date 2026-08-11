# -*- coding: utf-8 -*-
#Basic window, speech, functions.
#Idea from Yukio Nozawa and continue by ihcyna(Labubu)

import pygame
from . import buffer
from .sound_lib import sample
from copy import copy
from .key import *
from .timer import *
from . import sound_pool
from . import inputBox
from . import system  # Import system để check platform
from . import speech
class Window(object):
	def __new__(cls, *args, **kwargs):
		return object.__new__(cls)

	def __init__(self, platform=None):
		# check platform
		if platform is None:
			from . import system
			os_name = system.get_platform()["os"]
			platform = "mobile" if os_name in ("android", "ios") else "pc"
		buffer.platform = platform
		TargetClass = WindowPC if platform == "pc" else WindowMobile
		if TargetClass not in self.__class__.__mro__:
			self.__class__ = type(self.__class__.__name__, (self.__class__, TargetClass), {})
		TargetClass.__init__(self)

# base class
class WindowBase:
	import ctypes
	def __init__(self):
		self.speech = speech.Speech()
		pygame.display.init()
		self.clock = pygame.time.Clock()
		self.fp = 60
		self.frame_callback = None
		self.exit_callback = None

	def wait(self, msec):
		t = Timer()
		while t.elapsed < msec:
			self.frameUpdate()

	def say(self, text, i=True, split=False):
		self.speech.say(text, i=i, split=split)

	def saync(self,text):
		self.speech.saync(text)

	def input(self, title, message, password=False, dir=False, file=False):
		"""Shows a text input dialog and returns what was input by the user."""
		ret = inputBox.kbt(None, title, password, password=password, dir_dialog=dir, file_dialog=file)
		return ret

	def message(self, m, callback=None, open=None, move=None, close=None):
		from . import vb
		vb.message(m, callback, open, move, close)

	def message_gui(self, title, message, type=inputBox.INFO):
		i = inputBox.dialogMessage(title, message, type)
		return i

	def load_sound(self, name, h="hstream"):
		with open(name, "rb") as f:
			data = f.read()
			if h == "hstream":
				buffers = self.ctypes.create_string_buffer(data)
				ptr = self.ctypes.cast(buffers, self.ctypes.c_void_p)
				buffer.hstreambuffers[name] = {"buffer": ptr, "len": len(data)}
			elif h == "hsample":
				buffer.hsamplebuffers[name] = {"buffer": sample.Sample(data), "len": len(data)}

	def sound_cast(self, name, data, h="hstream"):
		if h == "hstream":
			buffers = self.ctypes.create_string_buffer(data)
			ptr = self.ctypes.cast(buffers, self.ctypes.c_void_p)
			buffer.hstreambuffers[name] = {"buffer": ptr, "len": len(data)}
		elif h == "hsample":
			buffer.hsamplebuffers[name] = {"buffer": sample.Sample(data, mem=True, length=len(data)), "len": len(data)}

	def beep(self, frequency, duration):
		# Only call windll if you are on a PC (Windows), mobile will handle it differently or ignore it to avoid crashes
		if buffer.platform == "pc":
			self.ctypes.windll.kernel32.Beep(frequency, duration)

	def beep_progress_bar(self, progress, duration=120):
		frequency = 200 + int((progress / 100) * (1500 - 200))
		self.beep(frequency, duration)

# class for pc (Windows, macos, linux)
class WindowPC(WindowBase):
	def __init__(self, platform=None):
		import wx
		super().__init__()
		self.platform = "pc"
		self.appwx = wx.App()
		self.keycode_timer = {}
		print(self.speech)

	def init(self, x, y, ttl, vv=0, show_vv=False, author=""):
		self.keys = [0]*255
		self.previousKeys = [0]*255
		self.screen = pygame.display.set_mode((640, 480), pygame.NOFRAME)
		pygame.display.set_caption(ttl if not show_vv else ttl+" "+vv)
		buffer.name_window = ttl
		buffer.version = vv
		buffer.author = author
		buffer.frame = self
		return True

	def frameUpdate(self):
		self.clock.tick(self.fp)
		pygame.event.pump()
		self.previousKeys = copy(self.keys)
		self.keys = pygame.key.get_pressed()
		
		if self.frame_callback: self.frame_callback()
		
		if self.keyPressed(k.lcontrol.value) or self.keyPressed(k.rcontrol.value): self.speech.speech.silence()
		if self.keyPressed(k.f4.value) and (self.keyPressing(k.lalt.value) or self.keyPressing(k.ralt.value)):
			if self.exit_callback: self.exit_callback()
		try:
			if self.keyPressed(k.left_bkt.value):  # Previous history item
				if self.speech.history_index > 0:
					if self.keyPressing(k.lshift.value) or self.keyPressing(k.right.value):
						self.speech.history_index = 0
						self.saync(self.speech.speech_history[self.speech.history_index]); return
					self.speech.history_index -= 1
					self.saync(self.speech.speech_history[self.speech.history_index])
			elif self.keyPressed(k.right_bkt.value):  # Next history item
				if self.keyPressing(k.lshift.value) or self.keyPressing(k.right.value):
					self.speech.history_index = len(self.speech.speech_history)-1
					self.saync(self.speech.speech_history[self.speech.history_index]); return
				if self.speech.history_index < len(self.speech.speech_history) - 1:
					self.speech.history_index += 1
					self.saync(self.speech.speech_history[self.speech.history_index])
		except IndexError: pass

	def keyPressed(self, key):
		key = key if not isinstance(key, str) else getattr(k, key).value
		return self.keys[key] and not self.previousKeys[key]

	def keyPressing(self, key, t=0):
		key = key if not isinstance(key, str) else getattr(k, key).value
		if key not in self.keycode_timer:
			self.keycode_timer[key] = Timer()
		if not self.keys[key]:
			return self.keys[key] and not self.previousKeys[key]
		elif self.keys[key]:
			if self.keycode_timer[key].elapsed >= t:
				self.keycode_timer[key].restart()
				return self.keys[key]

	# Block mobile swipe functions so that the code does not report an error if called incorrectly
	def keySlide(self, direction): return False
	def keySliding(self, direction): return False

# class for mobile (androix, apple)
class WindowMobile(WindowBase):
	def __init__(self, platform=None):
		super().__init__()
		self.platform = "mobile"
		# --- QUẢN LÝ ĐA ĐIỂM (MULTI-TOUCH) CỰC GỌN ---
		# dict chứa các ngón tay đang chạm trên màn hình (ID ngón tay: {start_x, start_y, current_x, current_y})
		self.touches = {} 
		
		# List lưu các hướng đang vuốt (sliding) và vừa vuốt xong (slide) trong frame hiện tại
		self.active_slidings = []
		self.completed_slides = []

	def init(self, x, y, ttl, vv=0, show_vv=False, author=""):
		# ANDROID VẪN PHẢI TẠO CỬA SỔ BỀ MẶT BẰNG PYGAME (SDL2 Window)
		self.screen = pygame.display.set_mode((640, 480), pygame.NOFRAME)
		pygame.display.set_caption(ttl if not show_vv else ttl+" "+vv)
		buffer.name_window = ttl
		buffer.version = vv
		buffer.author = author
		buffer.frame = self
		return True

	def frameUpdate(self):
		self.clock.tick(self.fp)
		
		# Xóa lịch sử vuốt của frame trước
		self.completed_slides.clear()
		self.active_slidings.clear()

		# Xử lý Event của Pygame
		for event in pygame.event.get():
			if event.type == pygame.QUIT:
				if self.exit_callback: self.exit_callback()

			# 1. NGÓN TAY CHẠM XUỐNG
			elif event.type == pygame.FINGERDOWN:
				# event.finger_id phân biệt ngón 1, ngón 2, ngón 3...
				self.touches[event.finger_id] = {
					"start": (event.x, event.y),
					"current": (event.x, event.y)
				}

			# 2. NGÓN TAY ĐANG DI CHUYỂN (Kéo lê / Sliding)
			elif event.type == pygame.FINGERMOTION:
				if event.finger_id in self.touches:
					t = self.touches[event.finger_id]
					t["current"] = (event.x, event.y)
					
					# Tính hướng đang vuốt (so với lúc chạm xuống)
					dx = t["current"][0] - t["start"][0]
					dy = t["current"][1] - t["start"][1]
					
					# Ngưỡng 0.05 (5% màn hình) để chống rung tay nhầm
					if abs(dx) > abs(dy) and abs(dx) > 0.05:
						self.active_slidings.append("right" if dx > 0 else "left")
					elif abs(dy) > abs(dx) and abs(dy) > 0.05:
						self.active_slidings.append("down" if dy > 0 else "up")

			# 3. NGÓN TAY NHẤC LÊN (Vuốt xong / Slide)
			elif event.type == pygame.FINGERUP:
				if event.finger_id in self.touches:
					t = self.touches[event.finger_id]
					dx = event.x - t["start"][0]
					dy = event.y - t["start"][1]
					
					# Lưu lại hướng vừa vuốt dứt khoát
					if abs(dx) > abs(dy) and abs(dx) > 0.05:
						self.completed_slides.append("right" if dx > 0 else "left")
					elif abs(dy) > abs(dx) and abs(dy) > 0.05:
						self.completed_slides.append("down" if dy > 0 else "up")
					
					# Xóa ngón tay khỏi danh sách quản lý
					del self.touches[event.finger_id]

		if self.frame_callback: self.frame_callback()

	# --- CÁC HÀM GỌI CHO MENU ---
	def keySlide(self, direction):
		"""Trả về True nếu CÓ ÍT NHẤT MỘT ngón tay vừa vuốt dứt khoát về hướng này"""
		return direction.lower() in self.completed_slides

	def keySliding(self, direction):
		"""Trả về True nếu CÓ ÍT NHẤT MỘT ngón tay ĐANG kéo về hướng này"""
		return direction.lower() in self.active_slidings

	def touchCount(self):
		"""Trả về số lượng ngón tay ĐANG chạm trên màn hình (để làm vuốt 2 ngón, 3 ngón...)"""
		return len(self.touches)

	def keyPressed(self, key): return False
	def keyPressing(self, key, t=0): return False