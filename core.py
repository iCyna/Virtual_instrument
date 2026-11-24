"""Core application state, platform guards, and instrument resolution."""
from copy import deepcopy
from pathlib import Path
import sys

import pyaudiogaming.system as system

ROOT = Path(__file__).resolve().parent
GENERAL_FONT = ROOT / "sf2toolkit" / "GeneralUserGS-v1471.sf2"
OPTIONAL_FONTS = {"Strings.sf2", "Synth.sf2", "Flute.sf2"}

frame, input, output, loop, recording, recorder, encoder = None, None, None, True, False, None, None


def is_android():
    return system.get_platform().get("os") == "android"


def vst_supported():
    return not is_android()


def default_config():
    def inst_entry(sf2_rel, sf2_id):
        return {
            "active_engine": "sf2",
            "sf2_path": system.match(sf2_rel),
            "sf2_id": sf2_id,
            "vst_path": "",
            "vst_chunk": "",
            "vst3_path": "",
            "vst3_state": "",
            "vst3_use_native_gui": False,
        }
    return {
        "input device": -1,
        "output device": -1,
        "instruments": {
            "piano": inst_entry("sf2toolkit/GeneralUserGS-v1471.sf2", 0),
            "guitar": inst_entry("sf2toolkit/Acoustic Guitars JNv2.4.sf2", 3),
            "drum": inst_entry("sf2toolkit/GeneralUserGS-v1471.sf2", 0),
            "bass": inst_entry("sf2toolkit/GeneralUserGS-v1471.sf2", 32),
            "electronic drum": inst_entry("sf2toolkit/GeneralUserGS-v1471.sf2", 0),
            "strings": inst_entry("sf2toolkit/Strings.sf2", 48),
            "synth": inst_entry("sf2toolkit/Synth.sf2", 81),
            "flute": inst_entry("sf2toolkit/Flute.sf2", 73),
        },
    }


config = default_config()


def resolve_config(cfg, name):
    settings = deepcopy(cfg["instruments"][name])
    if not vst_supported() and settings.get("active_engine") in ("vst", "vst3"):
        settings["active_engine"] = "sf2"
    if settings.get("active_engine", "sf2") == "sf2":
        path = Path(settings.get("sf2_path", ""))
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_file() and path.name in OPTIONAL_FONTS:
            path = GENERAL_FONT
        if not path.is_file():
            raise FileNotFoundError(f"SoundFont not found: {path}. Select an SF2 in Settings.")
        settings["sf2_path"] = str(path)
    return settings


def open_live_instrument(cfg, name):
    from audio_instruments import musical, vst, vst3

    settings = resolve_config(cfg, name)
    engine = settings.get("active_engine", "sf2") if vst_supported() else "sf2"
    instrument = vst3() if engine == "vst3" else (vst() if engine == "vst" else musical())
    try:
        if engine == "vst3":
            if not instrument.create_instrument(settings.get("vst3_path", ""), frequency=44100):
                raise RuntimeError(f"Could not load {name} VST3. Check the .vst3 path and architecture.")
            if settings.get("vst3_state"):
                instrument.set_state(settings["vst3_state"])
        elif engine == "vst":
            if not instrument.create_instrument(settings.get("vst_path", ""), frequency=44100):
                raise RuntimeError(f"Could not load {name} VST. Check the DLL and architecture.")
            if settings.get("vst_chunk"):
                instrument.set_chunk(settings["vst_chunk"])
            instrument.send_event = lambda chan, event, param: instrument.send_midi(chan, event, param)
        else:
            instrument.create_empty_stream(channels=16)
            font = instrument.load_font(settings["sf2_path"])
            if not font or not instrument.set_fonts(font):
                raise RuntimeError(f"Could not load {name} SoundFont")
        channel = 9 if "drum" in name else 0
        instrument.send_event(channel, 2, int(settings.get("sf2_id", 0)))
        instrument.play()
        return instrument
    except Exception:
        instrument.close()
        raise


def load(w):
    import setting
    return setting.load(w)


def save():
    import setting
    return setting.save()


def exit():
    sys.exit()


def getW():
    return frame


import drums, guitar, piano

live_instruments = {
    "Piano": piano,
    "Guitar": guitar,
    "Drums": drums,
}
