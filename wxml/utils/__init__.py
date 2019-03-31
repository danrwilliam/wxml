import os
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

    def AddMany(self, pattern):
        for g in glob.glob(pattern):
            self.Add(g)

    def Add(self, path, name=None):
        key = name or os.path.splitext(os.path.basename(path))[0]
        setattr(self, key, wx.Bitmap(path))

    add = Add
    add_many = AddMany