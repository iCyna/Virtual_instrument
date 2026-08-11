# -*- coding: utf-8 -*-
# copyright 2025 belong ihcyna (Labubu)<phucnggo29@gmail.com>.
#wx gui app of pyaudiogaming

import wx


class Window:
    def __init__(self, title="wxPython App", size=(400, 300)):
        self.app = wx.App(False)
        self.frame = wx.Frame(None, title=title, size=size)
        self.panel = wx.Panel(self.frame)
        self.elements = {}
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.panel.SetSizer(self.sizer)

    def button(self, label, handler, font=None, color=None):
        """Thêm một nút bấm vào giao diện."""
        button = wx.Button(self.panel, label=label)
        if font:
            button.SetFont(font)
        if color:
            button.SetForegroundColour(color)
        button.Bind(wx.EVT_BUTTON, handler)
        self.sizer.Add(button, 0, wx.ALL | wx.EXPAND, 5)
        self.elements[label] = button
        return button

    def print(self, text, font=None, color=None):
        """Thêm một dòng chữ hiển thị."""
        static_text = wx.StaticText(self.panel, label=text)
        if font:
            static_text.SetFont(font)
        if color:
            static_text.SetForegroundColour(color)
        self.sizer.Add(static_text, 0, wx.ALL, 5)
        self.elements[text] = static_text
        return static_text

    def input(self, label, value="", font=None):
        """Thêm một ô nhập liệu với nhãn."""
        box_sizer = wx.BoxSizer(wx.HORIZONTAL)
        static_text = wx.StaticText(self.panel, label=label)
        text_ctrl = wx.TextCtrl(self.panel, value=value)
        if font:
            static_text.SetFont(font)
            text_ctrl.SetFont(font)
        box_sizer.Add(static_text, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        box_sizer.Add(text_ctrl, 1, wx.ALL | wx.EXPAND, 5)
        self.sizer.Add(box_sizer, 0, wx.EXPAND)
        self.elements[label] = text_ctrl
        return text_ctrl

    def remove(self, label):
        """Xóa một thành phần khỏi giao diện."""
        if label in self.elements:
            element = self.elements[label]
            element.Destroy()
            del self.elements[label]
            self.sizer.Layout()
        else:
            print(f"Không tìm thấy thành phần có nhãn: {label}")

    def edit(self, label, font=None, color=None):
        """Thay đổi kiểu của một thành phần đã thêm."""
        element = self.elements.get(label)
        if not element:
            print(f"Không tìm thấy thành phần có nhãn: {label}")
            return
        if font:
            element.SetFont(font)
        if color:
            element.SetForegroundColour(color)

    def frameUpdate(self):
        """Hiển thị giao diện."""
        self.frame.Show()
        self.app.MainLoop()
