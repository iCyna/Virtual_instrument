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
	"guitar musical toolkit": system.match("sf2toolkit/Acoustic Guitars JNv2.4.sf2"),
	"piano musical toolkit": system.match("sf2toolkit/GeneralUserGS-v1471.sf2"),
	"drum musical toolkit": system.match("sf2toolkit/GeneralUserGS-v1471.sf2"),
	"guitar tools": 3,
}

def save():
	global config
	import pyaudiogaming.file as pf
	f=pf.File(password="config key", encode=True, aes=True)
	config["input device"]=input.device
	config["output device"] = output.device
	while 1:
		try:
			f.save(config, "settings.tl", mode="wb+", type="json")
			break
		except:continue

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