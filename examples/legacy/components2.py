import wx
import wxml
from wxml.builder import UiBuilder
import wxml.builder

@wxml.Control
class StaticTextEx(wx.StaticText):
    pass

@wxml.Ui('components2.xml')
class TestVm(wxml.ViewModel):
    def initialize(self):
        self.password = wxml.BindValue('download')
        self.username = wxml.BindValue('crawl')
        self.enabled = wxml.BindValue(False)

    def ready(self):
        sizer = self.view.widgets['container'].Sizer
        s = StaticTextEx(self.view.widgets['container'], label='testing')

    def append_usr(self, v):
        return 'user: %s' % v
    def append_pwd(self, v):
        return 'pwd: %s' % self.hide(v)

    def hide(self, v):
        return '*' * len(v)

if __name__ == "__main__":
    # wxml.builder.DEBUG_COMPILE=1
    # wxml.builder.DEBUG_ATTR=1
    # wxml.builder.DEBUG_EVAL=1
    wxml.run(TestVm, inspect=0)
