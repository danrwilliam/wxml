import wx
import wxml

import wxml.builder

@wxml.Ui('components2.xml')
class TestVm(wxml.ViewModel):
    def initialize(self):
        self.password = wxml.BindValue('download')
        self.username = wxml.BindValue('crawl')

    def append_usr(self, v):
        return 'user: %s' % v
    def append_pwd(self, v):
        return 'pwd: %s' % v


wxml.run(TestVm)