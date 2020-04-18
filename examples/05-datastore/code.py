import wx
from wxml import ViewModel, Ui, BindValue, DynamicValue
from wxml.bind import DataStore

@Ui('code.xml')
class View(ViewModel):

    def initialize(self):
        """
            initialize is called before constructing the UI.
            this is where bind values should be created, along
            with anything else used by the construction process.
        """
        self.label = 'Test'
        # a bind value that is serialized must also specify a name
        self.num = BindValue(0, serialize=True, name='num')
        self.dynamic = DynamicValue(self.num, update=self.dynamic_label)
        self.entry = BindValue('', serialize=True, name='entry')

    def dynamic_label(self):
        return 'pressed %d' % self.num.value

    def btn_press(self, evt):
        self.num.value += 1

if __name__ == "__main__":
    app = wx.App()
    model = View()
    model.view.Show(True)
    app.MainLoop()

    # saving the data store must happen after the
    # UI loop has completed
    DataStore.save()
