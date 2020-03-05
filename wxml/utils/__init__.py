import os
import re
import glob
import wx
import sys
import wxml.bind

def convert_path(path):
    path = re.sub(r'^([A-Z])\$', r'\1:', path)
    if not os.path.isabs(path):
        path = os.path.join(os.path.dirname(sys.modules['__main__'].__file__), path)
    return path

class Resources(object):
    @staticmethod
    def Add(self, name, item):
        setattr(Resources, name, item)

class ImgGroup(object):
    def __init__(self):
        self._map = {}
        self._loaded = {}

    def AddMany(self, pattern, mask=None):
        for g in glob.glob(convert_path(pattern)):
            self.Add(g, mask=mask)

    def Add(self, path, name=None, mask=None):
        path = convert_path(path)
        key = name or os.path.splitext(os.path.basename(path))[0]
        key = key.replace(' ', '_')

        if not hasattr(self, key):
            bmp = wx.Bitmap(path)
            if mask is not None:
                mk = wx.Mask(bmp, mask)
                bmp.SetMask(mk)

            setattr(self, key, bmp)

    add = Add
    add_many = AddMany

class IconGroup(object):
    def AddMany(self, pattern):
        for g in glob.glob(convert_path(pattern)):
            self.Add(g)

    def Add(self, path, name=None):
        path = convert_path(path)
        key = name or os.path.splitext(os.path.basename(path))[0]
        key = key.replace(' ', '_')

        if not hasattr(self, key):
            icon = ico = wx.Icon(path)
            setattr(self, key, icon)

    add = Add
    add_many = AddMany

class NamedTupleSerializer(wxml.bind.BindValueSerializer):
    def __init__(self, klass_obj):
        self._klass = klass_obj

    def deserialize(self, value):
        if value is None:
            return None
        else:
            return self._klass(**value)

    def serialize(self, value):
        out =  dict(value._asdict())
        return out
