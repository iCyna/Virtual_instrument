import ctypes
import math
import os
import traceback
from pyaudiogaming import system


phonon = system.load_dll("phonon")

class IPLVector3(ctypes.Structure):
    _fields_ = [("x", ctypes.c_float),
                ("y", ctypes.c_float),
                ("z", ctypes.c_float)]

class IPLAudioSettings(ctypes.Structure):
    _fields_ = [("samplingRate", ctypes.c_int32),
                ("frameSize", ctypes.c_int32)]

class IPLHRTFSettings(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int),
                ("sofaFileName", ctypes.c_char_p),
                ("sofaData", ctypes.POINTER(ctypes.c_uint8)),
                ("sofaDataSize", ctypes.c_int),
                ("volume", ctypes.c_float),
                ("normType", ctypes.c_int)]

class IPLContextSettings(ctypes.Structure):
    _fields_ = [("version", ctypes.c_uint32),
                ("logCallback", ctypes.CFUNCTYPE(None, ctypes.c_char_p)),
                ("allocateCallback", ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_size_t)),
                ("freeCallback", ctypes.CFUNCTYPE(None, ctypes.c_void_p)),
                ("simdLevel", ctypes.c_int),
                ("flags", ctypes.c_int)]

class IPLBinauralEffectSettings(ctypes.Structure):
    _fields_ = [("hrtf", ctypes.c_void_p)]

class IPLBinauralEffectParams(ctypes.Structure):
    _fields_ = [("direction", IPLVector3),
                ("interpolation", ctypes.c_int),
                ("spatialBlend", ctypes.c_float),
                ("hrtf", ctypes.c_void_p),
                ("peakDelays", ctypes.POINTER(ctypes.c_float))]

class IPLAudioBuffer(ctypes.Structure):
    _fields_ = [("numChannels", ctypes.c_int32),
                ("numSamples", ctypes.c_int32),
                ("data", ctypes.POINTER(ctypes.POINTER(ctypes.c_float)))]

phonon_context = None
phonon_audio_settings = IPLAudioSettings(48000, 128)
phonon_hrtf = None
hrtf_effect = None

def create_audio_buffer(num_channels, num_samples):
    buffer = (ctypes.POINTER(ctypes.c_float) * num_channels)()
    for i in range(num_channels):
        buffer[i] = (ctypes.c_float * num_samples)()
    return buffer

def initialize_phonon():
    global phonon_context, phonon_hrtf, hrtf_effect
    #hrtf_effect=None
    if phonon_hrtf is not None:
        phonon.iplHRTFRelease(ctypes.byref(phonon_hrtf))
        phonon_hrtf=None
    if phonon_context is None:
        phonon_context = ctypes.c_void_p()
        phonon_context_settings = IPLContextSettings()
        phonon_context_settings.version = 263171  
        phonon.iplContextCreate(ctypes.byref(phonon_context_settings), ctypes.byref(phonon_context))
    if phonon_hrtf is None:
        phonon_hrtf = ctypes.c_void_p()
        phonon_hrtf_settings = IPLHRTFSettings()
        phonon_hrtf_settings.type = 0
        phonon_hrtf_settings.volume = 1.0
        phonon.iplHRTFCreate(phonon_context, ctypes.byref(phonon_audio_settings), ctypes.byref(phonon_hrtf_settings), ctypes.byref(phonon_hrtf))
    if hrtf_effect is None:
        hrtf_effect = ctypes.c_void_p()
        effect_settings = IPLBinauralEffectSettings()
        effect_settings.hrtf = phonon_hrtf
        phonon.iplBinauralEffectCreate(phonon_context, ctypes.byref(phonon_audio_settings), ctypes.byref(effect_settings), ctypes.byref(hrtf_effect))

def calculate_relative_direction(source_position, listener_position, listener_ahead, listener_up):
    dx = source_position.x - listener_position.x
    dy = source_position.y - listener_position.y
    dz = source_position.z - listener_position.z

    length = math.sqrt(dx*dx + dy*dy + dz*dz)
    if length > 0:
        dx /= length
        dy /= length
        dz /= length

    return IPLVector3(dx, dy, dz)

def phonon_dsp(audio_data, x, y, z, volume_step, channels):
    if x == 0 and y == 0 and z == 0:
        return audio_data
    
    try:
        initialize_phonon()

        blend = 1.0

        samples = len(audio_data) // ctypes.sizeof(ctypes.c_float)
        float_buffer = (ctypes.c_float * samples).from_buffer_copy(audio_data)

        chunk_size = phonon_audio_settings.frameSize
        processed_chunks = []

        for chunk_start in range(0, samples, chunk_size * channels):
            chunk_end = min(chunk_start + chunk_size * channels, samples)
            chunk_samples = (chunk_end - chunk_start) // channels

            in_buffer = create_audio_buffer(channels, chunk_samples)
            out_buffer = create_audio_buffer(2, chunk_samples)
            mono_buffer = create_audio_buffer(1, chunk_samples)

            inbuffer = IPLAudioBuffer(channels, chunk_samples, in_buffer)
            outbuffer = IPLAudioBuffer(2, chunk_samples, out_buffer)
            mono_inbuffer = IPLAudioBuffer(1, chunk_samples, mono_buffer)

            volume = 1.0 - (math.floor(math.sqrt(x**2 + y**2 + z**2))) / (125.0 / volume_step)

            chunk_buffer = float_buffer[chunk_start:chunk_end]
            amp = 10 ** ((volume * 100 - 100) / 20) if volume > 0 else 0
            for i in range(chunk_samples):
                for ch in range(channels):
                    in_buffer[ch][i] = chunk_buffer[i * channels + ch] * amp

            chunk_buffer_pointer = (ctypes.c_float * (chunk_samples * channels))(*chunk_buffer)

            phonon.iplAudioBufferDeinterleave(phonon_context, chunk_buffer_pointer, ctypes.byref(inbuffer))
            
            if channels == 2:
                phonon.iplAudioBufferDownmix(phonon_context, ctypes.byref(inbuffer), ctypes.byref(mono_inbuffer))
            else:
                mono_inbuffer = inbuffer

            effect_params = IPLBinauralEffectParams()
            source_position = IPLVector3(x, y, z)
            listener_position = IPLVector3(0, 0, 0)
            listener_ahead = IPLVector3(0, 0, 1)
            listener_up = IPLVector3(0, 1, 0)
            
            effect_params.direction = calculate_relative_direction(source_position, listener_position, listener_ahead, listener_up)
            effect_params.interpolation = 1
            effect_params.spatialBlend = blend
            effect_params.hrtf = phonon_hrtf
            effect_params.peakDelays = None

            phonon.iplBinauralEffectApply(hrtf_effect, ctypes.byref(effect_params), ctypes.byref(mono_inbuffer), ctypes.byref(outbuffer))
            processed_chunk = (ctypes.c_float * (chunk_samples * 2))()
            phonon.iplAudioBufferInterleave(phonon_context, ctypes.byref(outbuffer), processed_chunk)
            processed_chunks.append(processed_chunk)

        result_buffer = (ctypes.c_float * (samples * 2 // channels))()
        result_index = 0
        for chunk in processed_chunks:
            ctypes.memmove(ctypes.byref(result_buffer, result_index * ctypes.sizeof(ctypes.c_float)),
                           chunk,
                           len(chunk) * ctypes.sizeof(ctypes.c_float))
            result_index += len(chunk)

        return bytes(result_buffer)

    except Exception as e:
        print(f"Error in phonon_dsp: {e}")
        traceback.print_exc()
        raise