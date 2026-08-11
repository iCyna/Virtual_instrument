# -*- coding: utf-8 -*-
# BASS_VST python wrapper
# copyright 2026 belong ihcyna (Labubu)<phucnggo29@gmail.com>.
# some ideas adapted from standard pybass wrappers.

__version__ = '0.1'
__author__ = 'ihcyna (Labubu) <phucnggo29@gmail.com>'
__doc__ = '''
pybassvst.py - is ctypes python module for BASS_VST.
BASS_VST is an extension to the BASS audio library, providing the ability
to use VST plugins in BASS channels (DSP effects) and load VSTi instruments.
'''

import ctypes
import os
from . import pybass
from pyaudiogaming import system

QWORD = pybass.QWORD
HSTREAM = pybass.HSTREAM

bassvst_module = system.load_dll('bass_vst')
func_type = system.get_functype()
pybass.BASS_PluginLoad(system.get_path('bass_vst'), 0)

# --- BASS_VST Flags ---
BASS_VST_KEEP_CHANS = 0x00000001
BASS_VST_SCOPE_SPECTRUM = 0x00000000
BASS_VST_SCOPE_OSCILLATOR = 0x00000001

# --- BASS_VST Structures ---

class BASS_VST_INFO(ctypes.Structure):
    _fields_ = [
        ('channelHandle', ctypes.c_ulong),    # DWORD
        ('uniqueID', ctypes.c_ulong),         # DWORD
        ('effectName', ctypes.c_char * 80),   # char[80]
        ('effectVersion', ctypes.c_ulong),    # DWORD
        ('effectVstVersion', ctypes.c_ulong), # DWORD
        ('hostVstVersion', ctypes.c_ulong),   # DWORD
        ('productName', ctypes.c_char * 80),  # char[80]
        ('vendorName', ctypes.c_char * 80),   # char[80]
        ('vendorVersion', ctypes.c_ulong),    # DWORD
        ('chansIn', ctypes.c_ulong),          # DWORD
        ('chansOut', ctypes.c_ulong),         # DWORD
        ('initialDelay', ctypes.c_ulong),     # DWORD
        ('hasEditor', ctypes.c_ulong),        # DWORD
        ('editorWidth', ctypes.c_ulong),      # DWORD
        ('editorHeight', ctypes.c_ulong),     # DWORD
        ('aeffect', ctypes.c_void_p),         # AEffect*
        ('isInstrument', ctypes.c_ulong),     # DWORD
        ('dspHandle', ctypes.c_ulong)         # HDSP
    ]

class BASS_VST_PARAM_INFO(ctypes.Structure):
    _fields_ = [
        ('name', ctypes.c_char * 16),         # char[16]
        ('unit', ctypes.c_char * 16),         # char[16]
        ('display', ctypes.c_char * 16),      # char[16]
        ('defaultValue', ctypes.c_float)      # float
    ]

# --- BASS_VST Functions ---

# DWORD BASS_VST_ChannelSetDSP(DWORD chan, const void *dllFile, DWORD flags, int priority);
BASS_VST_ChannelSetDSP = func_type(ctypes.c_ulong, ctypes.c_ulong, ctypes.c_char_p, ctypes.c_ulong, ctypes.c_int)(('BASS_VST_ChannelSetDSP', bassvst_module))

# BOOL BASS_VST_ChannelRemoveDSP(DWORD chan, DWORD vstHandle);
BASS_VST_ChannelRemoveDSP = func_type(ctypes.c_byte, ctypes.c_ulong, ctypes.c_ulong)(('BASS_VST_ChannelRemoveDSP', bassvst_module))

# DWORD BASS_VST_ChannelCreate(DWORD freq, DWORD chans, const void *dllFile, DWORD flags);
BASS_VST_ChannelCreate = func_type(ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_char_p, ctypes.c_ulong)(('BASS_VST_ChannelCreate', bassvst_module))

# BOOL BASS_VST_ChannelFree(DWORD vstHandle);
BASS_VST_ChannelFree = func_type(ctypes.c_byte, ctypes.c_ulong)(('BASS_VST_ChannelFree', bassvst_module))

# BOOL BASS_VST_GetInfo(DWORD vstHandle, BASS_VST_INFO *info);
BASS_VST_GetInfo = func_type(ctypes.c_byte, ctypes.c_ulong, ctypes.POINTER(BASS_VST_INFO))(('BASS_VST_GetInfo', bassvst_module))

# int BASS_VST_GetParamCount(DWORD vstHandle);
BASS_VST_GetParamCount = func_type(ctypes.c_int, ctypes.c_ulong)(('BASS_VST_GetParamCount', bassvst_module))

# float BASS_VST_GetParam(DWORD vstHandle, int paramIndex);
BASS_VST_GetParam = func_type(ctypes.c_float, ctypes.c_ulong, ctypes.c_int)(('BASS_VST_GetParam', bassvst_module))

# BOOL BASS_VST_SetParam(DWORD vstHandle, int paramIndex, float value);
BASS_VST_SetParam = func_type(ctypes.c_byte, ctypes.c_ulong, ctypes.c_int, ctypes.c_float)(('BASS_VST_SetParam', bassvst_module))

# BOOL BASS_VST_GetParamInfo(DWORD vstHandle, int paramIndex, BASS_VST_PARAM_INFO *info);
BASS_VST_GetParamInfo = func_type(ctypes.c_byte, ctypes.c_ulong, ctypes.c_int, ctypes.POINTER(BASS_VST_PARAM_INFO))(('BASS_VST_GetParamInfo', bassvst_module))

# int BASS_VST_GetProgramCount(DWORD vstHandle);
BASS_VST_GetProgramCount = func_type(ctypes.c_int, ctypes.c_ulong)(('BASS_VST_GetProgramCount', bassvst_module))

# int BASS_VST_GetProgram(DWORD vstHandle);
BASS_VST_GetProgram = func_type(ctypes.c_int, ctypes.c_ulong)(('BASS_VST_GetProgram', bassvst_module))

# BOOL BASS_VST_SetProgram(DWORD vstHandle, int programIndex);
BASS_VST_SetProgram = func_type(ctypes.c_byte, ctypes.c_ulong, ctypes.c_int)(('BASS_VST_SetProgram', bassvst_module))

# DWORD BASS_VST_EmbedEditor(DWORD vstHandle, HWND parentWindow);
BASS_VST_EmbedEditor = func_type(ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p)(('BASS_VST_EmbedEditor', bassvst_module))