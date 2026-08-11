# -*- coding: utf-8 -*-
import ctypes
import math
import threading
from . import system

# --- BẢNG HẰNG SỐ OPENAL ---
ALC_STEREO_SOFT = 0x1501
ALC_SHORT_SOFT = 0x1402
ALC_FORMAT_CHANNELS_SOFT = 0x1990
ALC_FORMAT_TYPE_SOFT = 0x1991
ALC_HRTF_SOFT = 0x1992
ALC_FREQUENCY = 0x1007
AL_FORMAT_MONO16 = 0x1101
AL_BUFFER = 0x1009
AL_POSITION = 0x1004
AL_PLAYING = 0x1014
AL_SOURCE_STATE = 0x1015
AL_BUFFERS_PROCESSED = 0x1016

_openal_dll = None
_render_lock = threading.RLock()

# [TỐI ƯU CỰC ĐỘ] CHỈ DÙNG 1 DEVICE VÀ 1 CONTEXT DUY NHẤT
_global_device = None
_global_context = None

def _load_openal_dll():
    global _openal_dll
    if _openal_dll: return _openal_dll
    dll = system.load_dll("alsoft.dll", ot="windows")
    
    # Ép kiểu 64-bit chống văng Game (Access Violation)
    dll.alcCreateContext.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
    dll.alcCreateContext.restype = ctypes.c_void_p
    dll.alcMakeContextCurrent.argtypes = [ctypes.c_void_p]
    dll.alcDestroyContext.argtypes = [ctypes.c_void_p]
    dll.alcGetProcAddress.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    dll.alcGetProcAddress.restype = ctypes.c_void_p

    dll.alGenSources.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_uint)]
    dll.alDeleteSources.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_uint)]
    dll.alGenBuffers.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_uint)]
    dll.alDeleteBuffers.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_uint)]
    
    dll.alBufferData.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    dll.alSourceQueueBuffers.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.POINTER(ctypes.c_uint)]
    dll.alSourceUnqueueBuffers.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.POINTER(ctypes.c_uint)]
    
    dll.alSourcePlay.argtypes = [ctypes.c_uint]
    dll.alSourcePause.argtypes = [ctypes.c_uint] # Thêm hàm Pause
    dll.alSourceStop.argtypes = [ctypes.c_uint]
    dll.alSourcei.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_int]
    dll.alSource3f.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_float, ctypes.c_float, ctypes.c_float]
    dll.alGetSourcei.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]

    _openal_dll = dll
    return dll

def _init_global_context(sample_rate):
    """Khởi tạo Context duy nhất cho toàn bộ hệ thống"""
    global _global_device, _global_context
    if _global_context: return

    dll = _load_openal_dll()
    addr = dll.alcGetProcAddress(None, b"alcLoopbackOpenDeviceSOFT")
    alcLoopbackOpenDeviceSOFT = ctypes.cast(addr, ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_char_p))
    _global_device = alcLoopbackOpenDeviceSOFT(None)

    attrs = (ctypes.c_int * 9)(ALC_FORMAT_CHANNELS_SOFT, ALC_STEREO_SOFT, ALC_FORMAT_TYPE_SOFT, ALC_SHORT_SOFT, ALC_FREQUENCY, sample_rate, ALC_HRTF_SOFT, 1, 0)
    _global_context = dll.alcCreateContext(_global_device, attrs)

