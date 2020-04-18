import wx
import os
import time
from xml.etree import ElementTree as ET
import collections
import importlib
import sys
import ast
import functools
import threading
import re
from typing import NamedTuple, Optional
import traceback
import logging
import enum
import platform
from pathlib import Path

from wxml.event import Event
from wxml.decorators import invoke_ui, block_ui
import wxml.bind as bind
from wxml.utils import ImgGroup, Resources, IconGroup
from wxml.attr import nested_getattr, nested_hasattr

DEBUG_EVAL = False
DEBUG_ATTR = False
DEBUG_COMPILE = False
DEBUG_TIME = False
DEBUG_BIND = False
DEBUG_ERROR = False
DEBUG_ERROR_UI = True
DEBUG_EVENT = False

AutoImportedPackages = set()

def full_class_path(class_type: type):
    module = '' if class_type.__module__ == "__main__" else '%s.' % class_type.__module__
    return '%s%s' % (module, class_type.__qualname__)

class CustomNodeType(enum.Enum):
    Control = 0
    PassParent = 1

class Passthrough(object):
    pass

def clone_element(element : ET.Element) -> ET.Element:
    new_element = ET.Element(element.tag, **element.attrib)
    for child in element:
        new_element.append(clone_element(child))
    return new_element

class Ui(object):
    Registry = {}
    _imported = set()

    def __init__(self, view_name):
        self.filename = view_name

    def __call__(self, class_obj):
        defined_in = sys.modules[class_obj.__module__].__file__
        xml_path = os.path.abspath(os.path.join(os.path.dirname(defined_in), self.filename))
        use_name = self.filename
        class_obj.filename = xml_path
        # make it available as the filename, and the class name
        Ui.Registry[use_name] = class_obj
        Ui.Registry[full_class_path(class_obj)] = class_obj

        # Import any custom wx controls from files that are defined
        if class_obj.__module__ != 'wxml.builder' and class_obj.__module__  not in Ui._imported:
            for name, obj in sys.modules[class_obj.__module__].__dict__.items():
                if isinstance(obj, type) and issubclass(obj, wx.Control):
                    path = full_class_path(obj)
                    if path not in Control.Registry:
                        Control.Registry[path] = obj
            Ui._imported.add(class_obj.__module__)

        return class_obj

class Control(object):
    Registry = {}

    def __init__(self, class_obj):
        self._path = full_class_path(class_obj)
        self._class_obj = class_obj
        Control.Registry[full_class_path(class_obj)] = class_obj

    def __call__(self, parent, *args, auto_sizer=True, **kwargs):
        # see if there is XML associated with this class
        ctor = getattr(self._class_obj, '_ctor', None)

        builder = UiBuilder(self._class_obj.__name__)
        builder._view_model_is_root = True
        builder.init_build(None)

        if ctor is None:
            ctor = ET.Element('Fake')

        obj = builder.wx_node(
            ctor,
            parent,
            actual_obj=self._class_obj,
            extra_args=args,
            extra_kwargs=kwargs,
            skip_sizer=not auto_sizer
        )
        for c in ctor:
            builder.compile(c, obj, {})

        assert obj is not None

        builder.post_build(obj)

        if parent.Sizer is not None:
            parent.Layout()

        if hasattr(obj, 'ready'):
            obj.ready()

        return obj

    def __str__(self):
        return '<%s(%s) object at 0x%x>' % (
            full_class_path(self.__class__),
            full_class_path(self._class_obj),
            id(self)
        )

def wx_getattr(value):
    if hasattr(wx, value):
        return getattr(wx, value)

    for name, mod in sys.modules.items():
        if name.startswith('wx.') and hasattr(mod, value):
            return getattr(mod, value)

    if value in UiBuilder.components:
        return UiBuilder.components[value]

    if value in Control.Registry:
        return Control.Registry[value]

def wx_hasattr(value):
    return wx_getattr(value) is not None

class NodeRegistry(dict):
    def __init__(self):
        super().__init__()
        self['names'] = {}
        self['filters'] = []

    def node(self, *names):
        def wraps(func):
            for name in names:
                self['names'][name] = func
            return func
        return wraps

    def filter(self, callable):
        def wraps(func):
            self['filters'].append((callable, func))
            return func
        return wraps

    def action_for(self, node):
        if node.tag in self['names']:
            return self['names'][node.tag]

        for _is, f in self['filters']:
            if _is(node):
                return f


Node = NodeRegistry()
NodePost = NodeRegistry()

