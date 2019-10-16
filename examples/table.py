import wxml


@wxml.Ui('table.xml')
class TableView(wxml.ViewModel):
    def initialize(self):
        self.data = [
            [wxml.BindValue('HAL'), wxml.BindValue('Discovery')],
            [wxml.BindValue('Keir'), wxml.BindValue('Unknown')]
        ]
        self.name_entry = wxml.BindValue('')
        self.location_entry = wxml.BindValue('')
        self.selection = wxml.BindValue(None)

        self.selection.after_changed += self.update_entry

    def ready(self):
        ctrl = self.view.widgets['list']

        for r, d in enumerate(self.data):
            ctrl.AppendItem(['' for i in d])
            for c, b in enumerate(d):
                b.add_target(ctrl, ctrl.SetTextValue, None, {'value': b, 'row': r, 'col': c})
                b.touch()

    def commit(self, evt):
        if self.selection.value is not None:
            self.data[self.selection.value][0].value = self.name_entry.value
            self.data[self.selection.value][1].value = self.location_entry.value

    def update_entry(self, v):
        self.name_entry.value = self.data[self.selection.value][0].value
        self.location_entry.value = self.data[self.selection.value][1].value



if __name__ == "__main__":
    wxml.run(TableView)