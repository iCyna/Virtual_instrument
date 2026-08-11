# -*- coding: utf-8 -*-
# PyAudioGaming ADB Device Control Center & Automation Menu
# Integrated strictly in English for absolute professional standards

import os
import re
import subprocess
from pyaudiogaming.system import match, get_platform, module_path, embedded_data_path
from pyaudiogaming.menu import menu

class ADBController:
	def __init__(self):
		self.adb_path = self._resolve_adb_path()
		self.start_server()

	def _resolve_adb_path(self):
		"""Resolves the correct platform binary dynamically using engine system methods."""
		plat_info = get_platform()
		os_name = plat_info["os"].lower()
		
		ext = ".exe" if os_name == "windows" else ""
		adb_filename = f"adb-{os_name}\\adb{ext}"

		# Locating binaries safely using native system framework locations
		possible_paths = [
			match(module_path(), "include", adb_filename),
			match(embedded_data_path(), "include", adb_filename),
			match(os.path.dirname(module_path()), "include", adb_filename)
		]

		for path in possible_paths:
			if os.path.exists(path):
				if os_name in ("linux", "macos"):
					try:
						os.chmod(path, 0o755)
					except Exception as e:
						print(e)
				return os.path.abspath(path)

		return "adb"

	def run_cmd(self, args: list) -> str:
		"""Executes the specialized architecture-specific ADB standalone binary."""
		try:
			startupinfo = None
			if os.name == 'nt':
				startupinfo = subprocess.STARTUPINFO()
				startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

			cmd = [self.adb_path] + args
			result = subprocess.run(
				cmd,
				stdout=subprocess.PIPE,
				stderr=subprocess.PIPE,
				text=True,
				encoding="utf-8",
				errors="ignore",
				startupinfo=startupinfo
			)
			return result.stdout
		except Exception as e:
			print(e)
			return f"Error: {str(e)}"

	def start_server(self):
		self.run_cmd(["start-server"])

	def get_devices(self) -> list:
		output = self.run_cmd(["devices"])
		devices = []
		# Lấy các dòng có chứa "device" và bỏ qua dòng tiêu đề
		for line in output.splitlines():
			if "\t" in line:  # Kiểm tra tab + device
				dev_id = line.split()[0] # Chỉ lấy phần ID (phần trước khoảng trắng)
				devices.append(dev_id)
		print(f"DEBUG: Found devices: {devices}")
		print(f"{output}\n{devices}")
		return devices

	def swipe(self, device_id: str, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 250):
		self.run_cmd(["-s", device_id, "shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms)])

	def press_key(self, device_id: str, keycode: int):
		self.run_cmd(["-s", device_id, "shell", "input", "keyevent", str(keycode)])

	def dump_hierarchy(self, device_id: str) -> str:
		self.run_cmd(["-s", device_id, "shell", "uiautomator", "dump", "/data/local/tmp/uidump.xml"])
		return self.run_cmd(["-s", device_id, "shell", "cat", "/data/local/tmp/uidump.xml"])

	def extract_ui_elements(self, xml_content: str) -> list:
		if not xml_content or "xml" not in xml_content:
			return []
		pattern = r'(text|content-desc)="([^"]+)"'
		matches = re.findall(pattern, xml_content)
		return [value.strip() for attr, value in matches if value.strip()]


class ADBControlCenter:
	def __init__(self, wnd):
		self.wnd = wnd
		self.adb = ADBController()
		self.selected_device = None
		# Display coordinate defaults for swiping calculations
		self.screen_width = 1080
		self.screen_height = 1920
		self.start_interface()

	def start_interface(self):
		"""Initializes and runs the absolute English control menu interface loop."""
		devices = self.adb.get_devices()
		main_menu = menu()
		menu_items = []
		if not devices:
			menu_items.append("No active Android devices discovered &D")
		else:
			for i, dev in enumerate(devices):
				menu_items.append(f"Select device {dev} &{i}")
		menu_items.append("Simulate active device manual gestures &G")
		menu_items.append("Scrape current GUI hierarchy context &S")
		menu_items.append("Send Home button trigger event &H")
		menu_items.append("Send Back button trigger event &B")
		menu_items.append("Force restart ADB engine server &R")
		menu_items.append("Exit control center utility &E")

		main_menu.initialize(self.wnd, ttl="Android Device Bridge Control Center Menu", items=menu_items)
		main_menu.open()

		is_running = True
		while is_running:
			self.wnd.frameUpdate()
			res = main_menu.frameUpdate()


			if res is not None:
				if res == -1 or main_menu.isLast(res):
					self.wnd.say("Exiting control interface.")
					is_running = False
					break
				selected_text = main_menu.getString(res)
				if "Select device" in selected_text and devices:
					self.selected_device = devices[res]
					self.wnd.say(f"Active focus attached to device {self.selected_device}")
					
				elif "No active Android devices" in selected_text:
					self.wnd.say("Discovery list empty. Please connect a hardware unit or emulator.")
					
				elif "Simulate active device manual gestures" in selected_text:
					if not self.selected_device:
						self.wnd.say("Action denied. Attach target device first.")
					else:
						self.wnd.say("Continuous manual gesture engine online. Use Arrow keys with 2 or 3 fingers modifier.")
						while 1:
							self.wnd.frameUpdate()
							if self.handle_continuous_gestures(): break

						
				elif "Scrape current GUI hierarchy context" in selected_text:
					if not self.selected_device:
						self.wnd.say("Please select a valid device target first.")
					else:
						self.wnd.say("Scraping interface layout hierarchy. Please wait.")
						xml = self.adb.dump_hierarchy(self.selected_device)
						elements = self.adb.extract_ui_elements(xml)
						if elements:
							self.wnd.say(f"Scraped elements found. Leading records: {', '.join(elements[:3])}")
						else:
							self.wnd.say("Layout vector scraped successfully but returned empty visible text fields.")
							
				elif "Send Home button" in selected_text:
					if self.selected_device:
						self.adb.press_key(self.selected_device, 3) # KEYCODE_HOME
						self.wnd.say("Home keyevent dispatched.")
					else:
						self.wnd.say("No target selected.")
						
				elif "Send Back button" in selected_text:
					if self.selected_device:
						self.adb.press_key(self.selected_device, 4) # KEYCODE_BACK
						self.wnd.say("Back keyevent dispatched.")
					else:
						self.wnd.say("No target selected.")
						
				elif "Force restart ADB engine server" in selected_text:
					self.wnd.say("Killing server subsystem.")
					self.adb.run_cmd(["kill-server"])
					self.adb.start_server()
					self.wnd.say("Server initialized again. Refreshing configuration.")
					is_running = False

	def handle_continuous_gestures(self):
		"""
		Manages real-time fluid directional swiping with exact coordinate calculation.
		Listens to strings using window.keyPressing(name, t=200) without importing pygame.
		Modifiers: Two-finger simulation = '2' key, Three-finger simulation = '3' key.
		"""
		# Determine current swipe scale coefficient using window native mapping
		multiplier = 1.0
		if self.wnd.keyPressed("exit"): return True
		if self.wnd.keyPressing("two"):
			multiplier = 2.0
		elif self.wnd.keyPressing("three"):
			multiplier = 3.0

		mid_x = self.screen_width // 2
		mid_y = self.screen_height // 2
		
		# Custom swipe offset scale mapping based on finger weights
		offset_x = int(300 * multiplier)
		offset_y = int(400 * multiplier)

		# 4 Directions execution blocks mapped with string identifiers
		if self.wnd.keyPressing("up", t=200):
			self.wnd.say(f"Swiping Up with scale intensity factor {multiplier}")
			self.adb.swipe(self.selected_device, mid_x, mid_y + offset_y, mid_x, mid_y - offset_y)

		elif self.wnd.keyPressing("down", t=200):
			self.wnd.say(f"Swiping Down with scale intensity factor {multiplier}")
			self.adb.swipe(self.selected_device, mid_x, mid_y - offset_y, mid_x, mid_y + offset_y)

		elif self.wnd.keyPressing("left", t=200):
			self.wnd.say(f"Swiping Left with scale intensity factor {multiplier}")
			self.adb.swipe(self.selected_device, mid_x + offset_x, mid_y, mid_x - offset_x, mid_y)

		elif self.wnd.keyPressing("right", t=200):
			self.wnd.say(f"Swiping Right with scale intensity factor {multiplier}")
			self.adb.swipe(self.selected_device, mid_x - offset_x, mid_y, mid_x + offset_x, mid_y)

if __name__ == "__main__":
	from pyaudiogaming.window import *
	w=Window()
	w.init(400,400, f"Androix bridge for {get_platform()}")
	ADBControlCenter(w)