import wx
from wxml import GenericViewModel


def btn_press(evt):
    print('button pushed')


app = wx.App()
model = GenericViewModel('code.xml')
model.view.Show()
app.MainLoop()
