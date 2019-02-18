import wx
import wxml



@wxml.Ui('view.xml')
class CustomListView(wxml.ViewModel):
    def __init__(self, *args, title='Default', **kwargs):
        self.title = title
        super().__init__(*args, **kwargs)

@wxml.Ui('example.xml')
class ExampleView(wxml.ViewModel):
    def initialize(self):
        self.option_check = wxml.BindValue(True)
        self.menu_tab = wxml.DynamicValue(update=self.get_tab, default=-1)
        self.selected_tab = wxml.BindValue(1)
        self.win_title = wxml.BindValue('title')

    def ready(self):
        self.view.vm = self

    def strapped(self, v):
        if v == 0:
            return 'First'
        elif v == 1:
            return 'Second'
        else:
            return 'None'

    def get_tab(self, *evt):
        if evt:
            evt = evt[0]
            new_value = evt.GetEventObject().HitTest(evt.GetPosition())[0]
        else:
            new_value = self.menu_tab.value

        self.selected_tab.value = new_value

        return new_value

@wxml.Ui('tree.xml')
class TreeView(wxml.ViewModel):
    def initialize(self):
        self.selections = wxml.BindValue([])

    def ready(self):
        for i in range(25):
            self.view.widgets['list'].AppendItem([str(i), str(i * i)], data=i)

    def open_context_menu(self, e):
        print('---open context menu')
        self.view.PopupMenu(self.view.widgets['context_menu'])

    def can_open(self, v):
        return len(v) == 1 and self.view.list.GetItemData(v[0]) == 4

if __name__ == "__main__":
    wxml.bind.DEBUG_UPDATE = True
    wxml.builder.DEBUG_BIND = True
    wxml.builder.DEBUG_EVENT = True
    wxml.builder.DEBUG_ERROR = True
    wxml.run(TreeView)#, inspect=True)