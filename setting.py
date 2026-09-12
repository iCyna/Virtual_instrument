import pyaudiogaming.menu as menu
import core
from pyaudiogaming import vb
from pyaudiogaming.inputBox import kbt
import pyaudiogaming.system as system

def open_instrument_settings(inst_name):
    w = core.getW()
    m = menu.menu()
    inst_data = core.config["instruments"][inst_name]
    
    while True:
        m.init(w, f"{inst_name.capitalize()} Settings")
        m.append(f"Active Engine: {inst_data['active_engine'].upper()}")
        m.append(f"SF2 Path: {inst_data['sf2_path']}")
        m.append(f"SF2 Program ID: {inst_data['sf2_id']}")
        m.append(f"VST Plugin Path: {inst_data['vst_path']}")
        m.append("Back")
        
        m.open()
        
        while True:
            w.frameUpdate()
            s = m.frameUpdate()
            if s is None:
                continue
            if s == -1 or s == 4:
                return
            
            if s == 0:
                new_engine = "vst" if inst_data["active_engine"] == "sf2" else "sf2"
                inst_data["active_engine"] = new_engine
                core.save()
                break
            elif s == 1:
                fname = kbt(None, f"Select SF2 for {inst_name}", "", file_dialog=True)
                if fname:
                    inst_data["sf2_path"] = fname
                    core.save()
                break
            elif s == 2:
                val = kbt(None, f"Enter SF2 Program ID for {inst_name}", "")
                if val and val.isdigit():
                    inst_data["sf2_id"] = int(val)
                    core.save()
                break
            elif s == 3:
                fname = kbt(None, f"Select VST Plugin (.dll) for {inst_name}", "", file_dialog=True)
                if fname:
                    inst_data["vst_path"] = fname
                    core.save()
                break

def run():
    inputs = core.input.get_device_names()
    outputs = core.output.get_device_names()
    dec_index = 0
    m = menu.menu()
    w = core.getW()
    
    instruments = list(core.config["instruments"].keys())
    
    while True:
        m.init(w, "Settings Menu")
        m.append("Input device: %s" % core.input.find_device_by_id(core.input.device))
        m.append("Output device: %s" % core.output.find_device_by_id(core.output.device))
        
        for inst in instruments:
            m.append(f"{inst.capitalize()} Settings")
            
        m.append("Back")
        m.open()
        
        while True:
            w.frameUpdate()
            if w.keyPressed("f5"):
                dec_index = 0
                inputs = core.input.get_device_names()
                outputs = core.output.get_device_names()
                w.say(f"{len(inputs)}, {len(outputs)}")
            
            s = m.getCursorPos()
            
            if w.keyPressed("left") and s < 2:
                dec_index -= 1
                if dec_index < 0:
                    dec_index = len(inputs) - 1 if s == 0 else len(outputs) - 1
                if s == 0:
                    core.input.device = inputs[dec_index]
                    m.modify(s, "Input device: %s" % inputs[dec_index])
                    w.say(core.input.find_device_by_id(core.input.device))
                else:
                    core.output.device = outputs[dec_index]
                    m.modify(s, "Output device: %s" % outputs[dec_index])
                    w.say(core.output.find_device_by_id(core.output.device))
                core.save()
                
            if w.keyPressed("right") and s < 2:
                dec_index += 1
                if s == 0:
                    if dec_index >= len(inputs):
                        dec_index = 0
                    core.input.device = inputs[dec_index]
                    m.modify(s, "Input device: %s" % inputs[dec_index])
                    w.say(core.input.find_device_by_id(core.input.device))
                else:
                    if dec_index >= len(outputs):
                        dec_index = 0
                    core.output.device = outputs[dec_index]
                    m.modify(s, "Output device: %s" % outputs[dec_index])
                    w.say(core.output.find_device_by_id(core.output.device))
                core.save()
                
            s_action = m.frameUpdate()
            if s_action is None:
                continue
            if s_action == -1 or s_action == len(m.items) - 1:
                return
            
            if 2 <= s_action < 2 + len(instruments):
                inst_name = instruments[s_action - 2]
                open_instrument_settings(inst_name)
                break