class HRTF_Stream:
    """Mỗi âm thanh chỉ là một Source siêu nhẹ, không mở Context riêng"""
    def __init__(self, sample_rate):
        self.dll = _openal_dll
        self.sample_rate = sample_rate

        addr = self.dll.alcGetProcAddress(None, b"alcRenderSamplesSOFT")
        self._alcRenderSamplesSOFT = ctypes.cast(addr, ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int))

        with _render_lock:
            self.dll.alcMakeContextCurrent(_global_context)
            self.source = ctypes.c_uint(0)
            self.dll.alGenSources(1, ctypes.byref(self.source))
            # Chỉ cần 2 buffer luân phiên là đủ mượt, tốn rất ít RAM
            self.buffers = (ctypes.c_uint * 2)()
            self.dll.alGenBuffers(2, self.buffers)
            self.free_buffers = [self.buffers[0], self.buffers[1]]
            self.dll.alcMakeContextCurrent(None)

    def process(self, mono_pcm, num_frames, lx, ly, lz, sx, sy, sz):
        if num_frames <= 0 or not mono_pcm:
            return b''

        with _render_lock:
            # Gán ngữ cảnh cho Luồng hiện tại
            self.dll.alcMakeContextCurrent(_global_context)
            
            # 1. Thu hồi Buffer đã dùng
            processed = ctypes.c_int(0)
            self.dll.alGetSourcei(self.source.value, AL_BUFFERS_PROCESSED, ctypes.byref(processed))
            if processed.value > 0:
                bufs_to_unqueue = (ctypes.c_uint * processed.value)()
                self.dll.alSourceUnqueueBuffers(self.source.value, processed.value, bufs_to_unqueue)
                for i in range(processed.value):
                    self.free_buffers.append(bufs_to_unqueue[i])

            if not self.free_buffers:
                self.dll.alcMakeContextCurrent(None)
                return b'\x00' * (num_frames * 4)

            # 2. Nạp dữ liệu mới
            buf_to_use = self.free_buffers.pop(0)
            self.dll.alBufferData(buf_to_use, AL_FORMAT_MONO16, mono_pcm, num_frames * 2, self.sample_rate)
            self.dll.alSourceQueueBuffers(self.source.value, 1, ctypes.byref(ctypes.c_uint(buf_to_use)))

            # 3. Tính toán vị trí 3D
            dx, dy, dz = sx - lx, sy - ly, sz - lz
            rad_x = math.atan2(dx, dy) if (dx != 0 or dy != 0) else 0.0
            rad_y = math.atan2(dz, math.hypot(dx, dy))
            self.dll.alSource3f(self.source.value, AL_POSITION, math.sin(rad_x)*math.cos(rad_y), math.sin(rad_y), -math.cos(rad_x)*math.cos(rad_y))

            # 4. Kích hoạt Source
            self.dll.alSourcePlay(self.source.value)
            
            # 5. Render đúng số Frame
            out_buffer = (ctypes.c_short * (num_frames * 2))()
            self._alcRenderSamplesSOFT(_global_device, out_buffer, num_frames)
            
            # 6. [BÍ QUYẾT] Pause Source ngay lập tức để nó không bị chạy lố và giữ được hiệu ứng HRTF tail cho đợt sau
            self.dll.alSourcePause(self.source.value)
            
            self.dll.alcMakeContextCurrent(None)
            
            return ctypes.string_at(out_buffer, num_frames * 4)

    def destroy(self):
        with _render_lock:
            self.dll.alcMakeContextCurrent(_global_context)
            self.dll.alSourceStop(self.source.value)
            self.dll.alSourcei(self.source.value, AL_BUFFER, 0) # Xả sạch
            self.dll.alDeleteSources(1, ctypes.byref(self.source))
            self.dll.alDeleteBuffers(2, self.buffers)
            self.dll.alcMakeContextCurrent(None)


class OpenALLoopback:
    def __init__(self):
        self.active_streams = {}
        self.pool_lock = threading.RLock()

    def process_sound(self, handle_token, mono_pcm, num_frames, sample_rate, lx, ly, lz, sx, sy, sz):
        with self.pool_lock:
            if handle_token not in self.active_streams:
                _init_global_context(sample_rate)
                self.active_streams[handle_token] = HRTF_Stream(sample_rate)
                
            stream = self.active_streams[handle_token]
            
        return stream.process(mono_pcm, num_frames, lx, ly, lz, sx, sy, sz)

    def free_token(self, token):
        with self.pool_lock:
            if token in self.active_streams:
                stream = self.active_streams.pop(token)
                stream.destroy()

_instance = None
def get_openal_audio():
    global _instance
    if not _instance:
        _instance = OpenALLoopback()
    return _instance

def initialize_openal_audio(sample_rate=44100):
    try:
        _load_openal_dll()
        _init_global_context(sample_rate)
        return True
    except Exception:
        return False