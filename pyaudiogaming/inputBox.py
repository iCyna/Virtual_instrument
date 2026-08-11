# -*- coding: utf-8 -*-
# copyright 2025 belong ihcyna (Labubu)<phucnggo29@gmail.com>.
#input and message gui box and dialog functions

import wx
from . import buffer

def check():pass

INFO = wx.OK | wx.ICON_INFORMATION
ERROR = wx.OK | wx.ICON_ERROR
WARNING = wx.OK | wx.ICON_WARNING
QUESTION = wx.YES_NO | wx.ICON_QUESTION

def kbt(self, title, message, password=False, dir_dialog=False, file_dialog=False):
	"""Shows an input dialog and returns what was input by the user. Returns None when canceled."""
	check()
	ret = None
	buffer.names_window.append(title)
	if password:
		dlg = wx.PasswordEntryDialog(None, message, title)
	elif dir_dialog:
		dlg = wx.DirDialog(None, message, style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
	elif file_dialog:
		dlg = wx.FileDialog(None, message, wildcard="All files (*.*)|*.*", style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
	else:
		dlg = wx.TextEntryDialog(None, message, title)
	if dlg.ShowModal() == wx.ID_OK:
		if file_dialog or dir_dialog:
			ret = dlg.GetPath()
		else: ret = dlg.GetValue()
	dlg.Destroy()
	buffer.names_window.remove(title)
	return ret

def kbc(self, title, message, choices, multi=False):
	"""Shows a choice dialog and returns the selected choice(s). Returns None when canceled."""
	check()
	ret = None
	buffer.names_window.append(title)
	if multi:
		dlg = wx.MultiChoiceDialog(None, message, title, choices)
	else:
		dlg = wx.SingleChoiceDialog(None, message, title, choices)
	if dlg.ShowModal() == wx.ID_OK:
		if multi:
			ret = dlg.GetSelections()
		else:
			ret = dlg.GetSelection()
	dlg.Destroy()
	buffer.names_window.remove(title)
	return ret

def dialogMessage(title, message, style=INFO, y=True, n=False):
	"""Shows a message dialog and returns None."""
	check()
	buffer.names_window.append(title)
	dialog = wx.MessageDialog(None, message, title, style)
	result = dialog.ShowModal()
	dialog.Destroy()
	if result == wx.ID_YES:
		buffer.names_window.remove(title)
		return y
	else:
		buffer.names_window.remove(title)
		return n