class UiBuilder(object):
    """
        Handles processing an Xml file that will be turned into an interface.
    """

    components = {}
    debug_names = {}
    counter = collections.defaultdict(lambda: 0)

    # actions that run when the builder is created
    _queued = []

    def __init__(self, filename):
        self.filename = filename
        self._view_model_is_root = False

    @staticmethod
    def run_at_start(func, *args, **kwargs):
        UiBuilder._queued.append((func, args, kwargs))

    def init_build(self, view_model):
        self.view_model = view_model

        self.models = {}
        self.debug_names = {}
        self.events = {}
        self.children = {}
        self.accel_table = []
        self.loop_vars = {}
        self.construction_errors = []
        self.values_to_update = []
        self.controller = '__main__'

        self.menu_ids = {}

        # try and run queued actions
        if wx.App.Get() is not None and UiBuilder._queued is not None:
            for f, args, kwargs in UiBuilder._queued:
                f(*args, **kwargs)
            UiBuilder._queued = None

    def post_build(self, obj):
        obj.widgets = {}
        obj.models = {}

        for widget, name in self.debug_names.items():
            obj.widgets[name] = widget
        for name, model in self.models.items():
            obj.models[name] = model

        for widget, events in self.events.items():
            if widget is None:
                widget = obj
            self.build_widget_events(obj, widget, events)

        obj.accel_table = self.accel_table

        if hasattr(obj, 'SetAcceleratorTable') and len(self.accel_table):
            entries = [wx.AcceleratorEntry() for _ in self.accel_table]
            for e, c in zip(entries, self.accel_table):
                e.Set(*c)

            obj.SetAcceleratorTable(wx.AcceleratorTable(entries))

        UiBuilder.debug_names.update(self.debug_names)

    def build(self, view_model, parent=None, sizer_flags=None):
        self.init_build(view_model)

        try:
            tree = ET.parse(self.filename)
        except Exception as ex:
            import traceback
            self.construction_errors.append([ex, 'PARSE', None, traceback.format_exc()])
            return None

        root = tree.getroot()
        root.attrib.update(sizer_flags or {})

        self.controller = root.attrib.pop('Controller', '__main__')

        obj = UiBuilder.compile(self, root, parent)
        if obj is None:
            obj = getattr(self, 'constructed')

        self.post_build(obj)

        return obj

    def build_widget_events(self, obj, widget, events):
        widget_name = self.debug_names[widget]
        setattr(obj, widget_name, widget)

        for (event, func, *evt_obj) in events:
            event_type = wx_getattr(event)

            if len(evt_obj):
                event_obj_name = self.debug_names[evt_obj[0]]
                event_handler = Event(event_obj_name)
                args = (event_type, event_handler, evt_obj[0])

                if DEBUG_EVENT:
                    print('  %s.%s event (%s) created' % (event_obj_name, event, event_handler.name), end='')
            else:
                event_handler = Event('%s_on_%s' % (widget_name, event.lstrip('EVT_').title()))
                args = (event_type, event_handler)

                if DEBUG_EVENT:
                    print('  %s.%s event (%s) created' % (widget_name, event, event_handler.name), end='')

            if func is not None:
                event_handler += func
                if DEBUG_EVENT:
                    print(', connected to %s' % func, end='')

            if DEBUG_EVENT:
                print()

            widget.Bind(*args)

            setattr(obj, event_handler.name, event_handler)

    def str2py(self, value, bare_class=False):
        """
            Convert a string value into something useable
        """

        if value and value[0] == '$':
            value = value[1:]
            not_a_class = False
        else:
            not_a_class = True

        retval = value
        resolved = 'str'

        bind_expr = r'^\(([_A-Za-z0-9\.]+)(?:\[([_A-Za-z0-9\.-]+)\])?(?:\:(EVT_[A-Z_]+)(?:\[([_A-Za-z0-9\.]+)\])?)?\)$'
        tokens = re.search(bind_expr, value)

        # one or two way binding
        if not_a_class and tokens is not None:
            key = tokens.group(1)
            to_widget = tokens.group(2)
            event = tokens.group(3)
            event = None if event is None else wx_getattr(event)

            transform = None
            receiver = None

            binding = self.str2py(key, bare_class=True)

            if binding is None and hasattr(self, 'overrides'):
                t, *k = key.split('.')
                k = '.'.join(k)
                binding = nested_getattr(k, self.overrides.get(t))

            if to_widget is not None:
                # auto member access with .
                if to_widget.startswith('.'):
                    prop = to_widget.lstrip('.').split('-', 1)
                    if len(prop) > 1:
                        prop, conv = prop
                        converter_func = self.str2py(conv, bare_class=True)
                    else:
                        prop = prop[0]
                        converter_func = str

                    transform = bind.ToWidgetProperty(binding, prop, converter_func)
                else:
                    transform = self.str2py(to_widget, bare_class=True)
                if not isinstance(transform, bind.Transformer):
                    transform = bind.ToWidgetGenericTransformer(None, transform)

            from_widget = tokens.group(4)
            if from_widget is not None:
                receiver = self.str2py(from_widget, bare_class=True)
                if not isinstance(receiver, bind.Transformer):
                    receiver = bind.FromWidgetGenericTransformer(None, receiver)

            if binding is not None and isinstance(binding, bind.BindValue):
                return binding, event, transform, receiver
        # one time binding
        elif not_a_class and len(value) and value[0] == '{' and value[-1] == '}':
            key = value.lstrip('{').rstrip('}')
            if key in self.loop_vars:
                resolved = 'loop_var'
                obj = self.loop_vars[key]
                if DEBUG_EVAL:
                    print('   Raw="{0}" ResolveType={1} Value={2} Class={3}'.format(value, resolved, obj, obj.__class__.__name__))
                return self.loop_vars[key]

            if hasattr(self, 'overrides'):
                t, *k = key.split('.')
                if t in self.overrides:
                    obj = self.overrides.get(t)
                    if k and obj is not None:
                        obj = nested_getattr('.'.join(k), obj)

                    resolved = 'OneTimeOverride'
                    if DEBUG_EVAL:
                        print('   Raw="{0}" ResolveType={1} Value={2} Class={3}'.format(value, resolved, obj, obj.__class__.__name__))

                    if obj is not None:
                        return obj

            bound = nested_getattr(key, self.view_model, default=None)#  getattr(self.view_model, key, None)
            if bound is not None:
                resolved = 'ViewModel'
                if DEBUG_EVAL:
                    print('   Raw="{0}" ResolveType={1} Value={2} Class={3}'.format(value, resolved, bound, bound.__class__.__name__))
                return bound

            child = self.children.get(key)#nested_getattr(key, self.children)
            if child is not None:
                resolved = 'View_widget'
                if DEBUG_EVAL:
                    print('   Raw="{0}" ResolveType={1} Value={2} Class={3}'.format(value, resolved, child, child.__class__.__name__))
                return child

            resource = nested_getattr(key, Resources, default=None)#  getattr(self.view_model, key, None)
            if resource is not None:
                resolved = 'Resources'
                if DEBUG_EVAL:
                    print('   Raw="{0}" ResolveType={1} Value={2} Class={3}'.format(value, resolved, resource, resource.__class__.__name__))
                return resource

            builder = nested_getattr(key, self, default=None)
            if builder is not None:
                resolved = 'UiBuilder'
                if DEBUG_EVAL:
                    print('   Raw="{0}" ResolveType={1} Value={2} Class={3}'.format(value, resolved, builder, builder.__class__.__name__))
                return resource

        # look first for something in the view model
        if not_a_class and bare_class:
            retval = nested_getattr(value, self.view_model, None)
            if retval is not None:
                resolved = 'ViewModel_member'
                if DEBUG_EVAL:
                    print('   Raw="{0}" ResolveType={1} Value={2} Class={3}'.format(value, resolved, retval, retval.__class__.__name__))
                return retval

        # look for something in the imported Python modules
        if not_a_class and bare_class:
            retval = nested_getattr(value, default=None)
            if retval is not None:
                resolved = 'ModuleMember'
                if DEBUG_EVAL:
                    print('   Raw="{0}" ResolveType={1} Value={2} Class={3}'.format(value, resolved, retval, retval.__class__.__name__))
                return retval

        if not_a_class and bare_class and hasattr(self, 'overrides'):
            t, *k = value.split('.')
            if t in self.overrides:
                obj = self.overrides.get(t)
                if k and obj is not None:
                    obj = nested_getattr('.'.join(k), obj)

                if obj is not None:
                    resolved = 'Override'
                    if DEBUG_EVAL:
                        print('   Raw="{0}" ResolveType={1} Value={2} Class={3}'.format(value, resolved, obj, obj.__class__.__name__))
                    return obj

        if not_a_class and wx_hasattr(value):
            retval = wx_getattr(value)
            resolved = 'wx attr'
        else:
            try:
                retval = ast.literal_eval(value)
                resolved = 'literal'
            except (SyntaxError, ValueError):
                if not_a_class:
                    for name, mod in sys.modules.items():
                        if name.startswith('wx.'):
                            context = {k: getattr(mod, k) for k in dir(mod)}
                            ns = {}
                            cmd = 'var_value = (%s)' % (value)

                            try:
                                exec(cmd, context, ns)
                                retval = ns['var_value']
                                resolved = '%s attr' % mod.__name__
                                break
                            except Exception as ex:
                                pass

        # last chance, look again at imported modules if this might be something
        if not_a_class and (resolved == 'str' and '.' in value):
            orig = value
            retval = nested_getattr(value, default=None)
            if retval is not None:
                resolved = 'ModuleMember(again)'
                if DEBUG_EVAL:
                    print('   Raw="{0}" ResolveType={1} Value={2} Class={3}'.format(value, resolved, retval, retval.__class__.__name__))
                return retval
            else:
                retval = orig

        if DEBUG_EVAL:
            print('   Raw="{0}" ResolveType={1} Value={2} Class={3}'.format(value, resolved, retval, retval.__class__.__name__))

        return retval

    def eval_args(self, args, exclude=None, prefix=None, only_args=None, excl_prefix=None):
        evaled = {}
        exclude = exclude or []
        iterator = {k: args[k] for k in only_args if k in args} if only_args is not None else args

        for key, value in iterator.items():
            if len(value) > 2 and value[1] == ':':
                value  = value[0] + value[2:]

            if (key not in exclude and
                (prefix is None or key.startswith(prefix)) and
                (excl_prefix is None or not any(key.startswith(e) for e in excl_prefix))):
                evaled[key] = self.str2py(value)
                if DEBUG_ATTR:
                    print('   Attr={0} Input="{1}" Value={2}'.format(key, value, evaled[key]))

        return evaled

    def eval_args_kwargs(self, args, exclude=None, prefix=None, only_args=None, excl_prefix=None):
        arg_map = {}
        kwargs = {}

        for key, value in self.eval_args(args, exclude, prefix, only_args, excl_prefix).items():
            if isinstance(key, int):
                arg_map[key] = value
            else:
                kwargs[key] = value

        if arg_map:
            args = [None] * (1 + max(arg_map))
            for idx, val in arg_map.items():
                args[idx] = val
        else:
            args = []

        return args, kwargs

    def compile(self, node, parent=None, params=None, inject=None):
        action = Node.action_for(node)

        if DEBUG_COMPILE:
            print(' %s.%s' % (os.path.splitext(os.path.basename(self.filename))[0], node.tag), '->', action.__name__ if action is not None else '[no action]')

        try:
            obj = action(self, node, parent, params)
        except Exception as ex:
            if DEBUG_ERROR:
                print('ERROR', '[tag: %s]' % node.tag, '[parent: %s]' % parent, 'exception:', ex)
            self.construction_errors.append([ex, node, parent, traceback.format_exc()])
            raise

        if obj is None:
            return
        elif isinstance(obj, tuple) or isinstance(obj, list):
            parent_obj, params2 = obj
            params = params or {}
            params.update(params2)
        else:
            parent_obj = obj
            params = params or {}

        if parent_obj is None:
            return

        if inject is not None:
            parent_obj.__dict__.update(inject)

        for child in node:
            obj = self.compile(child, parent_obj, params=params)

        post_action = NodePost.action_for(node)
        if post_action is not None:
            try:
                if DEBUG_COMPILE:
                    print(' %s.%s (post)' % (os.path.splitext(os.path.basename(self.filename))[0], node.tag), '->', post_action.__name__)
                post_action(self, node, parent_obj, params)
            except Exception as ex:
                if DEBUG_ERROR:
                    print('ERROR', '[%s.post]' % node.tag, '[parent: %s]' % parent, 'exception:', ex)
                self.construction_errors.append([ex, node.tag + '.post', parent, traceback.format_exc()])

        return parent_obj

    @Node.node('Bitmaps')
    def images(self, node, parent, params):
        if not hasattr(Resources, 'Bitmaps'):
            Resources.Bitmaps = ImgGroup()

        imgs = Resources.Bitmaps

        for c in node:
            if hasattr(imgs, c.tag):
                args = self.eval_args(c.attrib)
                getattr(imgs, c.tag)(**args)

    @Node.node('Icons')
    def icons(self, node, parent, params):
        if not hasattr(Resources, 'Icons'):
            Resources.Icons = IconGroup()

        imgs = Resources.Icons

        for c in node:
            if hasattr(imgs, c.tag):
                args = self.eval_args(c.attrib)
                getattr(imgs, c.tag)(**args)

    @Node.node('Namespace')
    def namespace(self, node, parent, params):
        return 1

    @Node.node('ShowIconStandalone')
    def show_icon_standalone(self, node, parent, params):
        path = Path(sys.modules['__main__'].__file__)
        myappid = 'python.script.%s' % '.'.join(path.parts[-2:])

        try:
            import ctypes
        except ImportError:
            return

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except AttributeError:
            pass

    @Node.filter(lambda n: n.tag in Control.Registry and n.tag in UiBuilder.components)
    def wx_custom_control_with_xml(self, node, parent=None, params=None, root=wx, tag=None):
        class_obj = Control.Registry[node.tag]
        ctor = class_obj._ctor

        builder = UiBuilder(class_obj.__name__)
        builder._view_model_is_root = True
        builder.init_build(None)

        use_node = ET.Element(node.tag)
        use_node.attrib.update(ctor.attrib)
        use_node.attrib.update(node.attrib)

        for c in ctor:
            use_node.append(clone_element(c))

        for child in node:
            use_node.append(clone_element(child))

        obj = builder.wx_node(use_node, parent, params, actual_obj=class_obj)
        for c in use_node:
            builder.compile(c, obj, {})

        builder.post_build(obj)

        var_name = node.attrib.get('Name', '%s_%d' % (tag or node.tag, self.counter[class_obj]))
        self.counter[class_obj] += 1
        self.debug_names[obj] = var_name
        self.children[var_name] = obj

        if isinstance(obj, (wx.Panel, wx.Frame)):
            self.wx_setsizer(use_node, obj, params)

        return obj

    @Node.filter(lambda n: n.tag in UiBuilder.components)
    def create_component(self, node, parent, params):
        obj = UiBuilder.components[node.tag]
        true_node = obj._ctor
        overrides = obj._overrides

        use_node = ET.Element('CustomWx')
        use_node.attrib['_class'] = node.tag
        use_node.attrib['_passthru'] = obj._type.name
        use_node.attrib.update(true_node.attrib)

        use_node.attrib.update({
            k: v
            for k, v in node.attrib.items()
            if k not in obj._overrides
        })

        for c in true_node:
            use_node.append(clone_element(c))

        parent_nodes = use_node.findall('.//*[@ChildParent]')
        for p in parent_nodes:
            if p.attrib.get('ChildParent', 'False').lower() in ('', 'true'):
                parent_node = p
                break
        else:
            parent_node = use_node

        for child in node:
            parent_node.append(clone_element(child))

        this_overrides = getattr(self, 'overrides', {})

        build_overrides = {}

        for name, default in overrides.items():
            val = self.str2py(node.attrib.get(name, overrides.get(name, default or '')))
            # if this is a string, we should try and convert it
            if isinstance(val, str):
                build_overrides[name] = self.str2py(val)
            else:
                build_overrides[name] = val

        builder = UiBuilder(self.filename + '[%s]' % node.tag)
        builder.init_build(self.view_model)
        builder.overrides = build_overrides
        obj = builder.compile(use_node, parent, params)
        builder.post_build(obj)

        if isinstance(obj, (wx.Panel, wx.Frame)):
            self.wx_setsizer(use_node, obj, params)

        return None

    @Node.filter(lambda n: n.tag in Control.Registry)
    def wx_custom_control(self, node, parent=None, params=None, root=wx, tag=None):
        return self.wx_node(node, parent, params, actual_obj=Control.Registry[node.tag])

    @Node.node('ImageList')
    def make_image_list(self, node, parent, params):
        obj = self.wx_node(node, parent=parent, params=params, parentless=True, skip_sizer=True)
        parent.AssignImageList(obj)

    @Node.filter(lambda n: hasattr(wx, n.tag) and issubclass(getattr(wx, n.tag), wx.DropTarget))
    def create_drop_target(self, node, parent, params):
        class_obj = wx_getattr(node.tag)
        name = node.attrib.get('Name')
        handler = class_obj(parent)

    def loop_over(self, node, parent, params):
        loop_var = self.str2py(node.attrib.get('over'))

        self.loop_vars = {}

        fake = ET.Element('Config')
        for child in node:
            fake.append(child)

        for var in loop_var:
            self.loop_vars['over'] = var
            for child in node:
                self.setup_parent(fake, parent, params)

    @Node.node('Config', 'parent')
    def setup_parent(self, root, parent, params, item=None):
        name = root.attrib.get('Item')
        if item is not None:
            parent = item
        elif name == 'sizer':
            parent = parent.Sizer

        for func in root:
            try:
                if func.tag == 'Loop':
                    self.loop_over(func, parent, params)
                else:
                    self.setup_parent_node(func, parent, params)
            except Exception as ex:
                self.construction_errors.append([ex, func, parent, traceback.format_exc()])

    def setup_parent_node(self, func, parent, params):
        call = getattr(parent, func.tag)

        if DEBUG_COMPILE:
            print(' %s.%s' % (parent.__class__.__name__, func.tag))

        # one-way bind to property, will update BindValue when event is fired
        if 'Bind' in func.attrib:
            binding, event, transform, receiver = self.str2py(func.attrib['Bind'])
            self.binding_hook(
                binding,
                parent,
                func.tag,
                event=event,
                receiver=receiver,
                can_update=False,
                bind_to=params.get('bind-to')
            )
        elif call is not None and callable(call):
            args = self.eval_args(func.attrib, exclude=["Name"])

            bindings = {
                k: v
                for k, v in args.items()
                if ((isinstance(v, tuple) and isinstance(v[0], bind.BindValue)) or
                     isinstance(v, bind.BindValue))
            }

            call_args = {k: v for k, v in args.items() if k not in bindings}
            binding_args = {k: v for k, v in call_args.items()}
            remove_binding = set()

            for k, b in bindings.items():
                if isinstance(b, bind.BindValue):
                    call_args[k] = b.value
                    remove_binding.add(k)
                else:
                    (b, e, t, v) = b
                    if t is not None:
                        call_args[k] = t.to_widget(b.value)
                    else:
                        call_args[k] = b.value

                binding_args[k] = b

            for k in remove_binding:
                bindings.pop(k)

            obj = call(**call_args)

            for name, (binding, event, transform, receiver) in bindings.items():
                self.binding_hook(
                    binding,
                    parent,
                    func.tag,
                    event=event,
                    transformer=transform,
                    all_args=binding_args,
                    receiver=receiver,
                    bind_to=params.get('bind-to')
                )

            name = func.attrib.get("Name")
            if name is not None:
                self.debug_names[obj] = name

            self.setup_parent(func, obj, params)
        elif call is not None or func.tag in dir(parent):
            set_to = self.eval_args({'value': func.attrib.get('value')})['value']
            if isinstance(set_to, bind.BindValue):
                setattr(parent, func.tag, set_to.value)
            elif isinstance(set_to, tuple) and isinstance(set_to[0], bind.BindValue):
                binding, event, transformer, receiver = set_to
                self.binding_hook(
                    binding,
                    parent,
                    func.tag,
                    event=event,
                    transformer=transformer,
                    receiver=receiver,
                    bind_to=params.get('bind-to')
                )
            else:
                setattr(parent, func.tag, set_to)

    def binding_hook(self, binding: bind.BindValue, parent, attr_name, event=None,
                     transformer=None, all_args=None, receiver=None,
                     can_update=True, bind_to=None):
        attribute = getattr(parent, attr_name)
        if callable(attribute):
            attr_name = attribute
            arguments = all_args
        else:
            arguments = {}

        to_widget = can_update
        from_widget = attr_name is not None and event is not None

        if DEBUG_BIND:
            if to_widget and from_widget:
                bind_type = 'Bidirectional'
            elif to_widget:
                bind_type = 'ToWidget'
            else:
                bind_type = 'ToSource'
            print('  Bound {0} to {1}.{2} direction={3}'.format(
                '<%s(%s):%s>'  % (binding.name or '', binding.__class__.__name__, hex(id(binding))),
                    parent.__class__.__name__,
                    attr_name,
                    bind_type
                )
            )

        if to_widget:
            binding.add_target(parent, attr_name, transform=transformer, arguments=arguments)
        if from_widget:
            binding.add_source(parent, event, attr_name, transform=receiver, bind_to=bind_to)

        if can_update and binding not in self.values_to_update:
            self.values_to_update.append(binding)

    SIZER_FLAGS_DICT = {
        wx.BoxSizer: [
            'Align',
            'Border',
            'Bottom',
            'Center',
            'Centre',
            'DoubleBorder',
            'DoubleHorzBorder',
            'Expand',
            'FixedMinSize',
            'Left',
            'Proportion',
            'ReserveSpaceEvenIfHidden',
            'Right',
            'Shaped',
            'Top',
            'TripleBorder',
        ],
        wx.GridBagSizer: [
            'Pos',
            'Span',
            'Flag',
            'Border'
        ],
        wx.StaticBoxSizer: [
            'Align',
            'Border',
            'Bottom',
            'Center',
            'Centre',
            'DoubleBorder',
            'DoubleHorzBorder',
            'Expand',
            'FixedMinSize',
            'Left',
            'Proportion',
            'ReserveSpaceEvenIfHidden',
            'Right',
            'Shaped',
            'Top',
            'TripleBorder',
        ],
        wx.GridSizer: [
            'Align',
            'Border',
            'Bottom',
            'Center',
            'Centre',
            'DoubleBorder',
            'DoubleHorzBorder',
            'Expand',
            'FixedMinSize',
            'Left',
            'Proportion',
            'ReserveSpaceEvenIfHidden',
            'Right',
            'Shaped',
            'Top',
            'TripleBorder',
        ],
        wx.FlexGridSizer: [
            'Align',
            'Border',
            'Bottom',
            'Center',
            'Centre',
            'DoubleBorder',
            'DoubleHorzBorder',
            'Expand',
            'FixedMinSize',
            'Left',
            'Proportion',
            'ReserveSpaceEvenIfHidden',
            'Right',
            'Shaped',
            'Top',
            'TripleBorder',
        ],
        wx.WrapSizer: [
            'Pos',
            'Span',
            'Flag',
            'Border',
        ]
    }
    ARGLESS_SIZER = set(
        ['Expand', 'Shaped', 'Top', 'Right', 'Left', 'Center', 'Bottom', 'Centre', 'ReserveSpaceEvenIfHidden']
    )

    def SizerFlags(self, parent):
        if parent.__class__ in UiBuilder.SIZER_FLAGS_DICT:
            flags = UiBuilder.SIZER_FLAGS_DICT.get(parent.__class__, [])
        elif parent is not None and hasattr(parent, 'Sizer') and parent.Sizer is not None:
            flags = UiBuilder.SIZER_FLAGS_DICT.get(parent.Sizer.__class__, UiBuilder.SIZER_FLAGS_DICT[wx.BoxSizer])
        elif parent is not None:
            flags = UiBuilder.SIZER_FLAGS_DICT.get(parent, [])
        else:
            flags = []

        return flags

    @Node.node('PaintDC')
    def paint_dc(self, node, parent, params):
        pass

    @Node.filter(lambda n: hasattr(wx, n.tag) and issubclass(getattr(wx, n.tag), wx.Sizer))
    def wx_create_sizer(self, node, parent, params):
        class_obj = nested_getattr(node.tag, root=wx)
        kwargs = self.eval_args(node.attrib, exclude=self.SizerFlags(class_obj))

        this_obj = class_obj(**kwargs)

        sizer_flags = self.eval_args(node.attrib, only_args=self.SizerFlags(class_obj))

        this_obj.default_flags = sizer_flags
        parent.SetSizer(this_obj)

        var_name = '%s_%d' % (node.tag, self.counter[class_obj])
        self.counter[class_obj] += 1
        self.debug_names[this_obj] = var_name

        return parent

    @Node.node('CustomWx')
    def wx_custom(self, node, parent, params):
        if node.attrib.pop('_passthru') == CustomNodeType.PassParent.name:
            return parent
        else:
            new_obj = self.wx_node(node, parent, params, tag=node.attrib.pop('_class'))
            return new_obj

    @Node.filter(lambda n: hasattr(wx, n.tag))
    def wx_node(self, node, parent=None, params=None, root=wx, tag=None, actual_obj=None,
                parentless=False, skip_sizer=False, extra_args=None, extra_kwargs=None):
        params = params or {}

        if actual_obj is not None:
            class_obj = actual_obj
        else:
            class_obj = nested_getattr(tag or node.tag, root=root)
            if class_obj is None:
                class_obj = wx_getattr(tag or node.tag)

        if class_obj is None:
            raise Exception('wx object [%s] could not be found' % (tag or node.tag))

        style_args = getattr(self, 'style_args', {}).get(tag or node.tag, {})

        args = self.eval_args(style_args, exclude=self.SizerFlags(parent) + ['Name', 'ChildParent'])
        args.update(self.eval_args(
            node.attrib,
            excl_prefix=['Config.', 'EventBindings.', 'Font.', 'FontInfo.'],
            exclude=self.SizerFlags(parent) + ['Name', 'ChildParent']
        ))

        bindings = {
            k: v
            for k, v in args.items()
            if isinstance(v, tuple) and isinstance(v[0], bind.BindValue)
        }

        for k, (b, e, to_widget, r) in bindings.items():
            args[k] = b.value if to_widget is None else to_widget.to_widget(b.value)

        for k, v in args.items():
            if isinstance(v, bind.BindValue):
                args[k] = v.value

        if extra_kwargs is not None:
            args.update(extra_kwargs)
        if extra_args is not None:
            p_args = extra_args
        else:
            p_args = ()

        if parentless:
            this_obj = class_obj(*p_args, **args)
        else:
            this_obj = class_obj(parent, *p_args, **args)

        if self._view_model_is_root and self.view_model is None:
            self.view_model = this_obj

        if hasattr(this_obj, 'SetDoubleBuffered'):
            this_obj.SetDoubleBuffered(True)

        for name, (binding, event, transform, receiver) in bindings.items():
            self.binding_hook(
                binding,
                this_obj,
                name.title(),
                event=event,
                transformer=transform,
                receiver=receiver,
                bind_to=params.get('bind-to')
            )

        var_name = node.attrib.get('Name', '%s_%d' % (tag or node.tag, self.counter[class_obj]))
        self.counter[class_obj] += 1
        self.debug_names[this_obj] = var_name
        self.children[var_name] = this_obj
        this_obj.Name = var_name

        if not skip_sizer and parent is not None and getattr(parent, 'Sizer', None) is not None:
            sizer_args = {k: v for k, v in getattr(parent.Sizer, 'default_flags', {}).items()}
            widget_args = self.eval_args(style_args, only_args=self.SizerFlags(parent.Sizer))
            overrides = self.eval_args(node.attrib, only_args=self.SizerFlags(parent.Sizer))
            sizer_args.update(widget_args)
            sizer_args.update(overrides)

            # shaped wins over proportion
            if 'Shaped' in sizer_args:
                sizer_args.pop('Proportion', None)

            if all(hasattr(wx.SizerFlags, f) for f in sizer_args):
                s = wx.SizerFlags()
                for key, value in sizer_args.items():
                    f = getattr(s, key)

                    if key in self.ARGLESS_SIZER:
                        # empty tuple, backwards compat '' -> ()
                        if value == () or value:
                            s = f()
                    else:
                        arg = [value] if not isinstance(value, (tuple, list)) else value
                        s = f(*arg)
                parent.Sizer.Add(this_obj, s)
            else:
                parent.Sizer.Add(this_obj, **{k.lower(): v for k, v in sizer_args.items()})

        # Config. attributes
        auto_config = ET.Element('Config')
        idx = len('Config.')
        for k in node.attrib:
            if k.startswith('Config.'):
                elem = k[idx:]
                elem_node = ET.Element(elem)
                elem_node.attrib['value'] = node.attrib[k]
                auto_config.append(elem_node)
        self.setup_parent(auto_config, this_obj, params)

        # EventBindings. attributes
        auto_config = ET.Element('EventBindings')
        idx = len('EventBindings.')
        for k in node.attrib:
            if k.startswith('EventBindings.'):
                elem = k[idx:]
                elem_node = ET.Element(elem)
                elem_node.attrib['handler'] = node.attrib[k]
                auto_config.append(elem_node)
        if auto_config:
            self.set_up_events(auto_config, this_obj, params)

        font_config = ET.Element('Font')
        idx = len('Font.')
        for k in node.attrib:
            if k.startswith('Font.'):
                elem = k[idx:]
                elem_node = ET.Element(elem)
                if node.attrib[k] != '':
                    elem_node.attrib[0] = node.attrib[k]
                font_config.append(elem_node)
        if font_config:
            self.modify_font(font_config, this_obj, params)

        font_info_config = ET.Element('FontInfo')
        idx = len('FontInfo.')
        for k in node.attrib:
            if k.startswith('FontInfo.'):
                elem = k[idx:]
                if elem in ('pointSize', 'pixelSize'):
                    font_info_config.attrib[elem] = node.attrib[k]
                else:
                    elem_node = ET.Element(elem)
                    if node.attrib[k] != '':
                        elem_node.attrib[0] = node.attrib[k]
                    font_info_config.append(elem_node)
        if font_info_config:
            self.wx_font_setup(font_info_config, this_obj, params)

        return this_obj

    def add_to_sizer(self, node, parent, this_obj):
        pass

    @Node.filter(lambda n: any(hasattr(mod, n.tag) for name, mod in sys.modules.items() if name.startswith('wx')))
    def wx_imported(self, node, parent=None, params=None):
        modules = [mod for name, mod in sys.modules.items() if name.startswith('wx') and hasattr(mod, node.tag)]
        if len(modules) == 0:
            return None
        return self.wx_node(node, parent, params, root=modules[0])

    @Node.node('Import')
    def import_package(self, node, parent, params):
        importlib.import_module(node.attrib.get('module'))

    @Node.node('EventBindings')
    def set_up_events(self, node, parent, params):
        if parent not in self.events:
            self.events[parent] = []

        for child in node:
            handler = child.attrib.get('handler')
            if handler is not None:
                func = self.find_method(handler)
            else:
                func = None

            self.events[parent].append([child.tag, func])

    def find_method(self, method_name):
        tokens = method_name.split('.')

        e = self.eval_args({'arg': method_name})
        if method_name.startswith('{:'):
            method_name = e['arg']
            tokens = method_name.split('.')

        if e['arg'] is not None and callable(e['arg']):
            method = e['arg']
        elif len(tokens) == 1:
            method = getattr(
                sys.modules[self.controller],
                method_name, getattr(self.view_model, method_name, None))
        else:
            method = nested_getattr(method_name)

        if method is None:
            method = self.str2py(method_name, bare_class=True)

        return method

    FONT_INFO_ATTRIBUTES = [d for d in dir(wx.FontInfo) if not d.startswith('_')]

    @Node.node('Font')
    def modify_font(self, node, parent, params):
        """
            modifies the parent object's Font property
        """

        font = parent.Font
        for child in node:
            func = getattr(font, child.tag)
            if callable(func):
                args, kwargs = self.eval_args_kwargs(child.attrib)
                retval = func(*args, **kwargs)
                if isinstance(retval, wx.Font):
                    font = retval
            else:
                args = self.eval_args(child.attrib, only_args=['value'])
                setattr(font, child.tag, args['value'])

        parent.Font = font

    @Node.node('FontInfo')
    def wx_font_setup(self, node, parent, params):
        """
            creates a FontInfo object, configures it, and then
            constructs a new Font object that is assigned to the
            parent object
        """

        args = self.eval_args(node.attrib)
        if 'pointSize' in args:
            info = wx.FontInfo(args['pointSize'])
        elif 'pixelSize' in args:
            info = xw.FontInfo(args['pixelSize'])
        else:
            info = wx.FontInfo()

        for child in node:
            if child.tag in self.FONT_INFO_ATTRIBUTES:
                args, kwargs = self.eval_args_kwargs(child.attrib)
                info = getattr(info, child.tag)(*args, **kwargs)

        font_setter = getattr(parent, 'SetFont', None)
        if font_setter is not None:
            font_setter(wx.Font(info))

    @Node.filter(lambda n: n.tag.startswith('wx.'))
    def wx_import_node(self, node, parent, params):
        module, class_name = node.tag.rsplit('.', 1)
        importlib.import_module(module)
        return self.wx_node(node, parent, params, root=sys.modules[module], tag=class_name)

    @NodePost.node('Frame', 'Panel')
    def wx_setsizer(self, node, parent, params):
        if parent.Sizer is not None and getattr(self.view_model, 'layout', '') == 'SetSizerAndFit':
            parent.SetSizerAndFit(parent.Sizer)

    @Node.node('Include')
    def include_xml(self):
        pass

    @Node.node('View')
    @Node.filter(lambda n: n.tag in Ui.Registry)
    def build_included_view(self, node, parent, params):
        if node.tag == 'View':
            filename = node.attrib.get('view')
        else:
            filename = node.tag

        # convert to relative to current XML
        # filename = os.path.join(os.path.dirname(os.path.abspath(self.filename)), filename)

        if filename in Ui.Registry:
            view_model = Ui.Registry[filename]
        else:
            view_model = lambda *args, **kwargs: GenericViewModel(filename, *args, **kwargs)
            Ui.Registry[filename] = view_model

        sizer_flags = self.SizerFlags(parent.Sizer)
        sizer_args = {k: v for k, v in node.attrib.items() if k in sizer_flags}

        args = self.eval_args(node.attrib, exclude=self.SizerFlags(parent) + ['Name', 'View', 'view'])
        constructed = view_model(defer=True, **args)
        constructed.build(parent=parent, sizer_flags=sizer_args)

        name = node.attrib.get('Name', '%s_%d' % (constructed.__class__.__name__, self.counter[constructed.__class__]))
        self.counter[constructed.__class__] += 1

        self.models[name] = constructed
        self.debug_names[constructed.view] = name
        self.children[name] = constructed.view

    @Node.node('Triggers')
    def triggers(self, node, parent, params):
        for n in node:
            if hasattr(parent, n.tag) and (callable(getattr(parent, n.tag)) or 'value' in n.attrib):
                value = nested_getattr(n.attrib.get('on'), root=self.view_model)
                if bind is not None and isinstance(value, bind.BindValue):
                    args = self.eval_args(n.attrib, exclude=['on'])
                    func = getattr(parent, n.tag)

                    def on_changed(args, func, new_value, parent=parent):
                        if not parent:
                            return

                        send = {}
                        for k, v in args.items():
                            if ((isinstance(v, tuple) and isinstance(v[0], bind.BindValue)) or
                                isinstance(v, bind.BindValue)):
                                send[k] = v.value
                            else:
                                send[k] = v
                        func(**send)

                    handler = functools.partial(on_changed, args, func)
                    value.after_changed += handler

                    def cleanup_trigger(value, handler):
                        value.after_changed -= handler

                    if hasattr(self.view_model, 'on_close'):
                        self.view_model.on_close += lambda value=value, handler=handler: cleanup_trigger(value, handler)

    @Node.node('Styles')
    def push_styles(self, node, parent, params):
        style_args = {}

        for child in node:
            style_args[child.tag] = child.attrib

        self.style_args = style_args

    def shortcut(self, val):
        if val is None:
            return None

        m = val.split('-')
        if len(m) < 2:
            return None

        acc = 0

        for accel in m[:-1]:
            a = 'ACCEL_' + accel.upper()
            o = wx_getattr(a)
            if o is not None:
                acc |= (o)

        return acc, ord(m[-1])

    @Node.node('MenuBar')
    def create_menubar(self, node, parent, params):
        bar = wx.MenuBar()
        parent.GetTopLevelParent().SetMenuBar(bar)

        menu_name = name = node.attrib.get('Name', 'Menu_%d' % self.counter[wx.MenuBar])
        self.counter[wx.MenuBar] += 1
        self.debug_names[bar] = name

        return bar

    def component_process_vars(self, child):
        if child.tag in UiBuilder.components:
            custom_args = list(UiBuilder.components[child.tag]._overrides.items())
        else:
            custom_args = set()
            for n, k in child.attrib.items():
                if len(k) > 2 and k[1] == ':':
                    temp = k.replace(':', '' , 1)[1:-1]
                    t = temp.split('=', 1)
                    if len(t) > 1:
                        default = t[1]
                        child.attrib[n] = k.replace('=%s' % default, '')
                    else:
                        default = None
                    custom_args.add((t[0], default))

        return custom_args

    @Node.node('Component', 'Mixin')
    def register_component(self, node, parent, params):
        name = node.attrib.get('Name')
        parent_type = node.attrib.get('Parent', 'Panel')

        elem = ET.Element(name)
        elem.attrib.update({k: v for k, v in node.attrib.items() if k not in ('Name', 'Parent')})

        if node.tag == 'Mixin' or parent_type == 'None':
            custom_obj = Passthrough()
            custom_obj._type = CustomNodeType.PassParent
        elif name in Control.Registry:
            custom_obj = Control.Registry[name]
            custom_obj._type = CustomNodeType.Control
        else:
            parents = [wx_getattr(parent_type)]
            custom_obj = type(name, tuple(parents), {})
            custom_obj._type = CustomNodeType.Control

        def find_vars(root, first=False):
            overrides = []

            # get everything on the first root
            if first:
                overrides.extend(self.component_process_vars(root))

            for idx, child in enumerate(root):
                custom_args = self.component_process_vars(child)
                overrides.extend(custom_args)
                overrides.extend(find_vars(child))

            return overrides

        custom_arguments = find_vars(node, first=True)

        overrides = {
            re.split('[:\[]', f)[0].split('.')[0]: d
            for f, d in custom_arguments
        }

        # if parent is a defined Xml component, then we need to make sure
        # that its definition is applied first
        if parent_type in UiBuilder.components:
            for c in UiBuilder.components[parent_type]._ctor:
                elem.append(clone_element(c))

        for c in node:
            elem.append(c)

        custom_obj._ctor = elem
        custom_obj._overrides = overrides

        UiBuilder.components[name] = custom_obj

    def auto_radio_menu_items(self, menu, child):
        args = self.eval_args(child.attrib)

        # use child tag names as choices
        if 'Choices' not in args:
            choices = [c.tag for c in child]
        elif isinstance(args['Choices'], bind.BindValue):
            choices = args['Choices'].value
        elif isinstance(args['Choices'], tuple):
            choices = args['Choices'][0].value
        else:
            choices = args['Choices']

        if 'Choice' not in args:
            bind_value = None
        elif isinstance(args['Choice'], bind.BindValue):
            from_ = to_ = lambda v: v
            bind_value = args['Choice']
        elif isinstance(args['Choice'], tuple):
            bind_value, _, to_, from_ = args['Choice']
        else:
            from_ = to_ = lambda v: v
            bind_value = None

        num = menu.GetMenuItemCount()
        if num > 0 and menu.FindItemByPosition(num - 1).Kind != wx.ITEM_SEPARATOR:
            menu.AppendSeparator()

        ids = {}

        menu_name = self.debug_names[menu]

        for choice in choices:
            label = str(choice)
            menu_item = wx.MenuItem(id=wx.ID_ANY, text=label, kind=wx.ITEM_RADIO)
            self.menu_ids['%s.radio.%s' % (menu_name, label)] = menu_item.Id
            self.debug_names[menu_item] = '%s_on_radio_%s' % (menu_name, child.tag)

            menu.Append(menu_item)
            ids[menu_item] = choice

        if bind_value is not None:
            def update_checks(item_ids):
                value = to_.to_widget(bind_value.value) if to_ else bind_value.value
                for k, v in item_ids.items():
                    k.Check(v == value)
                return 0

            def set_val(item_ids, evt):
                for k, v in item_ids.items():
                    if k.IsChecked():
                        bind_value.value = from_.from_widget(v) if from_ else v
                        return

            auto_dyn = bind.DynamicValue(
                bind_value,
                update=functools.partial(update_checks, ids)
            )
            if DEBUG_BIND:
                print('   Menu radio shadow DynamicValue created for %s' % (
                    (bind_value.name if bind_value.name else bind_value)
                ))

            for menu_item, choice in ids.items():
                menu.Bind(
                    wx.EVT_MENU,
                    functools.partial(set_val, ids),
                    menu_item
                )

                if DEBUG_BIND:
                    print('   - radio setter event bound for %s' % (
                        (bind_value.name if bind_value.name else bind_value)
                    ))

            bind_value.update_target()

        menu.AppendSeparator()

    @Node.node('Menu')
    def create_menu(self, node, parent, params):
        params = params or {}

        if 'menu_parent' not in params and isinstance(parent, wx.Window):
            params['menu_parent'] = parent

        menu = wx.Menu()

        menu_name = name = node.attrib.get('Name', 'Menu_%d' % self.counter[wx.Menu])
        self.counter[wx.Menu] += 1
        self.debug_names[menu] = name
        self._current_menu = menu

        menu_item = None

        for child in node:
            if child.tag == 'Menu':
                self.create_menu(child, menu, params)
            elif child.tag == 'Config':
                self.setup_parent(child, menu, params)
            elif child.tag == 'Radio':
                self.auto_radio_menu_items(menu, child)
            else:
                id_string = 'ID_' + child.attrib.get('id', 'ANY').upper().lstrip('ID_')
                item_id = self.str2py(id_string)

                if child.tag.startswith('___'):
                    item_kind = wx.ITEM_SEPARATOR
                else:
                    kind_string = 'ITEM_' + child.attrib.get('kind', 'NORMAL').upper().lstrip('ITEM_')
                    item_kind = self.str2py(kind_string)

                item_help = child.attrib.get('helpString', child.attrib.get('help', ''))

                name = child.attrib.get('Label', child.tag)

                menu_item = wx.MenuItem(id=item_id, text=name, kind=item_kind, helpString=item_help)
                self.debug_names[menu_item] = "%s_on_%s" % (menu_name, child.tag)
                self.menu_ids['%s.%s' % (menu_name, child.tag)] = menu_item.Id

                # build menu item before appending, so things like bitmaps work
                for c in child:
                    self.compile(c, menu_item, params)

                menu.Append(menu_item)

                handler = child.attrib.get('handler')
                if handler is not None:
                    func = self.find_method(handler)
                else:
                    func = None

                # bind events to view object
                mp = None
                if mp not in self.events:
                    self.events[mp] = []

                check_bind = child.attrib.get('Check')
                if item_kind == wx.ITEM_CHECK and check_bind:
                    binding = self.str2py(check_bind)
                    # set up bindings
                    if isinstance(binding, tuple):
                        binding, evt, to_, from_ = binding
                        if evt is not None:
                            binding.add_source(
                                menu,
                                evt,
                                menu.IsChecked,
                                transform=from_,
                                arguments={'bind_to': menu_item, 'id': menu_item.Id}
                            )
                        binding.add_target2(
                            menu,
                            menu.Check,
                            transform=to_,
                            id=menu_item.Id,
                            check=binding
                        )
                    # take current value
                    elif isinstance(binding, bind.BindValue):
                        menu.Check(menu_item.Id, binding.value)
                    else:
                        menu.Check(menu_item.Id, binding)
                else:
                    self.events[mp].append(('EVT_MENU', func, menu_item))

                scut = self.shortcut(child.attrib.get('Shortcut'))
                if scut is not None:
                    insert_id = menu_item.GetId()
                    acc, char = scut
                    self.accel_table.append((acc, char, insert_id))

        if parent is not None and isinstance(parent, wx.Menu):
            appended = parent.Append(wx_getattr(child.attrib.get('id', 'ID_ANY')), node.attrib.get('Name'), menu)
        elif parent is not None and isinstance(parent, wx.MenuBar):
            appended = parent.Append(menu, menu_name)
        else:
            params.pop('menu_parent', None)
            self.constructed = menu

        enabled = node.attrib.pop('Enabled', '')
        if enabled and isinstance(parent, wx.Menu):
            self.create_parent_func_binding(parent, 'Enable', params, id=str(appended.Id), enable=enabled)

        self.children[menu_name] = menu

    @Node.node('MainToolBar')
    def wx_toolbar(self, node, parent, params):
        self.create_toolbar(node, parent.GetTopLevelParent(), params, top=True)

    def create_parent_func_binding(self, parent, function, params, **kwargs):
        inner = ET.Element(function)
        inner.attrib.update(kwargs)
        self.setup_parent_node(inner, parent, params)

    @Node.node('ToolBar')
    def create_toolbar(self, node, parent, params, top=False):
        kwargs = self.eval_args(node.attrib)

        bar = wx.ToolBar(parent, **kwargs)

        if top:
            parent.SetToolBar(bar)

        menu_name = name = node.attrib.get('Name', 'ToolBar_%d' % self.counter[bar.__class__])
        self.counter[bar.__class__] += 1
        self.debug_names[bar] = name

        for child in node:
            if child.tag == 'Config':
                self.setup_parent(child, bar, params)
                continue

            handler = child.attrib.pop('handler', '')
            enabled = child.attrib.pop('enabled', '')

            if wx_hasattr(child.tag):
                obj = self.compile(child, bar)
                item = bar.AddControl(obj)
            else:
                tid = child.attrib.get('id', 'ANY')
                if tid in self.menu_ids:
                    item_id = self.menu_ids[tid]
                else:
                    id_string = 'ID_' + child.attrib.get('id', 'ANY').upper().lstrip('ID_')
                    item_id = self.str2py(id_string)

                if child.tag.startswith('___'):
                    bar.AddSeparator()
                    continue
                else:
                    kind_string = 'ITEM_' + child.attrib.get('kind', 'NORMAL').upper().lstrip('ITEM_')
                    item_kind = self.str2py(kind_string)

                item_help = child.attrib.get('helpString', child.attrib.get('help', ''))

                long_help = child.attrib.get('longHelp', '')

                bitmap = self.str2py(child.attrib.get('bitmap', ''))
                if not isinstance(bitmap, wx.Bitmap):
                    bitmap = wx.Bitmap()

                bitmap_disabled = self.str2py(child.attrib.get('disabled', ''))
                if not isinstance(bitmap_disabled, wx.Bitmap):
                    bitmap_disabled = wx.NullBitmap

                name = child.attrib.get('Label', child.tag)

                item = bar.AddTool(
                    toolId=item_id,
                    label=name,
                    bitmap=bitmap,
                    bmpDisabled=bitmap_disabled,
                    kind=item_kind,
                    shortHelp=item_help,
                    longHelp=long_help,
                )

                self.setup_parent(child, item, params)

                if item_kind == wx.ITEM_DROPDOWN:
                    dropdown_menu = child.attrib.get('menu')
                    if dropdown_menu:
                        b = self.eval_args({'menu': dropdown_menu})
                        if isinstance(b['menu'], wx.Menu):
                            bar.SetDropdownMenu(item.Id, b['menu'])

            if enabled:
                inner = ET.Element('EnableTool')
                inner.attrib['toolId'] = str(item.Id)
                inner.attrib['enable'] = enabled
                self.setup_parent_node(inner, bar, params)

            self.debug_names[item] = "%s_on_%s" % (menu_name, child.tag)
            self.menu_ids['%s.%s' % (menu_name, child.tag)] = item.Id

            if handler:
                func = self.find_method(handler)
            else:
                func = None

            # scut = self.shortcut(child.attrib.get('Shortcut'))
            # if scut is not None:
            #     insert_id = menu_item.GetId()
            #     acc, char = scut
            #     self.accel_table.append((acc, char, insert_id))

            if bar not in self.events:
                self.events[bar] = []
            self.events[bar].append(('EVT_TOOL', func, item))

        #self.setup_parent(node, bar, params, item=bar)

        bar.Realize()

    @Node.filter(lambda n: n.attrib.get('AutoImport', 'false').lower() == 'true')
    def extra_auto_import(self, node, parent, params):
        node.attrib.pop('AutoImport')

        module, class_name = node.tag.rsplit('.', 1)
        importlib.import_module(module)
        return self.wx_node(
            node,
            parent,
            params,
            root=sys.modules[module],
            tag=class_name,
            skip_sizer=True
        )

