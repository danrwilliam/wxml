import wx
import wxml
from wxml import Ui, BindValue, Transformer, DynamicValue
import time

class EveryOtherTransformer(Transformer):
    def to_widget(self, value):
        return value[::2]

@wxml.invoke_ui
def bg_handler(exc, exc_info):
    import traceback, sys

    tb = traceback.format_exception(*exc_info)
    msg  = '%s\n\n%s' % (exc, '\n'.join(tb))

    dlg = wx.MessageDialog(
        None, msg, '%s caught on background thread' % exc.__class__.__name__,
        style=wx.ICON_ERROR
    )
    dlg.ShowModal()
    dlg.Destroy()

@wxml.Ui('grid.xml')
class TestBed(wxml.ViewModel):
    text = BindValue('placeholder', name='placeholder', serialize=True)
    one_way = BindValue('start', name='one_way', serialize=True)
    message = 'Clear field'

    def pushed(self, evt):
        self.text.value = ''
        self.one_way.value = ''

    @wxml.background
    def start_task(self, evt):
        wxml.background.handler.clear()

        self.text.value = 'Starting task'

        for i in range(5):
            time.sleep(1)
            self.text.value = 'Task running for %d seconds' % (i + 1)

        val = self.show_dialog()

        self.text.value = 'show_dialog() returned %s' % val

        time.sleep(2)

        self.text.value = 'Task has completed'

    import threading

    @wxml.block_ui
    def show_dialog(self):
        dlg = wx.MessageDialog(self.view,
            'This is a message'
        )
        dlg.ShowModal()
        dlg.Destroy()
        return 2

    @wxml.background
    def exception_task(self, evt):
        wxml.background.handler.clear()
        self.text.value = 'Starting exception task'
        time.sleep(3)
        raise Exception('Throwing an exception')

    @wxml.background
    def exception_task_handled(self, evt):
        wxml.background.handler += bg_handler

        self.text.value = 'Waiting for 2 seconds'
        time.sleep(2)
        x = y + 10



if __name__ == "__main__":
    wxml.run(TestBed)