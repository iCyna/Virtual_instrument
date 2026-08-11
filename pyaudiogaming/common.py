# -*- coding: utf-8 -*-
# copyright 2025 belong ihcyna (Labubu)<phucnggo29@gmail.com>.

import os
import sys
import subprocess
import shutil

def run(cmd, sh=False):
	print("Executing: %s" % cmd)
	subprocess.call(cmd.split(),shell=sh)

def mkdir(fld):
	sys.stdout.write("Checking directory: %s ... " % fld)
	if os.path.isdir(fld):
		sys.stdout.write("exists\n")
		return
	else:
		os.mkdir(fld)
		sys.stdout.write("created\n")
