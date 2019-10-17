import sys
import os
import json
from typing import List, Dict, Optional, Callable, Type, Any
import enum

import wx
import threading

from wxml.decorators import invoke_ui, block_ui
import wxml.builder
from wxml.event import Event
from wxml.attr import nested_getattr, nested_hasattr

DEBUG_UPDATE = False
DEBUG_STORE = False

class BindFailure(enum.Enum):
    Ignore = "Ignore"
    IgnoreFirst = "IgnoreFirst"
    Raise = "Raise"

class BindTarget(object):
    def __init__(self, obj, attr, transform : Optional['Transformer'] = None,
                 arguments : Optional[Dict[str, Any]] = None):
        self.obj = obj
        self.attr = attr
        self.is_call = callable(self.attr)
        self.transformer = transform
        self.arguments = arguments or {}

        if self.is_call:
            self._bindings = [(k, v) for k, v in self.arguments.items() if isinstance(v, BindValue)]
        else:
            self._bindings = None

    def __call__(self, value):
        if self.transformer is not None:
            value = self.transformer.to_widget(value)

        if DEBUG_UPDATE:
            print('   - %s.%s updating with: %s'  % (
                wxml.builder.UiBuilder.debug_names.get(self.obj, self.obj),
                self.attr,
                value)
            )

        if self.is_call and self._bindings is not None:
            for idx, bind in self._bindings:
                self.arguments[idx] = bind.value
            self.attr(**self.arguments)
        elif self.is_call and self._bindings is None:
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
    """
        Handler for serializing/deserializing persisted data.
    """

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
                    data = json.loads(fp.read())
                    cls.store = data
                    if DEBUG_STORE:
                        print('Store File loaded from %s' % cls._store_file())
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
        val = cls.store.get(name)

        if DEBUG_STORE:
            print('store.get(%s) = %s' % (name, val))

        return val

class BindValue(object):
    def __init__(self, value, name=None, parent=None, serialize=False, trace=False):
        if serialize is True and name is None:
            raise ValueError('BindValue: name cannot be None when serialize is True')

        self._value = value
        self.name: str = name
        self._trace = trace

        self.serialize = serialize
        if self.serialize:
            stored_value = DataStore.get(self)
            if stored_value is not None:
                self._value = stored_value

        self.targets: List[BindTarget] = []
        self.sources: List[Callable] = {}
        self._previous = None

        # Fired when the value has changed, before updating targets
        self.value_changed = Event('value_changed')
        # Fired after updating targets
        self.after_changed = Event('after_changed')
        # Fired when setting the value, even if it is not changed
        self.value_set = Event('value_set')

        for p in (parent or []):
            if isinstance(p, BindValue):
                p.add_target(self, 'value')
            elif isinstance(p, Transformer):
                p.bound.add_target(p, p.from_widget)

    def add_target(self, obj, attr, transform=None, arguments=None):
        self.targets.append(BindTarget(obj, attr, transform, arguments))

    def add_target2(self, obj, attr, transform=None, **arguments):
        """
            shortcut method for add_target

            if transform is a callable, it will be wrapped into
            a ToWidgetGenericTransformer.

            arguments can be given as kwargs instead of passed as a
            dictionary
        """

        if callable(transform) and not isinstance(transform, wxml.Transformer):
            transform = ToWidgetGenericTransformer(self, transform)
        self.add_target(obj, attr, transform, arguments)

    def add_source(self, obj, event, attr, transform=None, bind_to=None, arguments=None):
        source = BindSource(obj, attr, transform, arguments)
        if bind_to:
            source.obj.Bind(event, self.receive, bind_to)
        else:
            source.obj.Bind(event, self.receive)
        self.sources[obj] = source

    def receive(self, evt):
        obj = evt.GetEventObject()
        value = self.sources[obj].receive()
        self._set(value, source=obj)
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

    def _set(self, new, source=None):
        if self._trace:
            print(' %s.value set (new=%s) (old=%s) (changed=%s)' % (
                self.name or self.__class__.__name__, new, self._value, new != self._value
            ))

        self.value_set(new)
        if self._value != new:
            self._previous = self._value
            self._value = new
            self.update_target(source=source)

    @value.setter
    def value(self, new):
        self._set(new)

    @block_ui
    def update_target(self, source=None):
        """
            Fires the value_changed event, updates all targets (except the source),
            and then fires the after_changed event.

            This will always be invoked on the UI thread.
        """
        self.value_changed(self._value)

        if DEBUG_UPDATE or self._trace:
            print(' %s update_target with %s (source: %s)' % (
                self.name or self.__class__.__name__, self._value, source
            ))

        for target in self.targets:
            if target.obj != source:
                target(self._value)

        self.after_changed(self._value)


