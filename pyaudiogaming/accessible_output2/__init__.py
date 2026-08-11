from __future__ import absolute_import
import ctypes
import os
import types
import sys
import importlib.util
from pyaudiogaming import system

def load_library(name,  	cdll=False):
	return system.load_dll(name, WinDLL=not cdll)

def get_output_classes():
    from . import outputs

    module_type = types.ModuleType
    classes = [
        m.output_class
        for m in outputs.__dict__.values()
        if isinstance(m, module_type) and hasattr(m, "output_class")
    ]
    return sorted(classes, key=lambda c: c.priority)

def find_datafiles():
    import platform
    from glob import glob
    import accessible_output2

    if platform.system() != "Windows":
        return []
    path = os.path.join(accessible_output2.__path__[0], "lib", "*.dll")
    results = glob(path)
    dest_dir = os.path.join("accessible_output2", "lib")
    return [(dest_dir, results)]
