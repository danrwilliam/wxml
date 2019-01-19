class Event(set):
    """
        Class for setting up callbacks
    """

    def __init__(self, name=None, fire_once=False):
        super(Event, self).__init__()
        self.fire_once = fire_once
        self.name = name or 'Event'

    def __iadd__(self, val):
        self.add(val)
        return self

    def __isub__(self, val):
        self.remove(val)
        return self

    def __call__(self, *args):
        self.fire(*args)

    def fire(self, *evt):
        for s in self:
            try:
                s(*evt)
            except TypeError as ex:
                raise
            if self.fire_once:
                self.clear()