def load_components(filename : str):
    """
        load defined components from the filename. this is used for
        loading library xml files that are not used for an actual UI.
    """

    builder = UiBuilder(filename)
    builder.init_build(None)

    import inspect
    stack = inspect.stack()
    caller = stack[1]
    calling_module = inspect.getmodule(caller[0])

    is_main = calling_module.__name__ == '__main__'
    module_name = calling_module.__name__

    tree = ET.parse(filename)
    tree.getroot()
    for component in tree.findall('.//Component'):
        # change name, so it's referred to the same name as the class
        if not is_main:
            component.attrib['Name'] = '%s.%s' % (module_name, component.attrib['Name'])
        builder.register_component(component, None, {})

    for mixin in tree.findall('.//Mixin'):
        builder.register_component(component, None, {})

    for bmp in tree.findall('.//Bitmaps'):
        UiBuilder.run_at_start(builder.images, bmp, None, {})

    for ico in tree.findall('.//Icons'):
        UiBuilder.run_at_start(builder.icons, ico, None, {})

class ViewModel(object):
    def __init__(self, defer: bool=False, parent : Optional[wx.Object] = None) -> None:
        self._compat_flags = {}
        self.on_close = Event('on_close')
        self.initialize()
        if not defer:
            self.build(parent=parent)

    def initialize(self):
        """
            Runs prior to constructing the Ui.
            Create instance specific properties here
        """
        pass

    def ready(self):
        """
            Runs after the UI is ready
        """
        pass

    def close(self, evt: wx.Event):
        """
            Runs any associated on_close events, and then
            destroys the view
        """
        if evt.CanVeto() and not self.can_close():
            evt.Veto()
            return

        self.on_close()
        self.view.Destroy()

    def can_close(self) -> bool:
        """
            Called when closing a frame to see if the operation
            should be cancelled.
        """
        return True

    def inspect(self):
        """
            Launches the wx inspection tool
        """
        import wx.lib.inspection
        wx.lib.inspection.InspectionTool().Show()

    def build(self, parent: wx.Object=None, sizer_flags=None):
        """
            Builds the UI from the XML file for this ViewModel.
            When the UI is built, events from the view are wired up
            to this view model.
        """

        start = time.perf_counter()

        if not os.path.exists(self.filename):
            raise IOError('XML file not found: %s' % self.filename)

        ui = UiBuilder(self.filename)
        view = self.view = ui.build(self, parent=parent, sizer_flags=sizer_flags)

        if view is not None:
            events = [v for v in view.__dict__.values() if isinstance(v, Event)]
            for event in events:
                if hasattr(self, event.name):
                    event += getattr(self, event.name)

            self.view = view

            self.view.Bind(wx.EVT_CLOSE, self.close)

            end = time.perf_counter()

            for v in ui.values_to_update:
                v.touch()

            if self.view is not None:
                self.ready()

            if DEBUG_TIME:
                print('%s construction time: %.2f seconds' % (self.filename, (end - start)))


        if DEBUG_ERROR:
            for ex, node, parent, trace in ui.construction_errors:
                if DEBUG_ERROR_UI:
                    ErrorViewModel.instance().add_error(
                        node.tag,
                        self.filename,
                        parent,
                        ex,
                        trace
                    )
                else:
                    print(node.tag, self.filename, parent.__class__.__name__, ex)
                    print(trace)
                    print('-' * 10)


            if len(ui.construction_errors) and DEBUG_ERROR_UI:
                ErrorViewModel.instance().view.Show()

        return self.view

    @invoke_ui
    def show(self, pos):
        self.view.Show(True)
        self.view.Position = (0, 0)
        self.view.Size = (100, 100)

