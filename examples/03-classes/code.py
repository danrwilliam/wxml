import wx
from wxml import ViewModel, Ui

@Ui('code.xml')
class View(ViewModel):
    label = 'Test'
    num = 0

    def btn_press(self, evt):
        self.num += 1
        print('button pushed %d' % self.num)

if __name__ == "__main__":
    app = wx.App()
    model = View()
    model.view.Show(True)
    app.MainLoop()
