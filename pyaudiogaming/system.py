# -*- coding: utf-8 -*-
#System checker for libraries

import platform
import os
import sys
import ctypes
import struct

def is_frozen():
	return hasattr(sys, "frozen")

def embedded_data_path():
	if is_frozen():
		return os.path.dirname(sys.executable)
	return os.path.dirname(__file__)

def abspath(path):
	return os.path.abspath(path)

def match(*args, abspath=True):
	path=os.path.join(*args)
	if abspath: path=os.path.abspath(path)
	return path

def module_path():
	return os.path.dirname(__file__)

def get_functype():
	return ctypes.CFUNCTYPE

def get_path(name):
	name=name+get_ext()
	arch_dir = get_arch_dir()
	if arch_dir:
		return os.path.join(module_path(), "lib", arch_dir, name)
	else:
		return os.path.join(module_path(), "lib", name)

def get_platform():
	system = platform.system().lower()
	machine = platform.machine().lower()
	result = {
		"os": "unknown",
		"arch": machine,
		"is_emulator": False
	}

	if system == "windows":
		result["os"] = "windows"
	elif system == "linux":
		if "ANDROID_ROOT" in os.environ:
			result["os"] = "android"
			if "generic" in os.environ.get("BUILD_FINGERPRINT", "").lower():
				result["is_emulator"] = True
		else:
			result["os"] = "linux"

	elif system == "darwin":
		if os.environ.get("SIMULATOR_DEVICE_NAME"):
			result["os"] = "ios"
			result["is_emulator"] = True
		else:
			result["os"] = "macos"

	return result

def get_arch() -> dict:	   
	machine = platform.machine().lower()
	is_arm = any(keyword in machine for keyword in ["arm", "aarch64", "v7a", "v8a"])
	return {"bit": struct.calcsize("P") * 8, "machine": machine, "is arm": is_arm}

def get_arch_dir():
	arch_dir=None
	info = get_platform()
	os_name = info["os"].lower()
	arch = get_arch()
	bit = arch.get("bit", 64)
	machine = arch.get("machine", "").lower()

	if os_name == "windows" or os_name=="macos":
		arch_dir = "x64" if bit == 64 else "x86"

	elif os_name == "linux":
		if "aarch64" in machine or "arm64" in machine:
			arch_dir = "aarch64"
		elif "arm" in machine:
			arch_dir = "armhf"
		else:
			arch_dir = "x64" if bit == 64 else "x86"
	return arch_dir

def get_ext():
	ext=None
	os_name=get_platform()["os"].lower()
	if os_name == "windows":
		ext = ".dll"
	elif os_name in ("linux", "android"):
		ext = ".so"
	elif os_name in ("macos", "ios"):
		ext = ".dylib"
	else:
		raise RuntimeError("Unsupported OS")
	return ext

def load_dll(name, ot="all", WinDLL=False):
	os_name=get_platform()["os"]
	if ot != "all" and os_name != ot:
		raise OSError(f"Library '{name}' not allowed on {os_name}, expected '{ot}'")

	filename = name if name.endswith(get_ext()) else name + get_ext()

	# ===== ANDROID / IOS =====
	if os_name in ("android", "ios"):
		try:
			return ctypes.CDLL(filename, mode=ctypes.RTLD_GLOBAL)
		except Exception as e:
			raise OSError(f"[{os_name}] Cannot load {filename}: {e}")

	# ===== ARCH DIR =====
	arch_dir = get_arch_dir()

	paths = []
	paths.append(os.path.join(module_path(), "lib", filename))
	paths.append(os.path.join(embedded_data_path(), "lib", filename))
	if arch_dir:
		paths.append(os.path.join(module_path(), "lib", arch_dir, filename))
		paths.append(os.path.join(embedded_data_path(), "lib", arch_dir, filename))
	# ===== LOAD =====
	last_error = None

	for p in paths:
		if os.path.exists(p):
			try:
				if os_name == "windows":
					if WinDLL:
						return ctypes.WinDLL(p)
					else:
						return ctypes.CDLL(p)
				else:
					return ctypes.CDLL(p)
			except Exception as e:
				last_error = e

	# fallback system
	try:
		if os_name == "windows":
			if WinDLL:
				return ctypes.WinDLL(filename)
			else:
				return ctypes.CDLL(filename)
		else:
			return ctypes.CDLL(filename)
	except Exception as e:
		last_error = e

	raise OSError(f"Cannot load library {filename}: {last_error}")