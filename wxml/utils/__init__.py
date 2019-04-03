import os
import re
import glob
import wx

class Resources(object):
    @staticmethod
    def Add(self, name, item):
        setattr(Resources, name, item)

class ImgGroup(object):
    def __init__(self):
        self._map = {}
        self._loaded = {}

    def AddMany(self, pattern, mask=None):
        for g in glob.glob(pattern):
            self.Add(g, mask=mask)

    def Add(self, path, name=None, mask=None):
        path = re.sub(r'^([A-Z])\$', r'\1:', path)
        key = name or os.path.splitext(os.path.basename(path))[0]
        key = key.replace(' ', '_')

        bmp = wx.Bitmap(path)
        if mask is not None:
            mk = wx.Mask(bmp, mask)
            bmp.SetMask(mk)

        setattr(self, key, bmp)

    add = Add
    add_many = AddMany

class IconGroup(object):
    def AddMany(self, pattern):
        for g in glob.glob(pattern):
            self.Add(g)

    def Add(self, path, name=None):
        path = re.sub(r'^([A-Z])\$', r'\1:', path)
        key = name or os.path.splitext(os.path.basename(path))[0]
        key = key.replace(' ', '_')

        icon = ico = wx.Icon(path)

        setattr(self, key, icon)

    add = Add
    add_many = AddMany