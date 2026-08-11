# -*- coding: utf-8 -*-
# Copyright 2026 belong ihcyna (Labubu) <phucnggo29@gmail.com>.
# BASS_FX environmental FX presets - DX8 Reverb Version (ổn định, bám sát lõi BASS).

from .sound_lib.external.pybass import *
from .sound_lib.external.pybass_fx import *

class Basic:
    """Central BASS_FX preset collection.

    - Đã chuyển hoàn toàn sang BASS_FX_DX8_REVERB của pybass.
    - Căn chỉnh fReverbMix và fReverbTime để tạo hiệu ứng không gian chân thực.
    """

    def __init__(self):
        BASS_FX_GetVersion()

        self.fxs = {
            # -----------------------------------------------------------------
            # ENVIRONMENT / ROOM REVERB (Sử dụng DX8 REVERB Lõi)
            # -----------------------------------------------------------------
            "large room": {"name": BASS_FX_DX8_REVERB, "param": self.large_room},
            "small room": {"name": BASS_FX_DX8_REVERB, "param": self.small_room},
            "hall": {"name": BASS_FX_DX8_REVERB, "param": self.hall},
            "long hallway": {"name": BASS_FX_DX8_REVERB, "param": self.long_hallway},
            "city": {"name": BASS_FX_DX8_REVERB, "param": self.city},
            "bedroom": {"name": BASS_FX_DX8_REVERB, "param": self.bedroom},
            "cave": {"name": BASS_FX_DX8_REVERB, "param": self.cave},
            "concert_arena": {"name": BASS_FX_DX8_REVERB, "param": self.concert_arena},
            "bathroom": {"name": BASS_FX_DX8_REVERB, "param": self.bathroom},
            "studio_vocal_booth": {"name": BASS_FX_DX8_REVERB, "param": self.studio_vocal_booth},
            "canyon": {"name": BASS_FX_DX8_REVERB, "param": self.canyon},

            # Extra environmental variants.
            "hallway_bright": {"name": BASS_FX_DX8_REVERB, "param": self.hallway_bright},
            "hallway_dark": {"name": BASS_FX_DX8_REVERB, "param": self.hallway_dark},
            "city_open": {"name": BASS_FX_DX8_REVERB, "param": self.city_open},
            "city_narrow": {"name": BASS_FX_DX8_REVERB, "param": self.city_narrow},
            "warehouse": {"name": BASS_FX_DX8_REVERB, "param": self.warehouse},
            "stone_room": {"name": BASS_FX_DX8_REVERB, "param": self.stone_room},

            # Modulation / dynamics / coloration.
            "flanger_space": {"name": BASS_FX_BFX_FLANGER, "param": self.flanger_space},
            "flanger_tunnel": {"name": BASS_FX_BFX_FLANGER, "param": self.flanger_tunnel},
            "radio_distortion": {"name": BASS_FX_BFX_DISTORTION, "param": self.radio_distortion},
            "telephone_distortion": {"name": BASS_FX_BFX_DISTORTION, "param": self.telephone_distortion},
            "studio_compressor": {"name": BASS_FX_BFX_COMPRESSOR2, "param": self.studio_compressor},
            "voice_leveler": {"name": BASS_FX_BFX_COMPRESSOR2, "param": self.voice_leveler},
            "chorus_ensemble": {"name": BASS_FX_BFX_CHORUS, "param": self.chorus_ensemble},
            "chorus_wide": {"name": BASS_FX_BFX_CHORUS, "param": self.chorus_wide},
            "phaser_robot": {"name": BASS_FX_BFX_PHASER, "param": self.phaser_robot},
            "phaser_slow": {"name": BASS_FX_BFX_PHASER, "param": self.phaser_slow},
            "vinyl_lofi": {"name": BASS_FX_BFX_DISTORTION, "param": self.vinyl_lofi},
            "hard_limiter": {"name": BASS_FX_BFX_COMPRESSOR2, "param": self.hard_limiter},
        }

        self.filters = {
            "muffled_wall": {"name": BASS_FX_BFX_BQF, "param": self.bqf_lowpass_wall},
            "underwater": {"name": BASS_FX_BFX_LPF, "param": self.lpf_underwater},
            "telephone_line": {"name": BASS_FX_BFX_BQF, "param": self.bqf_bandpass_phone},
            "subwoofer_boost": {"name": BASS_FX_BFX_PEAKEQ, "param": self.peakeq_bass_boost},
            "eq_low_mid_scoop": {"name": BASS_FX_BFX_PEAKEQ, "param": self.eq_low_mid_scoop},
            "eq_presence_boost": {"name": BASS_FX_BFX_PEAKEQ, "param": self.eq_presence_boost},
            "eq_air_highs": {"name": BASS_FX_BFX_PEAKEQ, "param": self.eq_air_highs},
            "eq_mud_cut": {"name": BASS_FX_BFX_PEAKEQ, "param": self.eq_mud_cut},
            "bqf_highpass_radio": {"name": BASS_FX_BFX_BQF, "param": self.bqf_highpass_radio},
            "bqf_notch_60hz": {"name": BASS_FX_BFX_BQF, "param": self.bqf_notch_60hz},
            "bqf_peaking_mid": {"name": BASS_FX_BFX_BQF, "param": self.bqf_peaking_mid},
            "lpf_muffled_neighbor": {"name": BASS_FX_BFX_LPF, "param": self.lpf_muffled_neighbor},
            "megaphone_extreme": {"name": BASS_FX_BFX_BQF, "param": self.megaphone_extreme},
            "sub_bass_rumble": {"name": BASS_FX_BFX_BQF, "param": self.sub_bass_rumble},
            "hpf_crystal_clear": {"name": BASS_FX_BFX_BQF, "param": self.hpf_crystal_clear},
            "allpass_phase": {"name": BASS_FX_BFX_BQF, "param": self.allpass_phase},
            "low_shelf_warm": {"name": BASS_FX_BFX_BQF, "param": self.low_shelf_warm},
            "high_shelf_air": {"name": BASS_FX_BFX_BQF, "param": self.high_shelf_air},
            "low_shelf_dark": {"name": BASS_FX_BFX_BQF, "param": self.low_shelf_dark},
            "high_shelf_dark": {"name": BASS_FX_BFX_BQF, "param": self.high_shelf_dark},
            "lowpass_dark": {"name": BASS_FX_BFX_BQF, "param": self.lowpass_dark},
            "lowpass_voice_muffle": {"name": BASS_FX_BFX_BQF, "param": self.lowpass_voice_muffle},
            "lowpass_wall_soft": {"name": BASS_FX_BFX_BQF, "param": self.lowpass_wall_soft},
            "highpass_rumble_cut": {"name": BASS_FX_BFX_BQF, "param": self.highpass_rumble_cut},
            "highpass_light": {"name": BASS_FX_BFX_BQF, "param": self.highpass_light},
            "bandpass_walkie_talkie": {"name": BASS_FX_BFX_BQF, "param": self.bandpass_walkie_talkie},
            "bandpass_radio": {"name": BASS_FX_BFX_BQF, "param": self.bandpass_radio},
            "bandpass_voice": {"name": BASS_FX_BFX_BQF, "param": self.bandpass_voice},
            "presence_clarity": {"name": BASS_FX_BFX_BQF, "param": self.presence_clarity},
            "treble_sparkle": {"name": BASS_FX_BFX_BQF, "param": self.treble_sparkle},
            "mud_reduction": {"name": BASS_FX_BFX_BQF, "param": self.mud_reduction},
            "boxiness_cut": {"name": BASS_FX_BFX_BQF, "param": self.boxiness_cut},
        }

    # =====================================================================
    # REVERB / ROOMS (Chuyển sang BASS_DX8_REVERB)
    # =====================================================================

    def _dx8_reverb(self, in_gain=0.0, reverb_mix=-10.0, reverb_time=1000.0, hf_ratio=0.001):
        """Khởi tạo BASS_DX8_REVERB
        fInGain: [-96.0, 0.0] Mặc định 0.0
        fReverbMix: [-96.0, 0.0] 0.0 là cực đại (vang to nhất)
        fReverbTime: [0.001, 3000.0] Thời gian kéo dài đuôi vang (ms)
        fHighFreqRTRatio: [0.001, 0.999]
        """
        params = BASS_DX8_REVERB()
        params.fInGain = float(in_gain)
        params.fReverbMix = float(reverb_mix)
        params.fReverbTime = float(reverb_time)
        params.fHighFreqRTRatio = float(hf_ratio)
        return params

    def small_room(self):
        return self._dx8_reverb(reverb_mix=-12.0, reverb_time=800.0)

    def large_room(self):
        return self._dx8_reverb(reverb_mix=-25.0, reverb_time=1500.0)

    def hall(self):
        return self._dx8_reverb(reverb_mix=-6.0, reverb_time=2200.0)

    def long_hallway(self):
        return self._dx8_reverb(reverb_mix=-10.0, reverb_time=1800.0)

    def hallway_bright(self):
        return self._dx8_reverb(reverb_mix=-8.0, reverb_time=1600.0, hf_ratio=0.5)

    def hallway_dark(self):
        return self._dx8_reverb(reverb_mix=-14.0, reverb_time=1500.0, hf_ratio=0.001)

    def city(self):
        return self._dx8_reverb(reverb_mix=-15.0, reverb_time=1200.0)

    def city_open(self):
        return self._dx8_reverb(reverb_mix=-31.0, reverb_time=120.0)

    def city_narrow(self):
        return self._dx8_reverb(reverb_mix=-10.0, reverb_time=1500.0)

    def bedroom(self):
        return self._dx8_reverb(reverb_mix=-18.0, reverb_time=500.0)

    def cave(self):
        return self._dx8_reverb(reverb_mix=-2.0, reverb_time=2800.0)

    def concert_arena(self):
        return self._dx8_reverb(reverb_mix=-4.0, reverb_time=2500.0)

    def bathroom(self):
        return self._dx8_reverb(reverb_mix=-10.0, reverb_time=900.0, hf_ratio=0.6)

    def studio_vocal_booth(self):
        return self._dx8_reverb(reverb_mix=-25.0, reverb_time=200.0)

    def canyon(self):
        return self._dx8_reverb(reverb_mix=0.0, reverb_time=3000.0)

    def warehouse(self):
        return self._dx8_reverb(reverb_mix=-6.0, reverb_time=2400.0)

    def stone_room(self):
        return self._dx8_reverb(reverb_mix=-9.0, reverb_time=1400.0, hf_ratio=0.8)

    # =====================================================================
    # MODULATION / DISTORTION / DYNAMICS
    # =====================================================================

    def flanger_space(self):
        params = BASS_BFX_FLANGER()
        params.fWetDry = 0.42
        params.fSpeed = 0.028
        params.lChannel = BASS_BFX_CHANALL
        return params

    def flanger_tunnel(self):
        params = BASS_BFX_FLANGER()
        params.fWetDry = 0.28
        params.fSpeed = 0.012
        params.lChannel = BASS_BFX_CHANALL
        return params

    def radio_distortion(self):
        params = BASS_BFX_DISTORTION()
        params.fDrive = 2.2
        params.fDryMix = 0.78
        params.fWetMix = 0.58
        params.fFeedback = 0.04
        params.fVolume = 1.0
        params.lChannel = BASS_BFX_CHANALL
        return params

    def telephone_distortion(self):
        params = BASS_BFX_DISTORTION()
        params.fDrive = 1.55
        params.fDryMix = 0.86
        params.fWetMix = 0.36
        params.fFeedback = 0.02
        params.fVolume = 1.0
        params.lChannel = BASS_BFX_CHANALL
        return params

    def vinyl_lofi(self):
        params = BASS_BFX_DISTORTION()
        params.fDrive = 1.08
        params.fDryMix = 0.90
        params.fWetMix = 0.26
        params.fFeedback = 0.0
        params.fVolume = 1.0
        params.lChannel = BASS_BFX_CHANALL
        return params

    def studio_compressor(self):
        params = BASS_BFX_COMPRESSOR2()
        params.fGain = 3.0
        params.fThreshold = -20.0
        params.fRatio = 2.5
        params.fAttack = 10.0
        params.fRelease = 180.0
        params.lChannel = BASS_BFX_CHANALL
        return params

    def voice_leveler(self):
        params = BASS_BFX_COMPRESSOR2()
        params.fGain = 4.0
        params.fThreshold = -24.0
        params.fRatio = 3.0
        params.fAttack = 14.0
        params.fRelease = 240.0
        params.lChannel = BASS_BFX_CHANALL
        return params

    def hard_limiter(self):
        params = BASS_BFX_COMPRESSOR2()
        params.fGain = 0.0
        params.fThreshold = -2.0
        params.fRatio = 20.0
        params.fAttack = 1.0
        params.fRelease = 80.0
        params.lChannel = BASS_BFX_CHANALL
        return params

    def chorus_ensemble(self):
        params = BASS_BFX_CHORUS()
        params.fDryMix = 0.90
        params.fWetMix = 0.42
        params.fFeedback = 0.10
        params.fMinSweep = 0.8
        params.fMaxSweep = 9.0
        params.fRate = 1.3
        params.lChannel = BASS_BFX_CHANALL
        return params

    def chorus_wide(self):
        params = BASS_BFX_CHORUS()
        params.fDryMix = 0.82
        params.fWetMix = 0.55
        params.fFeedback = 0.08
        params.fMinSweep = 1.0
        params.fMaxSweep = 14.0
        params.fRate = 0.75
        params.lChannel = BASS_BFX_CHANALL
        return params

    def phaser_robot(self):
        params = BASS_BFX_PHASER()
        params.fDryMix = 0.86
        params.fWetMix = 0.52
        params.fFeedback = 0.24
        params.fRate = 1.1
        params.fRange = 3.2
        params.fFreq = 900.0
        params.lChannel = BASS_BFX_CHANALL
        return params

    def phaser_slow(self):
        params = BASS_BFX_PHASER()
        params.fDryMix = 0.90
        params.fWetMix = 0.36
        params.fFeedback = 0.12
        params.fRate = 0.35
        params.fRange = 2.2
        params.fFreq = 700.0
        params.lChannel = BASS_BFX_CHANALL
        return params

