import wx
import wxml

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

        self.choices = [v for k, v in MediaType.__members__.items()]
        self.enum = wxml.BindValue(MediaType.Movie)

    def show_context(self, evt):
        print('show_context')
        self.view.PopupMenu(self.view.widgets['context'])

if __name__ == "__main__":
    # wxml.builder.DEBUG_ERROR = True
    # # wxml.builder.DEBUG_EVENT = True
    # wxml.builder.DEBUG_COMPILE = True
    # # wxml.builder.DEBUG_ATTR = True
    # wxml.builder.DEBUG_BIND = True
    # wxml.bind.DEBUG_UPDATE = True
    wxml.run(View)