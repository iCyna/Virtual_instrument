import sys
import guitar, piano, drums, mte
import setting
import pyaudiogaming.system as system
frame=None
output=None
loop=True
recording=False
recorder=None
encoder=None
config={
	"input device": -1,
	"output device": -1,
	"instruments": {
		"piano": {
			"active_engine": "sf2",
			"sf2_path": system.match("sf2toolkit/GeneralUserGS-v1471.sf2"),
			"sf2_id": 0,
			"vst_path": "",
			"vst_chunk": ""
		},
		"guitar": {
			"active_engine": "sf2",
			"sf2_path": system.match("sf2toolkit/Acoustic Guitars JNv2.4.sf2"),
			"sf2_id": 3,
			"vst_path": "",
			"vst_chunk": ""
		},
		"drum": {
			"active_engine": "sf2",
			"sf2_path": system.match("sf2toolkit/GeneralUserGS-v1471.sf2"),
			"sf2_id": 0,
			"vst_path": "",
			"vst_chunk": ""
		},
		"bass": {
			"active_engine": "sf2",
			"sf2_path": system.match("sf2toolkit/GeneralUserGS-v1471.sf2"),
			"sf2_id": 32,
			"vst_path": "",
			"vst_chunk": ""
		},
		"electronic drum": {
			"active_engine": "sf2",
			"sf2_path": system.match("sf2toolkit/GeneralUserGS-v1471.sf2"),
			"sf2_id": 0,
			"vst_path": "",
			"vst_chunk": ""
		},
		"strings": {
			"active_engine": "sf2",
			"sf2_path": system.match("sf2toolkit/Strings.sf2"),
			"sf2_id": 48,
			"vst_path": "",
			"vst_chunk": ""
		},
		"synth": {
			"active_engine": "sf2",
			"sf2_path": system.match("sf2toolkit/Synth.sf2"),
			"sf2_id": 81,
			"vst_path": "",
			"vst_chunk": ""
		},
		"flute": {
			"active_engine": "sf2",
			"sf2_path": system.match("sf2toolkit/Flute.sf2"),
			"sf2_id": 73,
			"vst_path": "",
			"vst_chunk": ""
		}
	}
}

def save():
	global config
	import pyaudiogaming.file as pf
	f=pf.File(password="config key", encode=True, aes=True)
	config["input device"]=input.device
	config["output device"] = output.device
	once=False
	while 1:
		frame.frameUpdate()
		try:
			f.save(config, "settings.tl", mode="wb+", type="json")
			break
		except Exception as e:
			if not once: print(e); once=True
			continue

def exit():
	sys.exit

def getW():
	return frame

menus={
	"Piano": piano,
	"Guitar": guitar,
	"drums": drums,
	"Music Tracker Editor": mte,
	"Settings": setting,
}