class ArrayBindValue(BindValue):
    def __init__(self, array: List, name=None, parent=None, serialize=False, trace=False, preserve=True):
        super().__init__(array, name=name, parent=parent, serialize=serialize, trace=trace)
        self.preserve = preserve
        self.index = BindValue(
            0,
            name='%s-sel' % name if name is not None else None,
            serialize=serialize,
            trace=trace
        )
        self.item = wxml.DynamicValue(
            self,
            update=self._update_selection,
            name='%s-item' % name if name is not None else None,
            trace=trace
        )
        self.after_changed += self._set_index

    def _set_index(self, e):
        if not self.preserve:
            return

        # at this point, the item has already been changed
        # so we need to use the previous item
        prev = self.item._previous

        if prev in self.value:
            new_idx = self.value.index(prev)
            if new_idx == self.index.value:
                self.index.touch()
            else:
                self.index.value = new_idx
        else:
            self.index.value = max(0, min(len(self.value), self.index.value))

    def _update_selection(self):
        return self.value[self.index.value]

class DynamicValue(BindValue):
    """
        Creating a DynamicValue without a update method will always cause
        targets to be updated. This can be used as a way to group together
        bind values to be listened to.
    """
    def __init__(self, *listeners : List[BindValue], update : Callable=None, default='', name=None, trace=False):
        super().__init__(default, serialize=False, name=name, trace=trace)
        self.action = update or self._noop
        for l in listeners:
            if isinstance(l, BindValue):
                l.add_target(self, self.update)

            # also subscribe to any bind values contained in this listener
            for k, v in l.__dict__.items():
                if isinstance(v, BindValue):
                    v.add_target(self, self.update)

        self.update()

    def _noop(self, changed=None):
        return not self._value

    def update(self, changed=None):
        value = self.action()
        self.value = value

    def push_event(self, event):
        value = self.action(event)
        self._value = value
        self.update_target()

class DynamicArrayBindValue(DynamicValue):
    """
        listeners: list of BindValue's that will cause this to update
        update   : the method that will get the new value
        name     : identifier useful for debugging
        trace    : additional tracing
        preserve : when the value changes, attempt to preserve
                   the selected item, otherwise the index is
                   constrained to the new contents
    """

    def __init__(self, *listeners : List[BindValue], update:Callable = None,
                 name:str=None, trace=False, preserve=True):
        super().__init__(*listeners, name=name, update=update, trace=trace)
        self.preserve = preserve
        self.index = BindValue(0, name='%s.index' % name if name is not None else None, trace=trace)
        self.item = DynamicValue(
            self,
            update=self._update_selected,
            trace=trace,
            name='%s.item' % name if name is not None else None
        )
        self.after_changed += self._set_index
        self.index.touch()

    def _update_selected(self):
        return self.value[self.index.value]

    def _set_index(self, e):
        if not self.preserve:
            return

        # at this point, the item has already been changed
        # so we need to use the previous item
        prev = self.item._previous

        if prev in self.value:
            new_idx = self.value.index(prev)
            if new_idx == self.index.value:
                self.index.touch()
            else:
                self.index.value = new_idx
        else:
            self.index.value = max(0, min(len(self.value), self.index.value))

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
