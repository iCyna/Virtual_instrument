from __future__ import absolute_import
import os
import platform
import ctypes
from pyaudiogaming import system
from .base import Output


class NVDA(Output):
    """Supports The NVDA screen reader"""

    name = "NVDA"
    lib32 = "nvdaControllerClient32.dll"
    lib64 = "nvdaControllerClient64.dll"
    argtypes = {
        "nvdaController_brailleMessage": (ctypes.c_wchar_p,),
        "nvdaController_speakText": (ctypes.c_wchar_p,),
    }
    def __init__(self):
        super(NVDA, self).__init__()
        self.helper_lib = None

    def NVDAHelperLoader(self):
        li=None
        li=system.get_arch()["bit"]
        arm = system.get_arch()["is arm"]
        if li == 32 or li == 64:pass
        elif arm:
            li="64A"
        else: raise Error("Cannot load NVDA helper remote")
        self.helper_lib = system.load_dll(f"nvdaHelperRemote{li}", ot="windows", WinDLL=True)
        try:
            if self.helper_lib:
                self.helper_lib.nvdaHelperRemote_sendKey.argtypes = (ctypes.c_short, ctypes.c_int)
                self.helper_lib.nvdaHelperRemote_logMessage.argtypes = (ctypes.c_int, ctypes.c_wchar_p)
                self.helper_lib.injectIntoProcess.argtypes = (ctypes.c_int,)
                self.helper_lib.nvdaHelper_uninjectFromProcess.argtypes = (ctypes.c_int,)                

                res = self.helper_lib.nvdaHelperRemote_connect()
                if res != 0:
                    print(f"NVDA Helper Remote connected with code: {res}")
                
            return self.helper_lib
        except Exception as e:
            print(f"Error loading NVDA Helper: {e}")
            return None

    def is_active(self):
        try:
            return self.lib.nvdaController_testIfRunning() == 0
        except:
            return False

    def braille(self, text, **options):
        self.lib.nvdaController_brailleMessage(text)

    def speak(self, text, interrupt=False):
        if interrupt:
            self.silence()
        self.lib.nvdaController_speakText(text)

    def silence(self):
        self.lib.nvdaController_cancelSpeech()

    def connect_remote(self):
        lib = self.helper_lib
        return lib.nvdaHelperRemote_connect() == 0 if lib else False

    def disconnect_remote(self):
        lib=self.helper_lib
        return lib.nvdaHelperRemote_disconnect() == 0 if lib else False

    def inject(self, pid):
        lib=self.helper_lib
        return lib.nvdaHelper_injectIntoProcess(pid) == 0 if lib else False

    def uninject(self, pid):
        lib=self.helper_lib
        return lib.nvdaHelper_uninjectFromProcess(pid) == 0 if lib else False

    def send_key(self, vk_code, is_extended=False):
        lib=self.helper_lib
        return lib.nvdaHelperRemote_sendKey(vk_code, 1 if is_extended else 0) == 0 if lib else False

    def resync(self):
        lib=self.helper_lib
        return lib.nvdaHelperLocal_resync() == 0 if lib else False

    def get_version_helper(self):
        lib=self.helper_lib
        if lib:
            try: return lib.nvdaHelperRemote_getVersion()
            except: return None
        return None

    def install_input_hook(self):
        lib=self.helper_lib
        return lib.nvdaHelperRemote_installInputHook() == 0 if lib else False

    def uninstall_input_hook(self):
        lib=self.helper_lib
        return lib.nvdaHelperRemote_uninstallInputHook() == 0 if lib else False

    def is_server_running(self):
        lib=self.helper_lib
        return lib.nvdaHelperRemote_isServerRunning() == 0 if lib else False

    def log_message(self, level, message):
        lib=self.helper_lib
        if lib:
            # level: 0=debug, 1=info, 2=warning, 3=error
            return lib.nvdaHelperRemote_logMessage(level, message) == 0
        return False

output_class = NVDA