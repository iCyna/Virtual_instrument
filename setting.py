"""Unified application settings: encrypted persistence, audio devices, SF2/VST2/VST3 & hybrid UI."""
import atexit
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import threading
import time

import pygame

import core
from pyaudiogaming import file as pf, vb
from pyaudiogaming.inputBox import kbt
from pyaudiogaming.sound_pool import input as audio_input, output as audio_output, playsingle

_VST3_PROBE_OK = set()
_VST3_CACHE = {}


def _cleanup_vst3_cache():
    for entry in list(_VST3_CACHE.values()):
        try:
            entry[0].close()
        except Exception:
            pass
    _VST3_CACHE.clear()


atexit.register(_cleanup_vst3_cache)

SETTINGS_FILE = "settings.tl"
SETTINGS_PASSWORD = "config key"
ENGINE_CODES_DESKTOP = ("sf2", "vst", "vst3")
ENGINE_LABELS_DESKTOP = ["SoundFont (SF2)", "VST2 Instrument (.dll)", "VST3 Instrument (.vst3)"]


def _merge_config(loaded):
    merged = core.default_config()
    if not isinstance(loaded, dict):
        return merged
    for key, val in loaded.items():
        if key == "instruments" and isinstance(val, dict):
            for inst_name, inst_cfg in val.items():
                if inst_name in merged["instruments"] and isinstance(inst_cfg, dict):
                    merged["instruments"][inst_name].update(inst_cfg)
                elif isinstance(inst_cfg, dict):
                    merged["instruments"][inst_name] = deepcopy(inst_cfg)
        else:
            merged[key] = val
    return merged


def load(w):
    core.frame = w
    w.fp = 60
    w.exit_callback = sys.exit
    store = pf.File(password=SETTINGS_PASSWORD, encode=True, aes=True)
    loaded = core.default_config()
    if store.check(SETTINGS_FILE):
        try:
            loaded = _merge_config(store.load(SETTINGS_FILE, mode="rb+", type="json"))
        except Exception as exc:
            print(f"Settings load warning: {exc}")
    core.config = loaded
    core.input = audio_input()
    core.output = audio_output(bbuffer=50)
    core.input.device = core.config.get("input device", -1)
    core.output.device = core.config.get("output device", -1)
    return core.config


def save():
    store = pf.File(password=SETTINGS_PASSWORD, encode=True, aes=True)
    if core.input is not None:
        core.config["input device"] = core.input.device
    if core.output is not None:
        core.config["output device"] = core.output.device
    w = core.getW()
    for attempt in range(3):
        if w is not None:
            w.frameUpdate()
        try:
            store.save(core.config, SETTINGS_FILE, mode="wb+", type="json")
            return True
        except Exception as exc:
            if attempt == 2:
                print(f"Settings save error: {exc}")
    return False


@contextmanager
def _preserve_screen():
    screen = pygame.display.get_surface()
    previous = screen.copy() if screen is not None else None
    try:
        yield
    finally:
        if previous is not None:
            screen.blit(previous, (0, 0))
            pygame.display.flip()


def _browse_file(w, title, suffix):
    try:
        path = kbt(None, title, title, file_dialog=True)
    except Exception:
        vb.info_box("File Browser", "Native file browsing is unavailable. Enter the path directly.", window=w)
        return None
    if not path:
        return None
    if Path(path).suffix.lower() != suffix:
        vb.warning_box("Invalid File", f"Please choose a {suffix} file.", window=w)
        return None
    return path


def _engine_to_index(engine_code, allow_vst):
    if not allow_vst:
        return 0
    return ENGINE_CODES_DESKTOP.index(engine_code) if engine_code in ENGINE_CODES_DESKTOP else 0