class GenericViewModel(ViewModel):
    """
        Useful for prototyping Ui before creating ViewModel,
        used when no ViewModel was registered for file
    """
    def __init__(self, filename, defer=False):
        self.filename = filename
        super().__init__(defer=defer)


@Ui('errors.xml')
class ErrorViewModel(ViewModel):
    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = ErrorViewModel()
        return cls._instance

    err_list : wx.ListCtrl
    _instance = None

    def initialize(self):
        self.file_headers = ['File', 'Node', 'Parent', 'Error', 'Error Text']
        self.msg_detail = []
        self.selection = bind.BindValue(0)

    def get_message_detail(self, v: int):
        if 0 <= v < len(self.msg_detail):
            return self.msg_detail[v]
        else:
            return ''

    def row_select_str(self, v: int):
        if v >= 0:
            return 'Error %d' % (v + 1)
        else:
            return ''

    def ready(self):
        self.err_list = self.view.widgets['error_list']

    @invoke_ui
    def add_error(self, node, filename, parent, exception, tb):
        self.err_list.AppendItem([
            filename,
            getattr(node, 'tag', node),
            parent.__class__.__name__,
            exception.__class__.__name__,
            str(exception)
        ], self.err_list.GetItemCount())
        self.msg_detail.append(tb)

        # go ahead and select the first row, if this is the first item
        if self.err_list.SelectedRow == -1:
            self.err_list.SelectRow(0)

    @block_ui
    def clear(self):
        self.err_list.DeleteAllItems()
        self.msg_detail = []

    def delete_all(self, evt):
        self.clear()

def run(view_model: ViewModel, *args, inspect=False, **kwargs):
    """
        Creates a wx.App, builds the given view_model and then
        starts the UI thread.
        The constructed view is expected to be a Frame.
        When the UI thread ends, the DataStore is saved to
        a file (if any values are serialized).
    """
    app = wx.App()
    view = view_model(*args, **kwargs)
    view.view.Show(True)

    if inspect:
        view.inspect()

    app.MainLoop()
    bind.DataStore.save()
