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
from typing import NamedTuple
import logging

from wxml.event import Event
from wxml.decorators import invoke_ui
import wxml.bind as bind

DEBUG_EVAL = False
DEBUG_ATTR = False
DEBUG_COMPILE = False
DEBUG_TIME = False
DEBUG_BIND = False
DEBUG_ERROR = False
DEBUG_EVENT = False

def full_class_path(class_type: type):
    module = '' if class_type.__module__ == "__main__" else '%s.' % class_type.__module__
    return '%s%s' % (module, class_type.__qualname__)

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
                    Control.Registry[full_class_path(use_name)] = obj
            Ui._imported.add(class_obj.__module__)

        return class_obj

class Control(object):
    Registry = {}

    def __init__(self, class_obj):
        Control.Registry[full_class_path(class_obj)] = class_obj

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

def nested_getattr(name, root=None, default=None):
    tokens = name.split('.')
    if root is None:
        try:
            obj = sys.modules[tokens[0]]
        except KeyError:
            return None
        start = 1
    else:
        obj = root
        start = 0

    for t in tokens[start:]:
        if not hasattr(obj, t):
            return default
        obj = getattr(obj, t)

    return obj

def nested_hasattr(name):
    return nested_getattr(name) is not None

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
    components = {}

    def __init__(self, filename):
        self.filename = filename

    def build(self, view_model, parent=None, sizer_flags=None):
        self.view_model = view_model
        self.counter = collections.defaultdict(lambda: 0)
        self.debug_names = {}
        self.events = {}
        self.children = {}
        self.accel_table = []
        self.loop_vars = {}
        self.construction_errors = []

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
        obj.widgets = {}

        for widget, name in self.debug_names.items():
            obj.widgets[name] = widget

        for widget, events in self.events.items():
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

        if hasattr(obj, 'SetAcceleratorTable') and len(self.accel_table):
            obj.SetAcceleratorTable(wx.AcceleratorTable(self.accel_table))

        return obj

    def str2py(self, value, bare_class=False):
        if value and value[0] == '$':
            value = value[1:]
            not_a_class = False
        else:
            not_a_class = True

        retval = value
        resolved = 'str'

        bind_expr = r'^\(([_A-Za-z0-9\.]+)(?:\[([_A-Za-z0-9\.]+)\])?(?:\:(EVT_[A-Z_]+)(?:\[([_A-Za-z0-9\.]+)\])?)?\)$'
        tokens = re.search(bind_expr, value)

        # one or two way binding
        if not_a_class and tokens is not None:
            key = tokens.group(1)
            to_widget = tokens.group(2)
            event = tokens.group(3)
            event = None if event is None else wx_getattr(event)

            transform = None
            receiver = None

            if to_widget is not None:
                transform = self.str2py(to_widget, bare_class=True)
                if not isinstance(transform, bind.Transformer):
                    transform = bind.ToWidgetGenericTransformer(None, transform)

            from_widget = tokens.group(4)
            if from_widget is not None:
                receiver = self.str2py(from_widget, bare_class=True)
                if not isinstance(receiver, bind.Transformer):
                    receiver = bind.FromWidgetGenericTransformer(None, receiver)

            binding = self.str2py(key, bare_class=True)

            if binding is None and hasattr(self, 'overrides'):
                t, *k = key.split('.')
                k = '.'.join(k)
                binding = nested_getattr(k, self.overrides.get(t))

            if binding is not None and isinstance(binding, bind.BindValue):
                return binding, event, transform, receiver
        # one time binding
        elif not_a_class and len(value) and value[0] == '{' and value[-1] == '}':
            key = value.lstrip('{').rstrip('}')
            if key in self.loop_vars:
                resolved = 'loop_var'
                return self.loop_vars[key]

            if hasattr(self, 'overrides'):
                t, *k = key.split('.')
                if t in self.overrides:
                    obj = self.overrides.get(t)
                    if k and obj is not None:
                        obj = nested_getattr('.'.join(k), obj)

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

            if key not in exclude and (prefix is None or key.startswith(prefix)):
                evaled[key] = self.str2py(value)
                if DEBUG_ATTR:
                    print('   Attr={0} Input="{1}" Value={2}'.format(key, value, evaled[key]))

        return evaled

    def compile(self, node, parent=None, params=None, inject=None):
        action = Node.action_for(node)

        if DEBUG_COMPILE:
            print(' %s.%s' % (os.path.splitext(os.path.basename(self.filename))[0], node.tag), '->', action.__name__ if action is not None else '[no action]')

        try:
            obj = action(self, node, parent, params)
        except Exception as ex:
            print('ERROR', '[tag: %s]' % node.tag, '[parent: %s]' % parent, 'exception:', ex)
            import traceback
            traceback.print_exc()
            self.construction_errors.append([ex, node, parent, traceback.format_exc()])
            return

        if obj is None:
            return
        elif isinstance(obj, tuple) or isinstance(obj, list):
            parent_obj, params2 = obj
            params = params or {}
            params.update(params2)
        else:
            parent_obj = obj
            params = {}

        if parent_obj is None:
            return

        if inject is not None:
            parent_obj.__dict__.update(inject)

        for child in node:
            obj = self.compile(child, parent_obj, params=params)

        post_action = NodePost.action_for(node)
        if post_action is not None:
            try:
                post_action(self, node, parent_obj, params)
            except Exception as ex:
                print('ERROR', '[tag post: %s]' % node.tag, '[parent: %s]' % parent, 'exception:', ex)
                import traceback
                traceback.print_exc()

        return parent_obj

    @Node.node('Namespace')
    def namespace(self, node, parent, params):
        return 1

    @Node.filter(lambda n: n.tag in UiBuilder.components)
    def create_component(self, node, parent, params):
        obj = UiBuilder.components[node.tag]
        true_node = obj._ctor
        overrides = obj._overrides

        use_node = ET.Element('CustomWx')
        use_node.attrib['_class'] = node.tag
        use_node.attrib.update({
            k: v
            for k, v in node.attrib.items()
            if k not in obj._overrides}
        )
        for c in true_node:
            use_node.append(c)

        children = [c for c in node]

        for child in children:
            use_node.append(child)

        if not hasattr(self, 'overrides'):
            overrides = {
                name: self.str2py(node.attrib.get(name, getattr(self, 'overrides', {}).get(name, default or '')))
                for name, default in overrides.items()
            }

            self.overrides = overrides
            within = False
        else:
            within = True

        obj = self.compile(use_node, parent, params)
        if isinstance(obj, (wx.Panel, wx.Frame)):
            self.wx_setsizer(use_node, obj, params)

        for child in children:
            use_node.remove(child)

        if not within:
            del self.overrides

        return None


    @Node.filter(lambda n: hasattr(wx, n.tag) and issubclass(getattr(wx, n.tag), wx.DropTarget))
    def create_drop_target(self, node, parent, params):
        class_obj = wx_getattr(node.tag)
        name = node.attrib.get('name')
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
    def setup_parent(self, root, parent, params):
        name = root.attrib.get('Item')
        if name == 'sizer':
            parent = parent.Sizer

        for func in root:
            if func.tag == 'Loop':
                self.loop_over(func, parent, params)
            else:
                call = getattr(parent, func.tag)

                # one-way bind to property, will update BindValue when event is fired
                if 'Bind' in func.attrib:
                    binding, event, transform, receiver = self.str2py(func.attrib['Bind'])
                    self.binding_hook(binding, parent, func.tag, event=event, receiver=receiver, can_update=False)
                elif call is not None and callable(call):
                    args = self.eval_args(func.attrib, exclude=["Name"])

                    bindings = {
                        k: v
                        for k, v in args.items()
                        if isinstance(v, tuple) and isinstance(v[0], bind.BindValue)
                    }

                    call_args = {k: v for k, v in args.items() if k not in bindings}
                    binding_args = {k: v for k, v in call_args.items()}

                    for k, (b, e, t, v) in bindings.items():
                        if t is not None:
                            call_args[k] = t.to_widget(b.value)
                        else:
                            call_args[k] = b.value

                        binding_args[k] = b

                    obj = call(**call_args)

                    for name, (binding, event, transform, receiver) in bindings.items():
                        self.binding_hook(
                            binding,
                            parent,
                            func.tag,
                            event=event,
                            transformer=transform,
                            all_args=binding_args,
                            receiver=receiver)

                    name = func.attrib.get("Name")
                    if name is not None:
                        self.debug_names[obj] = name

                    self.setup_parent(func, obj, params)
                elif call is not None or func.tag in dir(parent):
                    set_to = self.eval_args({'value': func.attrib.get('value')})['value']
                    if isinstance(set_to, tuple) and isinstance(set_to[0], bind.BindValue):
                        binding, event, transformer, receiver = set_to
                        self.binding_hook(
                            binding,
                            parent,
                            func.tag,
                            event=event,
                            transformer=transformer,
                            receiver=receiver
                        )
                    else:
                        setattr(parent, func.tag, set_to)

    def binding_hook(self, binding: bind.BindValue, parent, attr_name, event=None, transformer=None, all_args=None, receiver=None,
        can_update=True):
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
                '<%s(%s):%s>'  % (binding.name or '',  binding.__class__.__name__, hex(id(binding))),
                parent.__class__.__name__,
                attr_name,
                bind_type
            ))

        if to_widget:
            binding.add_target(parent, attr_name, transform=transformer, arguments=arguments)
        if from_widget:
            binding.add_source(parent, event, attr_name, transform=receiver)
        if can_update:
            binding.update_target(None)

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

    @Node.filter(lambda n: hasattr(wx, n.tag) and issubclass(getattr(wx, n.tag), wx.Sizer))
    def wx_create_sizer(self, node, parent, params):
        class_obj = nested_getattr(node.tag, root=wx)
        this_obj = class_obj(**self.eval_args(node.attrib, exclude=self.SizerFlags(class_obj)))

        sizer_flags = self.eval_args(node.attrib, only_args=self.SizerFlags(class_obj))
        #params['default-sizer'] = sizer_flags

        this_obj.default_flags = sizer_flags
        parent.SetSizer(this_obj)

        var_name = '%s_%d' % (node.tag, self.counter[class_obj])
        self.counter[class_obj] += 1
        self.debug_names[this_obj] = var_name

        return parent, params

    @Node.node('CustomWx')
    def wx_custom(self, node, parent, params):
        return self.wx_node(node, parent, params, tag=node.attrib.pop('_class'))

    @Node.filter(lambda n: n.tag in Control.Registry)
    def wx_custom_control(self, node, parent=None, params=None, root=wx, tag=None):
        return self.wx_node(node, parent, params, actual_obj=Control.Registry[node.tag])

    @Node.filter(lambda n: hasattr(wx, n.tag))
    def wx_node(self, node, parent=None, params=None, root=wx, tag=None, actual_obj=None):
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

        args = self.eval_args(style_args, exclude=self.SizerFlags(parent) + ['Name'])
        args.update(self.eval_args(node.attrib, exclude=self.SizerFlags(parent) + ['Name']))

        bindings = {
            k: v
            for k, v in args.items()
            if isinstance(v, tuple) and isinstance(v[0], bind.BindValue)
        }

        for k, (b, e, t, r) in bindings.items():
            args[k] = str(b)

        this_obj = class_obj(parent, **args)
        if hasattr(this_obj, 'SetDoubleBuffered'):
            this_obj.SetDoubleBuffered(True)

        for name, (binding, event, transform, receiver) in bindings.items():
            self.binding_hook(
                binding,
                this_obj,
                name.title(),
                event=event,
                transformer=transform,
                receiver=receiver
            )

        var_name = node.attrib.get('Name', '%s_%d' % (tag or node.tag, self.counter[class_obj]))
        self.counter[class_obj] += 1
        self.debug_names[this_obj] = var_name
        self.children[var_name] = this_obj

        if parent is not None and parent.Sizer is not None:
            sizer_args = {k: v for k, v in getattr(parent.Sizer, 'default_flags', {}).items()}
            widget_args = self.eval_args(style_args, only_args=self.SizerFlags(parent.Sizer))
            overrides = self.eval_args(node.attrib, only_args=self.SizerFlags(parent.Sizer))
            sizer_args.update(widget_args)
            sizer_args.update(overrides)

            if all(hasattr(wx.SizerFlags, f) for f in sizer_args):
                s = wx.SizerFlags()
                for key, value in sizer_args.items():
                    use_flags = True
                    f = getattr(s, key)
                    if key.lower() != 'expand':
                        arg = [value] if not isinstance(value, list) and not isinstance(value, tuple) else value
                        s = f(*arg)
                    else:
                        s = f()
                parent.Sizer.Add(this_obj, s)
            else:
                parent.Sizer.Add(this_obj, **{k.lower(): v for k, v in sizer_args.items()})
        else:
            params['sizer'] = None

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

        return method

    @Node.filter(lambda n: n.tag.startswith('wx.'))
    def wx_import_node(self, node, parent, params):
        module, class_name = node.tag.rsplit('.', 1)
        importlib.import_module(module)
        return self.wx_node(node, parent, params, root=sys.modules[module], tag=class_name)

    @NodePost.node('Frame', 'Panel')
    def wx_setsizer(self, node, parent, params):
        if parent.Sizer is not None:
            parent.SetSizerAndFit(parent.Sizer)

    @Node.node('View')
    @Node.filter(lambda n: n.tag in Ui.Registry)
    def include_view(self, node, parent, params):
        if node.tag == 'View':
            filename = node.attrib.get('view')
        else:
            filename = node.tag

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

        self.debug_names[constructed.view] = name
        self.children[name] = constructed.view

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

    @Node.node('Component')
    def register_component(self, node, parent, params):
        name = node.attrib.get('Name')
        parent_type = node.attrib.get('Parent', 'Panel')

        elem = ET.Element(name)
        elem.attrib.update({k: v for k, v in node.attrib.items() if k not in ('Name', 'Parent')})

        if name in Control.Registry:
            custom_obj = Control.Registry[name]
        else:
            parents = [wx_getattr(parent_type)]
            custom_obj = type(name, tuple(parents), {})

        def find_vars(root):
            overrides = []
            for idx, child in enumerate(root):
                if child.tag in UiBuilder.components:
                    vars = UiBuilder.components[child.tag]._overrides
                else:
                    vars = set()
                    for n, k in child.attrib.items():
                        if len(k) > 2 and k[1] == ':':
                            temp = k.replace(':', '' , 1)[1:-1]
                            t = temp.split('=', 1)
                            if len(t) > 1:
                                default = t[1]
                                child.attrib[n] = k.replace('=%s' % default, '')
                            else:
                                default = None
                            vars.add((t[0], default))

                overrides.extend(vars)
                overrides.extend(find_vars(child))
            return overrides

        overrides = {
            re.split('[:\[]', f)[0].split('.')[0]: d
            for f, d in find_vars(node)
        }

        for idx, child in enumerate(node):
            elem.insert(idx, child)

        custom_obj._ctor = elem
        custom_obj._overrides = overrides

        UiBuilder.components[name] = custom_obj

    @Node.node('Menu')
    def create_menu(self, node, parent, params):
        params = params or {}

        if 'menu_parent' not in params and isinstance(parent, wx.Window):
            params['menu_parent'] = parent

        menu = wx.Menu()
        menu_name = name = node.attrib.get('Name', 'Menu_%d' % self.counter[wx.Menu])
        self.counter[wx.Menu] += 1
        self.debug_names[menu] = name

        for child in node:
            if child.tag in 'Menu':
                self.create_menu(child, menu, params)
            else:
                id_string = 'ID_' + child.attrib.get('id', 'ANY').upper().lstrip('ID_')
                item_id = self.str2py(id_string)

                if child.tag.startswith('___'):
                    item_kind = wx.ITEM_SEPARATOR
                else:
                    kind_string = 'ITEM_' + child.attrib.get('kind', 'NORMAL').upper().lstrip('ITEM_')
                    item_kind = self.str2py(kind_string)

                item_help = child.attrib.get('help', '')

                name = child.attrib.get('Label', child.tag)
                menu_item = menu.Append(item_id, name, kind=item_kind, helpString=item_help)
                self.debug_names[menu_item] = "%s_on_%s" % (menu_name, child.tag)

                p = child.find('Config')
                if p:
                    self.setup_parent(p, menu_item, params)

                handler = child.attrib.get('handler')
                if handler is not None:
                    func = self.find_method(handler)
                else:
                    func = None

                scut = self.shortcut(child.attrib.get('Shortcut'))
                if scut is not None:
                    insert_id = menu_item.GetId()
                    acc, char = scut
                    self.accel_table.append((acc, char, insert_id))

                mp = parent
                if mp not in self.events:
                    self.events[mp] = []

                self.events[mp].append(('EVT_MENU', func, menu_item))

        if parent is not None and isinstance(parent, wx.Menu):
            parent.Append(wx_getattr(child.attrib.get('id', 'ID_ANY')), node.attrib.get('Name'), menu)
        elif parent is not None and isinstance(parent, wx.MenuBar):
            parent.Append(menu, menu_name)
        else:
            params.pop('menu_parent', None)
            self.children[menu_name] = menu
            self.constructed = menu


class ViewModel(object):
    def __init__(self, defer: bool=False) -> None:
        self.on_close = Event('on_close')
        self.initialize()
        if not defer:
            self.build()

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
        self.on_close()
        self.view.Destroy()

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

            if DEBUG_TIME:
                print('%s construction time: %.2f seconds' % (self.filename, end - start))


        if DEBUG_ERROR:
            for ex, node, parent, trace in ui.construction_errors:
                ErrorViewModel.instance().add_error(
                    node,
                    self.filename,
                    parent,
                    ex,
                    trace
                )

            if len(ui.construction_errors):
                ErrorViewModel.instance().view.Show()

        if self.view is not None:
            self.ready()

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

    @invoke_ui
    def clear(self):
        self.err_list.DeleteAllItems()
        self.msg_detail = []

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
