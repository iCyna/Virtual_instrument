# -*- coding: utf-8 -*-
# copyright 2025 belong ihcyna (Labubu)<phucnggo29@gmail.com>.
#files loader, saver and encoder functions etc

import json
import hashlib
import pickle
import os
import shutil
import base64
from cryptography.fernet import Fernet
import io
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

class File:
	def __init__(self, password: str, encode: bool = False, aes: bool = False):
		self.key = self.generate_key(password)
		self.cipher = self.dokey(self.key)
		self.aes_key = hashlib.sha256(password.encode()).digest()  # Tạo khóa AES từ khóa Fernet
		self.file_obj = None
		self.encode = encode
		self.aes = aes

	@staticmethod
	def generate_key(password: str) -> bytes:
		"""
		Tạo key từ mật khẩu bằng cách băm SHA-256.
		"""
		return base64.urlsafe_b64encode(hashlib.sha256(password.encode()).digest())

	@staticmethod
	def dokey(key: bytes) -> Fernet:
		"""
		Tạo đối tượng Fernet từ key.
		"""
		return Fernet(key)
	def aes_encrypt(self, data: bytes) -> bytes:
		"""
		Mã hóa dữ liệu bằng AES.
		"""
		iv = os.urandom(16)
		cipher = AES.new(self.aes_key, AES.MODE_CBC, iv)
		encrypted_data = cipher.encrypt(pad(data, AES.block_size))
		return iv + encrypted_data  # Ghép IV với dữ liệu đã mã hóa

	def aes_decrypt(self, data: bytes) -> bytes:
		"""
		Giải mã dữ liệu bằng AES.
		"""
		iv = data[:16]
		encrypted_data = data[16:]
		cipher = AES.new(self.aes_key, AES.MODE_CBC, iv)
		return unpad(cipher.decrypt(encrypted_data), AES.block_size)
	def open(self, file_path, mode):
		self.file_obj = open(file_path, mode)

	def close(self):
		if self.file_obj:
			self.file_obj.close()
			self.file_obj = None

	def save(self, data, file_path, mode="w+", type=""):
		if type == "json":
			data = json.dumps(data)
		elif type == "pickle":
			data = pickle.dumps(data)
		elif type == "txt":
			data = str(data)

		if self.encode:
			data = self.cipher.encrypt(data.encode('utf-8'))
			if self.aes: data = self.aes_encrypt(data)  # Mã hóa thêm bằng AES
		with open(file_path, mode) as file:
			file.write(data)

	def load(self, file_path: str, mode="r+", type: str = ""):
		with open(file_path, mode) as file:
			data = file.read()
		if self.encode:
			if self.aes: data = self.aes_decrypt(data)
			data = self.cipher.decrypt(data).decode('utf-8')
		if type == "json":
			return json.loads(data)
		elif type == "pickle":
			return pickle.loads(data)
		return data

	def remove(self, file_path: str):
		if os.path.exists(file_path):
			return os.remove(file_path)

	def create(self, file_path: str):
		with open(file_path, 'w'): pass

	def check(self, file_path: str) -> bool:
		return os.path.exists(file_path)

	def replace(self, old_file, new_file):
		self.delete_file(old_file)
		shutil.move(new_file, old_file)

	def copy(self, src: str, dest: str):
		return shutil.copy(src, dest)

	def move(self, src, dest):
		return shutil.move(src, dest)
	# end class