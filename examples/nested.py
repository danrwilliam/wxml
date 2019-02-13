import wx
import wxml

wxml.builder.DEBUG_TIME = True

@wxml.Ui('view.xml')
class CustomListView(wxml.ViewModel):
    def __init__(self, *args, title='Default', **kwargs):
        self.title = title
        super().__init__(*args, **kwargs)

@wxml.Ui('example.xml')
class ExampleView(wxml.ViewModel):
    pass

if __name__ == "__main__":
    wxml.run(ExampleView)