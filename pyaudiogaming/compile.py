# -*- coding: utf-8 -*-
# app build tool
#Idea from Yukio Nozawa and continue edit and fix by ihcyna(Labubu)

import os, sys, shutil, glob, ast
from pyaudiogaming import utils as common
from pyaudiogaming.file import *

def dopackage():
	print("Creating installer exe")
	rar_path = r"C:\Program Files\WinRAR\rar.exe"  # Thay thế đường dẫn nếu WinRAR được cài ở nơi khác
	if not os.path.exists(rar_path):
		print("Error: WinRAR not found at %s" % rar_path)
		sys.exit(1)
	
	f = open("_build.bat", "w+")
	f.write("\"%s\" a -cfg- -ed -ep1 -k -m5 -r -sfx \"-ztools\\rar_options.txt\" \"%s.exe\" \"%s.dist\\*\"" % (rar_path, PROJECT_FULL_NAME, PROJECT))
	f.close()
	common.run("cmd /c _build.bat")
	os.remove("_build.bat")

def build(PROJECT, PROJECT_FULL_NAME, args_compile=[], data=[], rename_file=None, packet=False, zstandard=True,  mode="pyinstaller"):
	print(PROJECT, PROJECT_FULL_NAME, args_compile, data, rename_file, packet)
	if PROJECT is None:
		PROJECT=PROJECT_FULL_NAME
	elif PROJECT_FULL_NAME is None:
		PROJECT_FULL_NAME=PROJECT
	elif PROJECT is None and PROJECT_FULL_NAME is None:
		print("Error: you should fill full project or file name you want compile!")
		sys.exit()

	if not isinstance(args_compile, list): args_compile = []
	if rename_file is None: rename_file = PROJECT_FULL_NAME
	if zstandard:
		if not any(a.strip().startswith("--onefile") for a in args_compile):
			args_compile.append("--onefile")
		args_compile[:] = [a for a in args_compile if not a.strip().startswith("--name")]
		args_compile[:] = [a for a in args_compile if not a.strip().startswith("--distpath")]
		args_compile.append(f"--name {rename_file}")
		args_compile.append(f"--distpath dist/{PROJECT_FULL_NAME}")

	libdata = ["include", "lib", "utils"]
	print("Building %s. This will take several minutes. Please wait..." % PROJECT)
	if "--skip-compile" in sys.argv:
		print("Skipping to packaging")
		if packet: dopackage()
		print("Done!")
		sys.exit()

	copydir=""

	cmd="%s %s %s.py" % (mode, " ".join(args_compile) if args_compile and isinstance(args_compile, list) else "", PROJECT)
	copydir="dist/%s"%PROJECT_FULL_NAME
	common.run(cmd, sh=True)
	print("making libraries")
	try:
		for libname in libdata:
			#common.mkdir("%s/%s" % (copydir, libname))
			shutil.copytree("pyaudiogaming/%s"%libname, "%s/%s" % (copydir, libname), dirs_exist_ok=True)
		if data:
			for elem in data:
				print("copying %s"%elem)
				shutil.copytree(elem, "%s/%s" % (copydir, elem), dirs_exist_ok=True)
				print("Copying %s files..."%elem)
	except: pass
	if packet: dopackage()
	print("Done!")

if __name__ == "__main__":
	name = sys.argv[0]
	args = sys.argv
	if not args: sys.exit()
	mode="build.txt"
	try:
		mode=sys.argv[1]
	except:pass
	if "." not in mode: print("error you need pass args as filename");sys.exit()
	f=File(password="", encode=False, aes=False)
	if not f.check(mode): sys.exit()
	text=f.load(mode, mode="r+", type="txt")
	if not text: sys.exit()
	text = list(text.splitlines())

	if len(text) < 6:
		print("Error: not true type of compile building config pyaudiogaming needs!")
		sys.exit()
	index=-1
	text = [line for line in text if not line.strip().startswith(("#", "//", "!", "@"))]
	for i in text:
		index+=1
		if i=="Null":
			text[index]=None
		elif i.startswith("[") and i.endswith("]"):
			text[index] = [str(x).strip() for x in ast.literal_eval(i)]
		elif i == "0" or i == "1":
			print("true or false", text[index])
			text[index] = True if i == "1" else False
	#try:
	build(*text)
	#except Exception as e:print(f"Error while compiling: {mode}: {e}")