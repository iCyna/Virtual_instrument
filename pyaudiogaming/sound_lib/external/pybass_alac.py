from __future__ import absolute_import
"BASS_ALAC wrapper by Christopher Toth"""

import ctypes
import os
from . import pybass
from pyaudiogaming import system

bass_fx_module = system.load_dll('bass_alac')
func_type = system.get_functype()

pybass.BASS_PluginLoad(system.get_path('bass_alac'), 0)

BASS_TAG_MP4 = 7
BASS_CTYPE_STREAM_ALAC = 0x10e00


#HSTREAM BASSALACDEF(BASS_ALAC_StreamCreateFile)(BOOL mem, const void *file, QWORD offset, QWORD length, DWORD flags);
BASS_ALAC_StreamCreateFile = func_type(pybass.HSTREAM, ctypes.c_byte, ctypes.c_void_p, pybass.QWORD, pybass.QWORD, ctypes.c_ulong)

#HSTREAM BASSALACDEF(BASS_ALAC_StreamCreateFileUser)(DWORD system, DWORD flags, const BASS_FILEPROCS *procs, void *user);
BASS_ALAC_StreamCreateFileUser = func_type(pybass.HSTREAM, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p)