def _save_instrument_fields(w, inst_name, values, allow_vst):
    settings = core.config["instruments"][inst_name]
    try:
        program = int(str(values.get("sf2_id", "0")).strip())
        if not 0 <= program <= 127:
            raise ValueError
    except ValueError:
        vb.warning_box("Invalid Program", "Enter a SoundFont program from 0 to 127.", window=w)
        return False

    sf2_path = (values.get("sf2_path") or "").strip()
    vst_path = (values.get("vst_path") or "").strip() if allow_vst else settings.get("vst_path", "")
    vst3_path = (values.get("vst3_path") or "").strip() if allow_vst else settings.get("vst3_path", "")
    use_native_gui = bool(values.get("vst3_use_native_gui")) if allow_vst else settings.get("vst3_use_native_gui", False)

    checks = [("sf2_path", sf2_path, ".sf2", True)]
    if allow_vst:
        checks.append(("vst_path", vst_path, ".dll", True))
        checks.append(("vst3_path", vst3_path, ".vst3", False))

    for field, val, suffix, must_be_file in checks:
        if val and val != settings.get(field):
            path = Path(val)
            exists_ok = path.is_file() if must_be_file else path.exists()
            if path.suffix.lower() != suffix or not exists_ok:
                vb.warning_box("File Not Found", f"Enter the path to an existing {suffix} plugin/file.", window=w)
                return False

    engines = ENGINE_CODES_DESKTOP if allow_vst else ("sf2",)
    eng_idx = int(values.get("engine") or 0)
    engine = engines[eng_idx] if 0 <= eng_idx < len(engines) else "sf2"
    if allow_vst and vst_path != settings.get("vst_path", ""):
        settings["vst_chunk"] = ""
    if allow_vst and vst3_path != settings.get("vst3_path", ""):
        settings["vst3_state"] = ""
    settings.update(
        active_engine=engine, sf2_id=program, sf2_path=sf2_path,
        vst_path=vst_path, vst3_path=vst3_path, vst3_use_native_gui=use_native_gui,
    )
    save()
    w.say(f"{inst_name.title()} settings saved.")
    return True


def _discover_vst3_preset_banks(vst3_path):
    """Auto-discover factory preset banks (.sfz / .fxp / .vstpreset) on disk for known VST3 plugins."""
    banks = {}
    low = str(vst3_path or "").lower()
    if "sfizz" in low:
        sfz_root = core.ROOT / "collections" / "sfz"
        if sfz_root.is_dir():
            for sub in sorted(sfz_root.iterdir(), key=lambda item: item.name.lower()):
                if not sub.is_dir():
                    continue
                files = sorted(
                    [f for f in sub.rglob("*.sfz") if f.is_file()],
                    key=lambda item: item.name.lower(),
                )
                if files:
                    banks[sub.name] = [(f.stem, str(f)) for f in files]
        return banks

    roots = []
    if "surge" in low:
        for folder in (r"C:\ProgramData\Surge XT\patches_factory", r"C:\ProgramData\Surge XT\patches_3rdparty"):
            p = Path(folder)
            if p.is_dir():
                roots.append(p)
    for root in roots:
        for sub in sorted(root.iterdir(), key=lambda item: item.name.lower()):
            if not sub.is_dir():
                continue
            files = sorted(
                [f for f in sub.rglob("*") if f.is_file() and f.suffix.lower() in (".fxp", ".vstpreset")],
                key=lambda item: item.name.lower(),
            )
            if files:
                banks[sub.name] = [(f.stem, str(f)) for f in files]
    return banks


def _default_bank_for_instrument(inst_name, bank_names):
    pref_map = {
        "bass": ("Bass", "Basses"),
        "piano": ("Piano", "E-Piano", "Keys", "Polysynths"),
        "synth": ("Leads", "Plucks", "Polysynths"),
        "strings": ("Strings", "Pads", "Brass"),
        "flute": ("Flute", "Winds", "Leads"),
        "drum": ("Drums", "Percussion"),
        "electronic drum": ("Drums", "Percussion"),
        "guitar": ("Guitar", "Plucks", "Keys"),
    }
    for wanted in pref_map.get(inst_name, ()):
        for bname in bank_names:
            if wanted.lower() in bname.lower():
                return bname
    return bank_names[0] if bank_names else ""


def _filter_vst3_params(params, category, query):
    q = (query or "").strip().lower()
    out = []
    for info in params:
        if category != "All" and info.get("category", "Other") != category:
            continue
        if q and q not in info["label"].lower() and q not in info["name"].lower():
            continue
        out.append(info)
    return out


