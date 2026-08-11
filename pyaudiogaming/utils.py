# -*- coding: utf-8 -*-
# instant support utility toolkit
# copyright 2025 belong ihcyna (Labubu)<phucnggo29@gmail.com>.

import platform
import os
import sys
import subprocess
import shutil
import secrets
import string
import random
from . import system

try:
	unicode = unicode
except NameError:
	unicode = str

def convert_to_unicode(name):
	if platform.system() == 'Darwin':return name
	if isinstance(name, str):
		return unicode(name.encode(sys.getfilesystemencoding()))
	return None

def token(min=4, max=12, more=""):
	# make a random code token
    length = random.randint(min, max)
    if length < 4:
        raise ValueError("length phải >= 4")

    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    special = "!@#$%^&*"+more
    result = [
        secrets.choice(lower),
        secrets.choice(upper),
        secrets.choice(digits),
        secrets.choice(special)
    ]

    all_chars = lower + upper + digits + special
    result += [secrets.choice(all_chars) for _ in range(length - 4)]

    random.shuffle(result)

    return str(r''.join(result))

def run(cmd, sh=False):
	# run command line
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

def get_window():
	# get pointer window to access more
	from .buffer import frame as bf
	return bf

def is_url(path_string):
	# Convert to lowercase and check the prefix
	prefixes = ('http://', 'https://', 'ftp://')
   
	if str(path_string).strip().lower().startswith(prefixes):
		return True
	else:
		return False