# =====================================================================
    # PEAK EQ (Đã ép Gain lên mức ±8dB đến ±12dB)
    # =====================================================================

    def _peakeq(self, band, center, gain, bw=0.0):
        """Khởi tạo BASS_BFX_PEAKEQ
        fBandwidth ưu tiên hơn fQ. Bw nhỏ (0.2 - 0.5) = Đỉnh cực nhọn. Bw lớn (1.0 - 2.0) = Dải rộng.
        """
        params = BASS_BFX_PEAKEQ()
        params.lBand = int(band)
        params.fBandwidth = float(bw) # Tính bằng quãng 8 (octaves)
        params.fCenter = float(center)
        params.fGain = float(gain)
        params.lChannel = float(BASS_BFX_CHANALL)
        return params

    def peakeq_bass_boost(self):
        # Đẩy siêu bạo lực âm trầm dội thẳng vào màng nhĩ
        return self._peakeq(band=0, center=60.0, gain=12.0, bw=1.5)

    def eq_mud_cut(self):
        # Khoét sạch dải lùng bùng, âm thanh sẽ rỗng ruột ngay lập tức
        return self._peakeq(band=1, center=250.0, gain=-10.0, bw=1.0)

    def eq_low_mid_scoop(self):
        # Gọt sạch mid-low, tiếng mỏng và sắc lại
        return self._peakeq(band=2, center=500.0, gain=-8.0, bw=1.2)

    def eq_presence_boost(self):
        # Đâm thẳng dải "hiện diện", giọng nói/tiếng bước chân xé tai, cực rõ
        return self._peakeq(band=3, center=3500.0, gain=9.0, bw=0.8)

    def eq_air_highs(self):
        # Tiếng xì xì, leng keng của âm cao được đẩy lên chói tai
        return self._peakeq(band=4, center=12000.0, gain=10.0, bw=1.2)

    # =====================================================================
    # BIQUAD FILTERS (Đã siết dải tần số và tăng cực đại Q)
    # =====================================================================

    def _bqf(self, kind, center, gain=0.0, bandwidth=0.0, q=0.707, slope=0.707):
        """Khởi tạo BASS_BFX_BQF
        Nếu bandwidth = 0, bộ lọc sẽ dùng thông số Q. Q càng cao, lọc càng gắt và có độ "réo".
        """
        params = BASS_BFX_BQF()
        params.lFilter = int(kind)
        params.fCenter = float(center)
        params.fGain = float(gain)
        params.fBandwidth = float(bandwidth)
        params.fQ = float(q)
        params.fS = float(slope)
        params.lChannel = float(BASS_BFX_CHANALL)
        return params

    def bqf_lowpass_wall(self):
        # Bị cản qua 3 lớp tường dày. Cắt cụt mọi thứ trên 350Hz. Chỉ còn tiếng sụp sụp.
        return self._bqf(BASS_BFX_BQF_LOWPASS, center=350.0, q=0.5)

    def lowpass_wall_soft(self):
        # Bức tường mỏng / gỗ. Cắt ở 800Hz.
        return self._bqf(BASS_BFX_BQF_LOWPASS, center=800.0, q=0.6)

    def lpf_underwater(self):
        # Ở dưới nước. Lowpass với Q rất cao (2.5) tạo ra tiếng ùng oàng cộng hưởng ở 400Hz.
        return self._bqf(BASS_BFX_BQF_LOWPASS, center=400.0, q=2.5)

    def lpf_muffled_neighbor(self):
        # Nghe lén hàng xóm. Gần giống tường nhưng rè hơn một chút.
        return self._bqf(BASS_BFX_BQF_LOWPASS, center=600.0, q=0.8)

    def lowpass_dark(self):
        # Che 1 tấm chăn dày lên loa. Mất hết độ sáng.
        return self._bqf(BASS_BFX_BQF_LOWPASS, center=1200.0, q=0.707)

    def lowpass_voice_muffle(self):
        # Ngạt mũi / Bịt miệng. 
        return self._bqf(BASS_BFX_BQF_LOWPASS, center=900.0, q=0.707)

    def bqf_bandpass_phone(self):
        # Điện thoại bàn cổ. Q=2.5 ép dải âm cực nhỏ và the thé.
        return self._bqf(BASS_BFX_BQF_BANDPASS, center=1200.0, q=2.5)

    def megaphone_extreme(self):
        # Loa phường / Loa cầm tay. Tập trung năng lượng ở 2500Hz gây chói gắt.
        return self._bqf(BASS_BFX_BQF_BANDPASS, center=2500.0, q=3.5)

    def bandpass_walkie_talkie(self):
        # Bộ đàm quân sự. Ngẹt, nhiễu và đục.
        return self._bqf(BASS_BFX_BQF_BANDPASS, center=1800.0, q=4.0)

    def bandpass_radio(self):
        # Radio cũ.
        return self._bqf(BASS_BFX_BQF_BANDPASS, center=2000.0, q=2.0)

    def bandpass_voice(self):
        # Cắt sạch bass và treble, chỉ chừa lại giọng người
        return self._bqf(BASS_BFX_BQF_BANDPASS, center=1000.0, q=1.0)

    def bqf_highpass_radio(self):
        # Loa laptop rởm. Mất sạch bass dưới 900Hz.
        return self._bqf(BASS_BFX_BQF_HIGHPASS, center=900.0, q=1.0)

    def hpf_crystal_clear(self):
        # Trong vắt nhưng mỏng lét. Highpass ở 2500Hz.
        return self._bqf(BASS_BFX_BQF_HIGHPASS, center=2500.0, q=0.8)

    def highpass_rumble_cut(self):
        # Cắt triệt để dải sub siêu trầm (dưới 120Hz).
        return self._bqf(BASS_BFX_BQF_HIGHPASS, center=120.0, q=1.5)

    def highpass_light(self):
        # Mất ấm áp, hơi chua chua.
        return self._bqf(BASS_BFX_BQF_HIGHPASS, center=300.0, q=0.707)

    def bqf_notch_60hz(self):
        # Xóa sổ tiếng rè dòng điện xoay chiều. Notch cực nhọn.
        return self._bqf(BASS_BFX_BQF_NOTCH, center=60.0, q=4.0)

    def bqf_peaking_mid(self):
        # Tôn phần giọng lên rõ rệt.
        return self._bqf(BASS_BFX_BQF_PEAKINGEQ, center=1000.0, gain=8.0, q=1.0)

    def allpass_phase(self):
        # Đảo pha dải 1200Hz, tạo cảm giác âm thanh bị dịch chuyển trong đầu.
        return self._bqf(BASS_BFX_BQF_ALLPASS, center=1200.0, q=1.5)

    def low_shelf_warm(self):
        # Shelving lọc dải bass. Âm trầm phủ dày cộp cả phòng.
        return self._bqf(BASS_BFX_BQF_LOWSHELF, center=200.0, gain=8.0, slope=1.0)

    def low_shelf_dark(self):
        # Triệt tiêu dải bass bằng Shelf.
        return self._bqf(BASS_BFX_BQF_LOWSHELF, center=300.0, gain=-12.0, slope=1.0)

    def high_shelf_air(self):
        # Thổi độ tơi xốp, không khí vào âm thanh (mở cực gắt ở 5000Hz).
        return self._bqf(BASS_BFX_BQF_HIGHSHELF, center=5000.0, gain=9.0, slope=1.0)

    def high_shelf_dark(self):
        # Trùm mền toàn bộ phần Treble.
        return self._bqf(BASS_BFX_BQF_HIGHSHELF, center=4000.0, gain=-15.0, slope=1.0)

    def presence_clarity(self):
        # Ép tiếng vỡ mặt, rõ mồn một.
        return self._bqf(BASS_BFX_BQF_PEAKINGEQ, center=3200.0, gain=10.0, q=1.5)

    def treble_sparkle(self):
        # Siêu bén. Nếu bật filter này với các âm sắc có đuôi .wav có thể sẽ nghe xì xì rất rõ.
        return self._bqf(BASS_BFX_BQF_PEAKINGEQ, center=8000.0, gain=8.0, q=1.5)

    def mud_reduction(self):
        # Chuyên trị các âm lùng bùng.
        return self._bqf(BASS_BFX_BQF_PEAKINGEQ, center=280.0, gain=-10.0, q=1.2)

    def boxiness_cut(self):
        # Hết âm thanh dạng "úp hộp mỳ tôm lên tai".
        return self._bqf(BASS_BFX_BQF_PEAKINGEQ, center=500.0, gain=-8.0, q=1.0)

    def sub_bass_rumble(self):
        # Chỉ giữ lại đúng phần rền vang của sấm chớp, hoặc bom nổ. Cắt mọi thứ trên 80Hz.
        return self._bqf(BASS_BFX_BQF_LOWPASS, center=80.0, q=1.0)