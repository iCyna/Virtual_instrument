import threading, pyaudiogaming.utils as utils
f,m = 4,5
token=utils.token(f, m)
count, much=0, 100
l=[]
v=True
def match(r):
	global l, count
	while v:
		count+=1
	l.remove(r); l.append(utils.token(f, m))

for r in range(0,6):
	l.append("...")
	threading.Thread(target=match, args=[r,], daemon=True).start()
try:
	while v:
		for i in l:
			if i==token: break;v=False
except:v=False
print(f"tried with {count} times: {token}")