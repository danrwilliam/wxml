import wxml

@wxml.Ui('array.xml')
class ArrayView(wxml.ViewModel):
    def initialize(self):
        self.first = wxml.ArrayBindValue([
            'first', 'second', 'third', 'fourth'
        ], name='first')

        self.second = wxml.DynamicArrayBindValue(self.first, update=self.get_second)

        self.first_times = wxml.BindValue(0)
        self.first_changed = wxml.BindValue(0)
        self.first_set = wxml.BindValue(0)

        self.first.index.after_changed += self.increment_first
        self.first.index.value_changed += self.increment_first_changed
        self.first.index.value_set += self.increment_first_set

        self.second_times = wxml.BindValue(0)
        self.second_changed = wxml.BindValue(0)
        self.second_set = wxml.BindValue(0)
        self.second.index.after_changed += self.increment_second
        self.second.index.value_changed += self.increment_second_changed
        self.second.index.value_set += self.increment_second_set

    def get_second(self):
        return [v.upper() for v in self.first.value]

    def reverse_first(self, evt):
        self.first.value = self.first.value[::-1]

    def increment_first(self, v):
        self.first_times.value += 1

    def increment_first_changed(self, v):
        self.first_changed.value += 1

    def increment_first_set(self, v):
        self.first_set.value += 1

    def increment_second(self, v):
        self.second_times.value += 1

    def increment_second_changed(self, v):
        self.second_changed.value += 1

    def increment_second_set(self, v):
        self.second_set.value += 1

if __name__ == "__main__":
    wxml.builder.DEBUG_ERROR=1
    wxml.run(ArrayView)