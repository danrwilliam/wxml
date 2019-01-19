import wx
import wxml
from wxml import Ui, BindValue, Transformer, DynamicValue
import threading

class EveryOtherTransformer(Transformer):
    def to_widget(self, value):
        return value[::2]

@wxml.Ui('grid.xml')
class TestBed(wxml.ViewModel):
    text = BindValue('placeholder', name='placeholder', serialize=True)
    one_way = BindValue('start', name='one_way', serialize=True)
    message = 'Clear field'

    def pushed(self, evt):
        self.text.value = ''
        self.one_way.value = ''

if __name__ == "__main__":
    wxml.run(TestBed)