import sys
import os
import json
from typing import List, Dict, Optional, Callable, Type, Any, Union
import enum

import wx
import threading

from wxml.decorators import invoke_ui, block_ui
import wxml.builder
from wxml.event import Event
from wxml.attr import nested_getattr, nested_hasattr

DEBUG_UPDATE = False
DEBUG_STORE = False


class BindTarget(object):
    def __init__(self,
                 obj : Any,
                 attr : Union[Callable, str],
                 transform : Optional['Transformer'] = None,
                 arguments : Optional[Dict[str, Any]] = None):
        self.obj = obj
        self.attr = attr
        self.is_call = callable(self.attr)
        self.transformer = transform
        self.arguments = arguments or {}

        self.bind_key = None

        if self.is_call:
            bindings = [k for k, v in self.arguments.items() if isinstance(v, BindValue)]
            if len(bindings):
                self.bind_key = bindings[0]
            else:
                self.bind_key = None

    def __call__(self, value : Any) -> None:
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
    def __init__(self,
                 obj : Any,
                 attr : Union[Callable, str],
                 converter : Optional['Transformer'] = None,
                 arguments : Optional[Dict[str, Any]] = None):
        self.obj = obj
        self.attr = attr
        self.is_call = callable(self.attr)
        self.converter = converter
        self.arguments = arguments or {}

    def receive(self) -> Any:
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

    @staticmethod
    def _store_file():
        filename = os.path.join(DataStore.Directory, '%s.store.json' % os.path.splitext(os.path.basename(sys.modules['__main__'].__file__))[0])
        return filename

    @staticmethod
    def _load():
        if os.path.exists(DataStore._store_file()):
            try:
                with open(DataStore._store_file(), 'r') as fp:
                    data = json.loads(fp.read())
                    DataStore.store = data
                    if DEBUG_STORE:
                        print('Store File loaded from %s' % DataStore._store_file())
            except Exception:
                DataStore.store = {}
        else:
            DataStore.store = {}

    @staticmethod
    def save():
        if len(DataStore._map) > 0:
            with open(DataStore._store_file(), 'w') as fp:
                state = {
                    k: b.save()
                    for k, b in DataStore._map.items()
                }
                print(json.dumps(state, indent=4), file=fp)

    @staticmethod
    def get(bind):
        if DataStore.store is None:
            DataStore._load()

        if bind.name is None:
            name = 'value-%d' % DataStore.counter
            DataStore.counter += 1
        else:
            name = bind.name

        DataStore._map[name] = bind
        val = bind.load(DataStore.store.get(name))

        if DEBUG_STORE:
            print('store.get(%s) = %s' % (name, val))

        return val

class BindValueSerializer(object):
    def serialize(self, value):
        raise NotImplementedError('implement serialize in child')

    def deserialize(self, value):
        raise NotImplementedError('implement deserialize in child')


class BindValue(object):
    def __init__(self,
                 value : Any,
                 name : Optional[str] = None,
                 parent = None,
                 serialize = False,
                 trace = False,
                 serializer : Optional[BindValueSerializer] = None):

        if serialize is True and name is None:
            raise ValueError('BindValue: name cannot be None when serialize is True')

        self._value = value
        self.name: str = name
        self._trace = trace

        self._serializer = serializer

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

    def load(self, value):
        if self._serializer is not None and value is not None:
            return self._serializer.deserialize(value)
        else:
            return value

    def save(self):
        if self._serializer is not None:
            return self._serializer.serialize(self.value)
        else:
            return self.value

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

        if self._trace or DEBUG_UPDATE:
            print(' %s.value changed by widget=%s new_value=%s value=%s' % (
                self.name or self.__class__.__name__, obj, value, self.value
            ))

        self._set(value, source=obj)

        # call skip to make any further event handlers are called
        evt.Skip()

    def __str__(self):
        return str(self._value)

    def touch(self, all=False):
        """
            Fires an update of all targets without changing the value
        """
        if all:
            self.touch_all()
        else:
            self.update_target()

    def touch_all(self):
        """
            Fire update of all targets, including any BindValue members
        """
        self.touch()
        for v in self.__dict__.values():
            if isinstance(v, BindValue):
                v.touch_all()

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
    def __init__(self,
                 array: List,
                 name : Optional[str] = None,
                 parent=None,
                 serialize=False,
                 trace=False,
                 preserve=True,
                 index_update: Optional[Callable[[], None]] = None,
                 serializer : Optional[BindValueSerializer] = None,
                 default_index : int = 0,
                 default : Optional[Any] = None):
        super().__init__(array, name=name, parent=parent, serialize=serialize, trace=trace, serializer=serializer)
        self.preserve = preserve

        if default is not None:
            try:
                def_index = self.value.index(default)
            except ValueError:
                def_index = default_index
        else:
            def_index = default_index

        self.index = BindValue(
            def_index,
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

        self.after_changed += (index_update or self._set_index)

    def _set_index(self, e):
        if not self.preserve:
            self.index.value = 0
            self.index.touch()
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
        try:
            return self.value[self.index.value]
        except (IndexError, KeyError):
            return None


class DynamicValue(BindValue):
    """
        Creating a DynamicValue without a update method will always cause
        targets to be updated. This can be used as a way to group together
        bind values to be listened to.
    """
    def __init__(self,
                 *listeners : List[BindValue],
                 update : Callable[[], None] = None,
                 default : Optional[Any] = '',
                 name : Optional[str] = None,
                 trace = False):
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


class DynamicArrayBindValue(DynamicValue, ArrayBindValue):
    """
        listeners: list of BindValue's that will cause this to update
        update   : the method that will get the new value
        name     : identifier useful for debugging
        trace    : additional tracing
        preserve : when the value changes, attempt to preserve
                   the selected item, otherwise the index is
                   constrained to the new contents
    """

    def __init__(self,
                 *listeners : List[BindValue],
                 update : Optional[Callable[[], None]] = None,
                 name : Optional[str] = None,
                 trace = False,
                 index_update: Optional[Callable[[], None]] = None,
                 preserve = True):
        super().__init__(*listeners, name=name, update=update, trace=trace)
        self.preserve = preserve
        if index_update is not None:
            self.after_changed -= self._set_index
            self.after_changed += index_update


class Transformer(object):
    def __init__(self, bind_value: BindValue):
        self.bound = bind_value
    def to_widget(self, value):
        raise NotImplementedError()
    def from_widget(self, value):
        raise NotImplementedError


class ToWidgetGenericTransformer(Transformer):
    def __init__(self, bind_value, converter : Callable[[Any], Any]):
        super().__init__(bind_value)
        self.converter = converter

    def to_widget(self, value):
        return self.converter(value)


class FromWidgetGenericTransformer(Transformer):
    def __init__(self, bind_value, converter : Callable[[Any], Any]):
        super().__init__(bind_value)
        self.converter = converter

    def from_widget(self, value):
        return self.converter(value)

class ToWidgetProperty(ToWidgetGenericTransformer):
    def __init__(self, bind_value, prop_name : str, conv : Callable[[Any], Any] = str):
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
