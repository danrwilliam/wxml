import sys
import os
import json
from typing import List, Dict, Optional, Callable, Type
import enum

import wx
import threading

from wxml.decorators import invoke_ui
from wxml.event import Event

DEBUG_UPDATE = False

class BindFailure(enum.Enum):
    Ignore = "Ignore"
    IgnoreFirst = "IgnoreFirst"
    Raise = "Raise"

class BindTarget(object):
    def __init__(self, obj, attr, transform=None, arguments=None):
        self.obj = obj
        self.attr = attr
        self.is_call = callable(self.attr)
        self.transformer = transform
        self.arguments = arguments or {}

        if self.is_call:
            bindings = [k for k, v in self.arguments.items() if isinstance(v, BindValue)]
            if len(bindings):
                self.bind_key = bindings[0]
            else:
                self.bind_key = None

    def __call__(self, value):
        if self.transformer is not None:
            value = self.transformer.to_widget(value)

        if self.is_call and self.bind_key is not None:
            self.arguments[self.bind_key] = value
            self.attr(**self.arguments)
        elif self.is_call and self.bind_key is None:
            self.attr(value)
        else:
            setattr(self.obj, self.attr, value)


class BindSource(object):
    def __init__(self, obj, attr, converter):
        self.obj = obj
        self.attr = attr
        self.converter = converter

    def receive(self):
        value = getattr(self.obj, self.attr)
        if self.converter is not None:
            value = self.converter.from_widget(value)
        return value

class DataStore:
    store = None
    _map = {}
    counter = 0

    @classmethod
    def _store_file(cls):
        filename = '%s.store.json' % os.path.splitext(os.path.basename(sys.modules['__main__'].__file__))[0]
        return filename

    @classmethod
    def _load(cls):
        if os.path.exists(cls._store_file()):
            try:
                with open(cls._store_file(), 'r') as fp:
                    cls.store = json.loads(fp.read())
            except Exception:
                cls.store = {}
        else:
            cls.store = {}

    @classmethod
    def save(cls):
        if len(cls._map) > 0:
            with open(cls._store_file(), 'w') as fp:
                state = {
                    k: b.value
                    for k, b in cls._map.items()
                }
                print(json.dumps(state, indent=4), file=fp)

    @classmethod
    def get(cls, bind):
        if cls.store is None:
            cls._load()

        if bind.name is None:
            name = 'value-%d' % cls.counter
            cls.counter += 1
        else:
            name = bind.name

        cls._map[name] = bind

        return cls.store.get(name)

class BindValue(object):
    def __init__(self, value, name=None, parent=None, serialize=False):
        if serialize is True and name is None:
            raise ValueError('BindValue: name cannot be None when serialize is True')

        self._value = value
        self.name: str = name

        self.serialize = serialize
        if self.serialize:
            stored_value = DataStore.get(self)
            if stored_value is not None:
                self._value = stored_value

        self.targets: List[BindTarget] = []
        self.sources: List[Callable] = {}
        self._previous = None

        self.value_changed = Event('value_changed')
        self.after_changed = Event('after_changed')

        for p in (parent or []):
            if isinstance(p, BindValue):
                p.add_target(self, 'value')
            elif isinstance(p, Transformer):
                p.bound.add_target(p, p.from_widget)

    def add_target(self, obj, attr, transform=None, arguments=None):
        self.targets.append(BindTarget(obj, attr, transform, arguments))

    def add_source(self, obj, event, attr, transform=None):
        source = BindSource(obj, attr, transform)
        source.obj.Bind(event, self.receive)
        self.sources[obj] = source

    def receive(self, evt):
        obj = evt.GetEventObject()
        value = self.sources[obj].receive()
        self._value = value
        self.update_target(source=obj)
        evt.Skip()

    def __str__(self):
        return str(self._value)

    def touch(self):
        """
            Fires an update of all targets without changing the value
        """
        self.update_target()

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, new):
        if self._value != new:
            self._previous = self._value
            self._value = new
            self.update_target()

    @invoke_ui
    def update_target(self, source=None):
        """
            Fires the value_changed event, updates all targets, and then
            fires the after_changed event.

            This will always be invoked on the UI thread.
        """
        self.value_changed(self._value)
        for target in self.targets:
            if target.obj != source:
                if DEBUG_UPDATE: print('  %s updating %s' % (self.name or self.__class__.__name__, target.obj))
                target(self._value)
        self.after_changed(self._value)


class ArrayBindValue(BindValue):
    def __init__(self, array: List, name=None, parent=None, serialize=False):
        super().__init__(array, name=name, parent=parent, serialize=serialize)
        self.index = BindValue(
            0,
            name='%s-sel' % name if name is not None else None,
            serialize=serialize
        )
        self.after_changed += self._set_index

    def _set_index(self, e):
        self.index.value = self.index.value
        self.index.update_target()

    @property
    def selected(self):
        return self.value[self.index.value]

    @selected.setter
    def selected(self, value):
        idx = max(0, self.value.index(value))
        self.index.value = idx

class DynamicValue(BindValue):
    def __init__(self, *listeners : List[BindValue], update : Callable=None, serialize=False):
        super().__init__('', serialize=False)
        self.action = update
        for l in listeners:
            l.add_target(self, self.update)
            for k, v in l.__dict__.items():
                if isinstance(v, BindValue):
                    v.add_target(self, self.update)


    def update(self, changed=None):
        value = self.action()
        self.value = value
        self.after_changed(self.value)

class DynamicArrayBindValue(DynamicValue):
    def __init__(self, *listeners : List[BindValue], update:Callable = None, changed_index=None):
        super().__init__(*listeners, update=update)
        self.index = BindValue(0)
        self.after_changed += self._set_index
        self.changed_index = changed_index

    def _set_index(self, e):
        self.index.value = self.index.value if self.changed_index is None else self.changed_index
        self.index.update_target()

    @property
    def selected(self):
        return self.value[self.index.value]

class Transformer(object):
    def __init__(self, bind_value: BindValue):
        self.bound = bind_value
    def to_widget(self, value):
        raise NotImplementedError()
    def from_widget(self, value):
        raise NotImplementedError

class ToWidgetGenericTransformer(Transformer):
    def __init__(self, bind_value, converter):
        super().__init__(bind_value)
        self.converter = converter

    def to_widget(self, value):
        return self.converter(value)


class FromWidgetGenericTransformer(Transformer):
    def __init__(self, bind_value, converter):
        super().__init__(bind_value)
        self.converter = converter

    def from_widget(self, value):
        return self.converter(value)