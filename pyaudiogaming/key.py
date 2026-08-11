# -*- coding: utf-8 -*-
# copyright 2026 belong ihcyna (Labubu)<phucnggo29@gmail.com>.
#keys callback value

import secrets
import string
import random
from copy import copy
from enum import Enum, auto
from pygame.locals import *

class k(Enum):
	s = K_s
	a = K_a
	d = K_d
	f = K_f
	g = K_g
	h = K_h
	j = K_j
	k = K_k
	l = K_l
	q = K_q
	w = K_w
	e = K_e
	r = K_r
	t = K_t
	y = K_y
	u = K_u
	i = K_i
	o = K_o
	p = K_p
	z = K_z
	x = K_x
	c = K_c
	v = K_v
	b = K_b
	n = K_n
	m = K_m
	left = K_LEFT
	right = K_RIGHT
	up = K_UP
	down = K_DOWN
	home = K_HOME
	end = K_END
	page_up = K_PAGEUP
	page_down = K_PAGEDOWN
	enter = K_RETURN
	f1 = K_F1
	f2 = K_F2
	f3 = K_F3
	f4 = K_F4
	f5 = K_F5
	f6 = K_F6
	f7 = K_F7
	f8 = K_F8
	f9 = K_F9
	f10 = K_F10
	f11 = K_F11
	f12 = K_F12
	backspace = K_BACKSPACE
	jlit = K_DELETE
	lshift = K_LSHIFT
	rshift = K_RSHIFT
	shift = lshift or rshift
	lalt = K_LALT
	ralt = K_RALT
	lcontrol = K_LCTRL
	rcontrol = K_RCTRL
	space = K_SPACE
	tab = K_TAB
	exit = K_ESCAPE
	print_screen = K_PRINT
	sys_req = K_SYSREQ
	insert = K_INSERT
	menu = K_MENU
	capslock = K_CAPSLOCK
	left_bkt = K_LEFTBRACKET  # Phím [
	right_bkt = K_RIGHTBRACKET # Phím ]
	quote = K_QUOTE          
	backslash = K_BACKSLASH
	dot = K_PERIOD
	comma = K_COMMA            
	semicolon = K_SEMICOLON
	minus = K_MINUS           
	equal =K_EQUALS
	grave = K_BACKQUOTE        
	slash = K_SLASH 
	one=K_1
	two=K_2
	three=K_3
	four=K_4
	five=K_5
	six=K_6
	seven=K_7
	eight=K_8
	nine=K_9
	zero=K_0

	def eq(self, other):
		return self.value == other
	@property
	def int(self):
		return self.value
	def __eq__(self, other):
		if isinstance(other, int):
			return self.int == other
		return super().__eq__(other)

def token(min=4, max=12):
	from . import utils
	return utils.token(min, max)