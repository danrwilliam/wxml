import wx
from wxml import GenericViewModel

label = 'Test'

def btn_press(evt):
    print('button pushed')

app = wx.App()
model = GenericViewModel('code.xml')
model.view.Show()
app.MainLoop()
