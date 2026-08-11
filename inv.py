# init app
from pyaudiogaming.window import *

w=Window()
w.init(654, 543, "instrument-virtual gaming toolkit")
import master
master.load(w)
master.mainmenu()