def _probe_vst3_safe(w, resolved_path, timeout_sec=25.0):
    """Verify VST3 loads cleanly via DawDreamer in an isolated child process while keeping main UI alive."""
    if resolved_path in _VST3_PROBE_OK:
        return True, ""
    code = (
        "import sys, dawdreamer as daw; "
        "eng = daw.RenderEngine(44100, 512); "
        "eng.make_plugin_processor('p', sys.argv[1]); "
        "print('OK')"
    )
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.Popen(
            [sys.executable, "-c", code, resolved_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=creationflags,
        )
    except Exception as exc:
        return False, f"Could not start VST3 probe: {exc}"

    w.say("Checking VST3 plugin... Press Escape to cancel.")
    start_t, last_beep_t, pct = time.time(), 0.0, 10
    while proc.poll() is None:
        w.frameUpdate()
        if w.keyPressed("esc") or w.keyPressed("exit"):
            proc.kill()
            w.say("Cancelled VST3 check.")
            return False, "Cancelled by user."
        if time.time() - start_t > timeout_sec:
            proc.kill()
            return False, f"Plugin hung for {int(timeout_sec)}s (missing factory data or incompatible VST3)."
        now = time.time()
        if now - last_beep_t >= 0.18:
            pct = min(90, pct + 4)
            try:
                playsingle("collections/audio/progress.ogg", pitch=15 + (pct * 5))
            except Exception:
                pass
            last_beep_t = now
        time.sleep(0.015)

    out, err = proc.communicate()
    if proc.returncode != 0 or "OK" not in (out or ""):
        detail = (err or out or "Unknown VST3 load failure").strip().splitlines()
        return False, detail[-1] if detail else "VST3 plugin failed to load."
    _VST3_PROBE_OK.add(resolved_path)
    return True, ""


def _load_vst3_with_progress(w, vst3_path, state_b64=""):
    """Safe VST3 loader: isolated DawDreamer probe prevents hangs/crashes, then caches in memory."""
    path_obj = Path(vst3_path)
    if path_obj.suffix.lower() != ".vst3" or not path_obj.exists():
        return None, [], f"Invalid or missing VST3 path: {vst3_path}"

    from audio_instruments import _resolve_vst3_bundle, vst3
    resolved = _resolve_vst3_bundle(vst3_path)

    if resolved in _VST3_CACHE:
        plugin, idx = _VST3_CACHE[resolved]
        if state_b64:
            plugin.set_state(state_b64)
            for entry in idx:
                entry["loaded"] = False
        return plugin, idx, ""

    ok, probe_err = _probe_vst3_safe(w, resolved, timeout_sec=25.0)
    if not ok:
        return None, [], probe_err

    plugin = vst3()
    try:
        w.frameUpdate()
        if not plugin.create_instrument(resolved, frequency=44100):
            return None, [], plugin.last_error or "Plugin failed to load."
        w.frameUpdate()
        if state_b64:
            plugin.set_state(state_b64)
            w.frameUpdate()
        idx = plugin.get_parameter_index() if hasattr(plugin, "get_parameter_index") else plugin.get_parameters()
        w.frameUpdate()
    except Exception as exc:
        plugin.close()
        return None, [], str(exc)

    _VST3_CACHE[resolved] = (plugin, idx)
    try:
        playsingle("collections/audio/progress.ogg", pitch=15 + (100 * 5))
    except Exception:
        pass
    return plugin, idx, ""


def open_vst3_parameter_form(w, inst_name, plugin, param_index=None, vst3_path=""):
    """Accessible VST3 studio form: Factory Preset Banks first, categories, search, F5, PageUp/PageDown."""
    all_params = param_index if param_index is not None else (
        plugin.get_parameter_index() if hasattr(plugin, "get_parameter_index") else plugin.get_parameters()
    )
    if not all_params:
        vb.info_box("VST3 Parameters", f"{inst_name.title()} exposes no editable parameters.", window=w)
        return False

    settings = core.config["instruments"][inst_name]
    presets = settings.setdefault("vst3_presets", {})
    banks = _discover_vst3_preset_banks(vst3_path or settings.get("vst3_path", ""))
    bank_names = list(banks.keys())
    cur_bank = _default_bank_for_instrument(inst_name, bank_names) if bank_names else ""
    cur_bank_preset_idx = 0

    program_param = next((p for p in all_params if p["name"] == "program"), None)
    if program_param is not None and hasattr(plugin, "hydrate_parameters"):
        w.frameUpdate()
        plugin.hydrate_parameters([program_param])
    if program_param is not None and not program_param.get("valid_values"):
        program_param = None

    body_params = [p for p in all_params if p is not program_param]
    cat_order = ["Quick / Main", "Oscillator / Voice", "Filter & Envelope", "LFO & Mod", "Effects & Mix", "Other"]
    present_cats = [c for c in cat_order if any(p.get("category") == c for p in body_params)]
    categories = present_cats + ["All"]

    cur_cat = categories[0]
    search_query = ""
    page_size = 10
    page = 0
    chan = 9 if "drum" in inst_name else 0
    test_notes = (36, 42, 38, 42) if "drum" in inst_name else ((36, 43, 45, 48) if inst_name == "bass" else (60, 64, 67, 72))

    while True:
        filtered = _filter_vst3_params(body_params, cur_cat, search_query)
        total_pages = max(1, (len(filtered) + page_size - 1) // page_size)
        page = max(0, min(page, total_pages - 1))
        chunk = filtered[page * page_size:(page + 1) * page_size]

        if chunk and hasattr(plugin, "hydrate_parameters"):
            unloaded = [p for p in chunk if not p.get("loaded")]
            if unloaded:
                w.frameUpdate()
                plugin.hydrate_parameters(unloaded)

        title = f"{inst_name.title()} VST3 [{cur_bank or cur_cat}] Page {page + 1}/{total_pages}"
        form = vb.form(w, config={"label": title, "adjacent_submit": False})

        # #1 Control right at the top: Factory Sound Bank + Sound Preset Browser (e.g. Surge XT 2,000+ presets!)
        if bank_names:
            bank_items = banks[cur_bank]
            cur_bank_preset_idx = max(0, min(cur_bank_preset_idx, len(bank_items) - 1))
            preset_labels = [f"{idx + 1}: {pname}" for idx, (pname, ppath) in enumerate(bank_items)]

            def on_bank_preset_change(frm, item):
                nonlocal cur_bank_preset_idx
                sel_idx = int(item.get("value") or 0)
                if 0 <= sel_idx < len(bank_items):
                    cur_bank_preset_idx = sel_idx
                    pname, ppath = bank_items[sel_idx]
                    if hasattr(plugin, "load_preset_file") and plugin.load_preset_file(ppath):
                        for entry in all_params:
                            entry["loaded"] = False
                        w.say(pname)
                        plugin.play_test_chord(notes=test_notes, dur_ms=360, chan=chan)

            form.add("sound_bank", "combo", value=bank_names.index(cur_bank), choices=bank_names,
                     label="Sound Bank (Basses, Leads, Plucks, Keys...)")
            form.add("switch_bank", "button", label="Open Selected Sound Bank")
            form.add("sound_preset", "combo", value=cur_bank_preset_idx, choices=preset_labels,
                     label=f"Sound Preset in {cur_bank} (Up/Down to switch & preview)", callback=on_bank_preset_change)

        if program_param is not None:
            raw_vals = list(program_param["valid_values"])
            labels = [f"{idx + 1}: {str(v).strip() or 'Preset ' + str(idx + 1)}" for idx, v in enumerate(raw_vals)]
            cur_val = program_param["value"]
            cur_idx = raw_vals.index(cur_val) if cur_val in raw_vals else 0

            def on_program_change(frm, item):
                sel_idx = int(item.get("value") or 0)
                if 0 <= sel_idx < len(raw_vals):
                    chosen = raw_vals[sel_idx]
                    plugin.set_parameter("program", chosen, use_raw=False)
                    program_param["value"] = chosen
                    w.say(labels[sel_idx])
                    plugin.play_test_chord(notes=test_notes, dur_ms=320, chan=chan)

            form.add("factory_program", "combo", value=cur_idx, choices=labels,
                     label="Factory Sound / Preset (Up/Down to switch & preview)", callback=on_program_change)

        form.add("test_sound", "button", label="Test Sound (F5)")
        form.add("load_preset_file", "button", label="Load Instrument / Preset File (.sfz / .fxp / .vstpreset)...")

        preset_names = sorted(presets.keys())
        if preset_names:
            form.add("preset_pick", "combo", value=0, choices=preset_names, label="My Saved Presets")
            form.add("load_preset", "button", label="Load Saved Preset")
        form.add("save_preset", "button", label="Save Current Sound As Preset...")

        form.add("category", "combo", value=categories.index(cur_cat), choices=categories,
                 label="Parameter Group")
        form.add("search", "input", value=search_query, label="Search Parameter")
        form.add("apply_filter", "button", label="Apply Group / Search")

        for idx, info in enumerate(chunk):
            fname = f"p_{idx}"
            disp = f" [{info['string_value']}]" if info.get("string_value") else ""
            lbl = f"{info['label']}{disp}"

            def make_cb(p_info, p_kind):
                def on_change(frm, item):
                    val = item.get("value")
                    if p_kind == "bool":
                        plugin.set_parameter(p_info["name"], bool(val), use_raw=False)
                        p_info["value"] = bool(val)
                    elif p_kind == "combo":
                        chosen = p_info["valid_values"][int(val or 0)]
                        plugin.set_parameter(p_info["name"], chosen, use_raw=False)
                        p_info["value"] = chosen
                    else:
                        raw = max(0.0, min(1.0, float(val or 0) / 100.0))
                        plugin.set_parameter(p_info["name"], raw, use_raw=True)
                        p_info["raw_value"] = raw
                    real_str = plugin.get_parameter_display(p_info["name"])
                    if real_str:
                        p_info["string_value"] = real_str
                        w.say(f"{p_info['label']}: {real_str}")
                return on_change

            if info["is_bool"]:
                form.add(fname, "switch", value=bool(info["value"]), label=lbl, callback=make_cb(info, "bool"))
            elif info["valid_values"] and len(info["valid_values"]) <= 40:
                choices = [str(v) for v in info["valid_values"]]
                cur_str = str(info["value"])
                cur_idx = choices.index(cur_str) if cur_str in choices else 0
                form.add(fname, "combo", value=cur_idx, choices=choices, label=lbl, callback=make_cb(info, "combo"))
            else:
                pct = max(0, min(100, int(round(info["raw_value"] * 100))))
                form.add(fname, "slider", value=pct, min=0, max=100, step=1, unit="%",
                         label=lbl, callback=make_cb(info, "slider"))

        if total_pages > 1:
            form.add("prev_page", "button", label="Previous Page (PageUp)")
            form.add("next_page", "button", label="Next Page (PageDown)")
        form.add("apply", "button", label="Save & Close")
        form.add("cancel", "button", label="Cancel")

        form.mainloop()
        action = None
        while action is None:
            w.frameUpdate()
            if w.keyPressed("pageup") or w.keyPressed("page_up"):
                if total_pages > 1:
                    page = (page - 1) % total_pages
                    w.say(f"Page {page + 1} of {total_pages}")
                    action = "_paging"
                    break
            if w.keyPressed("pagedown") or w.keyPressed("page_down"):
                if total_pages > 1:
                    page = (page + 1) % total_pages
                    w.say(f"Page {page + 1} of {total_pages}")
                    action = "_paging"
                    break
            if w.keyPressed("f5"):
                plugin.play_test_chord(notes=test_notes, chan=chan)
                w.say("Test sound")
                continue

            res = form.frameUpdate()
            if res == -1 or (res is not None and any(it["name"] == res and it["kind"] == "button" for it in form.items)):
                w.wait(5)
                action = res

        if action == "_paging":
            continue
        if action in (-1, "cancel"):
            return False
        if action == "switch_bank" and bank_names:
            cur_bank = bank_names[int(form.get("sound_bank") or 0)]
            cur_bank_preset_idx = 0
            first_name, first_path = banks[cur_bank][0]
            if hasattr(plugin, "load_preset_file") and plugin.load_preset_file(first_path):
                for entry in all_params:
                    entry["loaded"] = False
                w.say(f"Bank {cur_bank}: {first_name}")
                plugin.play_test_chord(notes=test_notes, dur_ms=360, chan=chan)
            continue
        if action == "load_preset_file":
            try:
                picked = kbt(None, "Load VST3 Preset", "Choose .fxp or .vstpreset file:", "", file_dialog=True)
            except Exception:
                picked = None
            if picked and hasattr(plugin, "load_preset_file") and plugin.load_preset_file(picked):
                for entry in all_params:
                    entry["loaded"] = False
                w.say(f"Loaded {Path(picked).stem}")
                plugin.play_test_chord(notes=test_notes, dur_ms=360, chan=chan)
            continue
        if action == "apply_filter":
            cur_cat = categories[int(form.get("category") or 0)]
            search_query = str(form.get("search") or "").strip()
            page = 0
            continue
        if action == "test_sound":
            plugin.play_test_chord(notes=test_notes, chan=chan)
            w.say("Test sound")
            continue
        if action == "load_preset" and preset_names:
            pname = preset_names[int(form.get("preset_pick") or 0)]
            if plugin.set_state(presets[pname]):
                for entry in all_params:
                    entry["loaded"] = False
                if program_param is not None and hasattr(plugin, "hydrate_parameters"):
                    plugin.hydrate_parameters([program_param], force=True)
                w.say(f"Loaded preset {pname}")
                plugin.play_test_chord(notes=test_notes, dur_ms=320, chan=chan)
            continue
        if action == "save_preset":
            pname = kbt(None, "Save VST3 Preset", "Enter preset name:", f"{inst_name.title()} Preset")
            if pname and pname.strip():
                presets[pname.strip()] = plugin.get_state()
                save()
                w.say(f"Saved preset {pname.strip()}")
            continue
        if action == "prev_page":
            page = (page - 1) % total_pages
            continue
        if action == "next_page":
            page = (page + 1) % total_pages
            continue
        if action == "apply":
            return True


def open_quick_vst3_controls(w, preferred_inst=None):
    """Quick launcher from the main UI (Ctrl+F1): jump straight to VST3 presets/controls."""
    if not core.vst_supported():
        vb.info_box("VST3 Unavailable", "VST3 plugins are disabled on Android.", window=w)
        return False
    instruments = list(core.config["instruments"].items())
    vst3_ready = [name for name, cfg in instruments if cfg.get("vst3_path")]
    if not vst3_ready:
        vb.info_box("No VST3 Configured", "No instrument has a VST3 path yet. Opening Settings (F1).", window=w)
        run()
        return False
    if preferred_inst in vst3_ready and len(vst3_ready) == 1:
        target = preferred_inst
    elif len(vst3_ready) == 1:
        target = vst3_ready[0]
    else:
        default_idx = vst3_ready.index(preferred_inst) if preferred_inst in vst3_ready else 0
        form = vb.form(w, config={"label": "Quick VST3 Controls", "adjacent_submit": False})
        form.add("inst", "combo", value=default_idx, choices=[n.title() for n in vst3_ready], label="VST3 Instrument")
        form.add("use_gui", "check", value=bool(core.config["instruments"][vst3_ready[default_idx]].get("vst3_use_native_gui", False)),
                 label="Use Native VST3 GUI (uncheck for vb.form)")
        form.add("open", "button", label="Open Controls / Presets")
        form.add("cancel", "button", label="Cancel")
        if form.open() != "open":
            return False
        target = vst3_ready[int(form.get("inst") or 0)]
        cfg = core.config["instruments"][target]
        return open_vst3_controls(w, target, cfg.get("vst3_path", ""), bool(form.get("use_gui")))

    cfg = core.config["instruments"][target]
    return open_vst3_controls(w, target, cfg.get("vst3_path", ""), bool(cfg.get("vst3_use_native_gui", False)))


def open_vst3_controls(w, inst_name, vst3_path, use_native_gui):
    """Open either the native VST3 GUI or accessible vb.form based on user checkbox."""
    if not core.vst_supported():
        vb.info_box("VST3 Unavailable", "VST3 plugins are automatically disabled on Android.", window=w)
        return False
    vst3_path = (vst3_path or "").strip()
    if not vst3_path or not Path(vst3_path).exists():
        vb.warning_box("Missing VST3", "Select an existing .vst3 plugin path first.", window=w)
        return False

    settings = core.config["instruments"][inst_name]
    plugin, param_index, err = _load_vst3_with_progress(w, vst3_path, settings.get("vst3_state", ""))
    if plugin is None:
        if err and err != "Cancelled by user.":
            vb.error_box("VST3 Load Error", err, window=w)
        return False

    try:
        if use_native_gui:
            w.say(f"Opening native GUI for {inst_name.title()}. Close the plugin window to save preset.")
            new_state = plugin.show_native_gui()
            if new_state:
                settings["vst3_state"] = new_state
            settings["vst3_path"] = vst3_path
            settings["vst3_use_native_gui"] = True
            save()
            w.say(f"Saved VST3 state for {inst_name.title()}.")
            return True

        changed = open_vst3_parameter_form(w, inst_name, plugin, param_index=param_index, vst3_path=vst3_path)
        if changed:
            settings["vst3_state"] = plugin.get_state()
            settings["vst3_path"] = vst3_path
            settings["vst3_use_native_gui"] = False
            save()
            w.say(f"Saved VST3 parameters for {inst_name.title()}.")
        return changed
    except Exception as exc:
        vb.error_box("VST3 Error", str(exc), window=w)
        return False


@_preserve_screen()
def open_instrument_settings(inst_name):
    w = core.getW()
    allow_vst = core.vst_supported()
    settings = core.config["instruments"][inst_name]
    form = vb.form(w, config={"label": f"{inst_name.title()} Settings", "adjacent_submit": False})
    engine_choices = ENGINE_LABELS_DESKTOP if allow_vst else ["SoundFont (SF2)"]
    eng_val = _engine_to_index(settings.get("active_engine", "sf2"), allow_vst)
    form.add("engine", "combo", value=eng_val, choices=engine_choices, label="Sound Engine")
    form.add("sf2_path", "input", value=settings.get("sf2_path", ""), label="SoundFont File (.sf2)")
    form.add("browse_sf2", "button", label="Browse SoundFont...")
    form.add("sf2_id", "input", value=str(settings.get("sf2_id", 0)), number_only=True, label="Program ID (0-127)")
    if allow_vst:
        form.add("vst_path", "input", value=settings.get("vst_path", ""), label="VST2 Instrument DLL")
        form.add("browse_vst", "button", label="Browse VST2 DLL...")
        form.add("vst3_path", "input", value=settings.get("vst3_path", ""), label="VST3 Instrument (.vst3)")
        form.add("browse_vst3", "button", label="Browse VST3...")
        form.add("vst3_use_native_gui", "check", value=bool(settings.get("vst3_use_native_gui", False)),
                 label="Use Native VST3 GUI (uncheck for vb.form)")
        form.add("open_vst3_ui", "button", label="Open VST3 Controls / GUI...")
    form.add("save", "button", label="Save")
    form.add("cancel", "button", label="Cancel")

    while True:
        action = form.open()
        if action in (-1, "cancel"):
            return
        if action == "browse_sf2":
            picked = _browse_file(w, "Choose a SoundFont (.sf2)", ".sf2")
            if picked:
                form.set("sf2_path", picked)
            continue
        if action == "browse_vst" and allow_vst:
            picked = _browse_file(w, "Choose a VST2 Instrument (.dll)", ".dll")
            if picked:
                form.set("vst_path", picked)
            continue
        if action == "browse_vst3" and allow_vst:
            picked = _browse_file(w, "Choose a VST3 Instrument (.vst3)", ".vst3")
            if picked:
                form.set("vst3_path", picked)
            continue
        if action == "open_vst3_ui" and allow_vst:
            open_vst3_controls(w, inst_name, form.get("vst3_path"), bool(form.get("vst3_use_native_gui")))
            continue
        if action == "save" and _save_instrument_fields(w, inst_name, form.values(), allow_vst):
            return


@_preserve_screen()
def run():
    w = core.getW()
    allow_vst = core.vst_supported()
    instruments = list(core.config["instruments"])
    in_devs = core.input.devices() if core.input is not None else []
    out_devs = core.output.devices() if core.output is not None else []

    in_sel = next((idx for idx, dev in enumerate(in_devs) if dev["index"] == core.input.device), 0) if in_devs else 0
    out_sel = next((idx for idx, dev in enumerate(out_devs) if dev["index"] == core.output.device), 0) if out_devs else 0

    form = vb.form(w, config={"label": "Settings", "adjacent_submit": False})
    form.add("section", "tab", choices=["Audio Devices", "Instruments"], value=0, label="Settings Section")

    # Tab 0: Audio Devices
    in_choices = [dev["name"].replace("&", "&&") for dev in in_devs] or ["No input devices"]
    out_choices = [dev["name"].replace("&", "&&") for dev in out_devs] or ["No output devices"]
    form.add("input_dev", "combo", value=in_sel, choices=in_choices, label="Audio Input", tab_page="Audio Devices")
    form.add("output_dev", "combo", value=out_sel, choices=out_choices, label="Audio Output", tab_page="Audio Devices")
    form.add("apply_audio", "button", label="Apply Audio Devices", tab_page="Audio Devices")

    # Tab 1: Instruments (SF2 / VST2 / VST3 for EVERY instrument)
    def sync_instrument_fields(frm, item):
        idx = int(item.get("value") or 0)
        if not 0 <= idx < len(instruments):
            return
        cfg = core.config["instruments"][instruments[idx]]
        frm.set("engine", _engine_to_index(cfg.get("active_engine", "sf2"), allow_vst))
        frm.set("sf2_path", cfg.get("sf2_path", ""))
        frm.set("sf2_id", str(cfg.get("sf2_id", 0)))
        if allow_vst:
            frm.set("vst_path", cfg.get("vst_path", ""))
            frm.set("vst3_path", cfg.get("vst3_path", ""))
            frm.set("vst3_use_native_gui", bool(cfg.get("vst3_use_native_gui", False)))

    if instruments:
        first_cfg = core.config["instruments"][instruments[0]]
        eng_choices = ENGINE_LABELS_DESKTOP if allow_vst else ["SoundFont (SF2)"]
        form.add("instrument", "combo", value=0, choices=[name.title() for name in instruments],
                 label="Instrument", callback=sync_instrument_fields, tab_page="Instruments")
        form.add("engine", "combo", value=_engine_to_index(first_cfg.get("active_engine", "sf2"), allow_vst),
                 choices=eng_choices, label="Sound Engine", tab_page="Instruments")
        form.add("sf2_path", "input", value=first_cfg.get("sf2_path", ""),
                 label="SoundFont File (.sf2)", tab_page="Instruments")
        form.add("browse_sf2", "button", label="Browse SoundFont...", tab_page="Instruments")
        form.add("sf2_id", "input", value=str(first_cfg.get("sf2_id", 0)),
                 number_only=True, label="Program ID (0-127)", tab_page="Instruments")
        if allow_vst:
            form.add("vst_path", "input", value=first_cfg.get("vst_path", ""),
                     label="VST2 Instrument DLL", tab_page="Instruments")
            form.add("browse_vst", "button", label="Browse VST2 DLL...", tab_page="Instruments")
            form.add("vst3_path", "input", value=first_cfg.get("vst3_path", ""),
                     label="VST3 Instrument (.vst3)", tab_page="Instruments")
            form.add("browse_vst3", "button", label="Browse VST3...", tab_page="Instruments")
            form.add("vst3_use_native_gui", "check", value=bool(first_cfg.get("vst3_use_native_gui", False)),
                     label="Use Native VST3 GUI (uncheck for vb.form)", tab_page="Instruments")
            form.add("open_vst3_ui", "button", label="Open VST3 Controls / GUI...", tab_page="Instruments")
        form.add("save_inst", "button", label="Save Instrument", tab_page="Instruments")

    form.add("close", "button", label="Close")

    while True:
        action = form.open()
        if action in (-1, "close"):
            return
        if action == "apply_audio":
            changed = []
            if in_devs:
                chosen_in = in_devs[form.get("input_dev")]
                if core.input.set_device(chosen_in["index"]):
                    changed.append(f"Input: {chosen_in['name']}")
                else:
                    vb.warning_box("Audio Input", f"Could not switch to {chosen_in['name']}.", window=w)
            if out_devs:
                chosen_out = out_devs[form.get("output_dev")]
                if core.output.set_device(chosen_out["index"]):
                    changed.append(f"Output: {chosen_out['name']}")
                else:
                    vb.warning_box("Audio Output", f"Could not switch to {chosen_out['name']}.", window=w)
            if changed:
                save()
                w.say("Applied " + ", ".join(changed))
        elif action == "browse_sf2":
            picked = _browse_file(w, "Choose a SoundFont (.sf2)", ".sf2")
            if picked:
                form.set("sf2_path", picked)
        elif action == "browse_vst" and allow_vst:
            picked = _browse_file(w, "Choose a VST2 Instrument (.dll)", ".dll")
            if picked:
                form.set("vst_path", picked)
        elif action == "browse_vst3" and allow_vst:
            picked = _browse_file(w, "Choose a VST3 Instrument (.vst3)", ".vst3")
            if picked:
                form.set("vst3_path", picked)
        elif action == "open_vst3_ui" and allow_vst and instruments:
            inst_name = instruments[int(form.get("instrument") or 0)]
            open_vst3_controls(w, inst_name, form.get("vst3_path"), bool(form.get("vst3_use_native_gui")))
        elif action == "save_inst" and instruments:
            inst_name = instruments[int(form.get("instrument") or 0)]
            _save_instrument_fields(w, inst_name, form.values(), allow_vst)
