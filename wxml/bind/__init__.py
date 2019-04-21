import sys
import os
import json
from typing import List, Dict, Optional, Callable, Type
import enum

import wx
import threading

from wxml.decorators import invoke_ui, block_ui
import wxml.builder
from wxml.event import Event
from wxml.attr import nested_getattr, nested_hasattr

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

        if DEBUG_UPDATE:
            print('   - %s.%s updating with: %s'  % (
                wxml.builder.UiBuilder.debug_names.get(self.obj, self.obj),
                self.attr,
                value)
            )

        if self.is_call and self.bind_key is not None:
            self.arguments[self.bind_key] = value
            self.attr(**self.arguments)
        elif self.is_call and self.bind_key is None:
            self.attr(value)
        else:
            setattr(self.obj, self.attr, value)


class BindSource(object):
    def __init__(self, obj, attr, converter=None, arguments=None):
        self.obj = obj
        self.attr = attr
        self.is_call = callable(self.attr)
        self.converter = converter
        self.arguments = arguments or {}

    def receive(self):
        if self.is_call:
            value = self.attr(**self.arguments)
        else:
            value = getattr(self.obj, self.attr)

        if self.converter is not None:
            value = self.converter.from_widget(value)

        return value

class DataStore:
    Directory = ''
    store = None
    _map = {}
    counter = 0

    @classmethod
    def _store_file(cls):
        filename = os.path.join(DataStore.Directory, '%s.store.json' % os.path.splitext(os.path.basename(sys.modules['__main__'].__file__))[0])
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

    def add_source(self, obj, event, attr, transform=None, bind_to=None, arguments=None):
        source = BindSource(obj, attr, transform, arguments)
        if bind_to:
            b = source.obj.Bind(event, self.receive, bind_to)
        else:
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

    @block_ui
    def update_target(self, source=None):
        """
            Fires the value_changed event, updates all targets, and then
            fires the after_changed event.

            This will always be invoked on the UI thread.
        """
        self.value_changed(self._value)

        if DEBUG_UPDATE:
            print(' %s update_target with %s (source: %s)' % (
                self.name or self.__class__.__name__, self._value, source
            ))

        for target in self.targets:
            if target.obj != source:
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
        self.item = wxml.DynamicValue(self, update=self._update_selection)
        self.after_changed += self._set_index

    def _set_index(self, e):
        self.index.value = self.index.value
        self.index.update_target()

    def _update_selection(self):
        return self.value[self.index.value]

    @property
    def selected(self):
        return self.value[self.index.value]

    @selected.setter
    def selected(self, value):
        idx = max(0, self.value.index(value))
        self.index.value = idx

class DynamicValue(BindValue):
    def __init__(self, *listeners : List[BindValue], update : Callable=None, default='', name=None):
        super().__init__(default, serialize=False, name=name)
        self.action = update or self._noop
        for l in listeners:
            if isinstance(l, BindValue):
                l.add_target(self, self.update)

            for k, v in l.__dict__.items():
                if isinstance(v, BindValue):
                    v.add_target(self, self.update)

    def _noop(self, changed=None):
        pass

    def update(self, changed=None):
        value = self.action()
        self._value = value
        self.update_target()

    def push_event(self, event):
        value = self.action(event)
        self._value = value
        self.update_target()

class DynamicArrayBindValue(DynamicValue):
    def __init__(self, *listeners : List[BindValue], update:Callable = None, changed_index=None,
                 name:str=None):
        super().__init__(*listeners, name=name, update=update)
        self.index = BindValue(0, name='%s.index' % name if name is not None else None)
        self.item = DynamicValue(self, update=self._update_selected)
        self.after_changed += self._set_index
        self.changed_index = changed_index

    def _update_selected(self):
        return self.value[self.index.value]

    def _set_index(self, e):
        self.index.value = self.index.value if self.changed_index is None else self.changed_index
        self.index.update_target()

    @property
    def selected(self):
        if self.index.value < len(self.value):
            return self.value[self.index.value]
        else:
            return None

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

class ToWidgetProperty(ToWidgetGenericTransformer):
    def __init__(self, bind_value, prop_name, conv=str):
        self._property = prop_name
        self._conv = conv
        super().__init__(bind_value, self.get_property)

    def get_property(self, value):
        attribute = nested_getattr(self._property, root=self.bound.value)
        if attribute is None:
            val = ''
        elif callable(attribute):
            val = attribute()
        else:
            val = attribute

        return self._conv(val)