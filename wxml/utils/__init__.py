import os
from pathlib import Path
import re
import glob
import wx
import sys
import wxml.bind
from typing import Union

def convert_path(path: Union[str, os.PathLike]) -> str:
    if not isinstance(path, str):
        path = str(path)
    path = Path(re.sub(r'^([A-Z])\$', r'\1:', path))
    if not path.is_absolute():
        directory = Path(sys.modules['__main__'].__file__).parent
        path = directory / path
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
        p = convert_path(pattern)
        for g in p.parent.glob(p.name):
            self.Add(g, mask=mask)

    def Add(self, path, name=None, mask=None):
        path = convert_path(path)
        key = name or path.stem
        key = key.replace(' ', '_')

        if not hasattr(self, key):
            bmp = wx.Bitmap(wx.Image(str(path)))
            if mask is not None:
                mk = wx.Mask(bmp, mask)
                bmp.SetMask(mk)

            setattr(self, key, bmp)

    add = Add
    add_many = AddMany

class IconGroup(object):
    def AddMany(self, pattern):
        p = convert_path(pattern)
        for g in p.parent.glob(p.name):
            self.Add(g)

    def Add(self, path, name=None):
        path = convert_path(path)
        key = name or path.stem
        key = key.replace(' ', '_')

        if not hasattr(self, key):
            icon = wx.Icon(wx.Bitmap(wx.Image(str(path))))
            setattr(self, key, icon)

    add = Add
    add_many = AddMany

class IconBundleGroup(object):
    def AddMany(self, pattern):
        p = convert_path(pattern)
        for g in p.parent.glob(p.name):
            self.Add(g)

    def Add(self, path, name=None):
        path = convert_path(path)
        key = name or path.stem
        key = key.replace(' ', '_')

        if not hasattr(self, key):
            icon = wx.IconBundle(str(path))
            setattr(self, key, icon)


class NamedTupleSerializer(wxml.bind.BindValueSerializer):
    def __init__(self, class_obj):
        self._tuple_class = class_obj

    def deserialize(self, value):
        if value is None:
            return None
        else:
            return self._tuple_class(**value)

    def serialize(self, value):
        out =  dict(value._asdict())
        return out
