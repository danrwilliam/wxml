"""
    Shows how to create menus with dynamically enabled menus and menu items,
    as well as binding check and radio items.
"""

import wx
import wxml
import wx.lib.agw.shortcuteditor

from enum import Enum


class MediaType(Enum):
    Movie = 0
    TV = 1
    Documentary = 2
    Music = 3

@wxml.Ui('menu_change.xml')
class View(wxml.ViewModel):
    def initialize(self):
        self.check_one = wxml.BindValue(True)
        self.check_two = wxml.BindValue(False)

        self.choices = [v.name for v in MediaType.__members__.values()]
        self.enum = wxml.BindValue(MediaType.Movie)
        self.enum.after_changed += self.new_value
        self.no_choice = wxml.BindValue('Third')
        self.action_choice = wxml.BindValue('')

    def ready(self):
        print(self.view.accel_table)

    def new_value(self, v):
        #print(self.enum.value, self.enum.value.__class__)
        pass

    def enum2name(self, v : MediaType) -> str:
        return v.name

    def name2enum(self, v : str) -> MediaType:
        return MediaType[v]

    def btn_pressed(self, evt):
        print('btn_pressed')

    def show_context(self, evt):
        self.view.PopupMenu(self.view.widgets['context'])

    def action(self, evt):
        self.action_choice.value = 'Action fired'

    def action2(self, evt):
        self.action_choice.value = 'Action2 fired'

    def edit_cuts(self, evt):
        dlg = wx.lib.agw.shortcuteditor.ShortcutEditor(self.view)
        dlg.FromAcceleratorTable([('action %d', *k) for k in self.view.accel_table])
        dlg.ShowModal()

if __name__ == "__main__":
    #wxml.builder.DEBUG_ERROR = True
    wxml.builder.DEBUG_EVENT = True
    #wxml.builder.DEBUG_COMPILE = True
    #wxml.builder.DEBUG_ATTR = True
    #wxml.builder.DEBUG_BIND = True
    #wxml.bind.DEBUG_UPDATE = True

    wxml.run(View, inspect=False)