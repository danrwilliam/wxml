# wxml

**wxml** is a library for constructing wxPython user interfaces by defining them in a Xml file. Its purpose is to enable streamlined UI development.

## Xml Structure

The basic flow of the Xml document creates objects at each node (depending on what the node is). The object constructed for that node is then passed down to each of its child nodes. This parent object will often be used as the first argument to children's constructors.

Objects with the ```Name``` attribute will be available in the constructed view's namespace.

```xml
<Frame>
    <Panel>
        <Button label="Hello world" Name="button" />
    </Panel>
</Frame>
```

In this example, the Frame object is constructed and passed down to the Panel. The Panel object uses its parent (the Frame) as the first argument to its constructor. The Panel object is then passed down to the Button, and used in its constructor.

### Arguments

This section describes how to declare arguments to functions and constructors in the xml file.

Arguments are specified by their name to pass to methods as keyword arguments. The `Name` attribute is reserved to be used as the widget name. When constructing widgets, the arguments to be passed to the containing sizer are title cased.

```xml
<Button label="Test" Name="widget_name" Border="ALL, 2" />
```

#### Name

The ```Name``` attribute is reserved for use. This is the name that the widget is accessible in the `view.widgets` dictionary after building the UI.

### Named Nodes

This section defines the custom nodes.

#### Config

This node switches from the usual flow of passing down the parent object to child objects, and enables the calling of methods and settings of values in the parent object. This allows customization of the object that is not available in the constructor.

Both members and functions can be used in this section. If the item is a member, then the ```value``` attribute is used.

```xml
<Button>
    <Config>
        <Label value="button label">
    </Config>
</Button>
```

#### Import

With this node, Python modules can be imported.

#### EventBindings

This node switches from the usual flow, to enable the binding of events to the parent object. The events are expected to be of type ```wx.Event```.

Subscribers to these events can be set up in 2 ways. In the following example, an event called ```test_on_button``` will be created in the constructed view object. The ViewModel will be searched for a method called ```test_on_button```, if it does it will automatically be bound to the event. Alternatively, the ```handler``` attribute can be used to tell the ViewModel what to subscribe to. The second binding will automatically bind the event to the ```pushed``` method. This method is expected in the ViewModel, if it does not exist, no error will be raised.

```xml
<Button Name="test">
    <EventBindings>
        <EVT_BUTTON />
        <EVT_BUTTON handler="pushed">
    </EventBindings>
</Button>
```

#### Styles

This allows for the passing of arguments to all objects of a certain type. These arguments are used in the constructor or when adding to the sizer.

```xml
<Styles>
    <Button Border="ALL, 50" />
</Styles>

<Button label="Test" />
```


#### View

This instantiates an instance of a ```wxml.ViewModel```.

This is done by specifying the name of the view (xml filename). The registered View is then constructed.

```xml
<View view="imported_view.xml" Name="imported" />
```


#### Bitmaps, Icons

Bitmaps and icons can be loaded in the following way. Once loaded, they can be accessed using
`wxml.Resources` (a static instance).

Please note that absolute paths on Windows (`G:\path\name`) will need to change to UNC-style paths (`G$\path\name`).

```xml
<Frame>
    <Bitmaps>
        <Add path="button1.bmp" />
        <Add path="button2.bmp" mask="GREEN" />
        <AddMany path="buttons_*.bmp" />
    </Bitmaps>

    <Icons>
        <Add path="app_icon.icon" />
    </Icons>

    <Button>
        <Config>
            <Bitmap value="{Bitmaps.button1}" />
        </Config>
    </Button>

    <Config>
        <Icon value="{Icons.app_icon}" />
    </Config>
</Frame>
```

#### ShowIconStandalone

This makes the application icon appear separately, if running as a Python script.

Requires `ctypes` module.

#### Component

This defines a custom component. See the section below for more detail.

#### Menu

This creates a menu. The creation of the menu items is streamlined from the usual widget creation.

The name of the node can serve as the menu item's label. A event handler (`EVT_MENU`) can be attached
with the `handler` attribute. Binding a value to the `EVT_MENU` event will not work.

A shortcut can be created automatically for the menu item with the `Shortcut` attribute. This expects
a modifier and a character.

```xml
<Menu Name="context_menu">
    <Open>
        <Config>
            <Enabled value="(selections[can_open])" />
        </Config>
    </Open>
    <Clone Shortcut="CTRL-C" handler="clone_active" />
</Menu>
```

#### MenuBar

This creates a Menu bar for the frame. Creating the menu items follows the same pattern as with `Menu`.


#### Mixin

This is similar to a Component except that it operates on a single control.

```xml
<Mixin Name="TrackDisable">
    <Config>
        <!-- UiState is a BindValue available in the ViewModel -->
        <Enabled value="(UiState)" />
    </Config>
</Mixin>

<Mixin Name="Click">
    <EventBindings>
        <EVT_BUTTON handler="{:action}" />
    </EventBindings>
</Mixin>

<Button label="Click">
    <TrackDisable />
    <Click on="{show}" />
</Button>
```

The two defined mixins allow common customizations to be encapsulated and reused.

#### ToolBar and MainToolBar

Create a toolbar.

MainToolBar will create the tool bar and set it for the top level parent.

Dropdown tools can have their menu set with `menu` attribute. Tools can be enabled or disabled with the
`enabled` attribute (which calls `EnableTool` with that tool's ID).

Other controls can be added as well.

```xml
<Menu Name="Export">
    <Txt label="&amp;Txt" />
    <Csv label="&amp;Csv" />
    <Xml label="&amp;Xml" />
</Menu>

<MainToolBar>
    <Open id="OPEN" bitmap="wx.ArtProvider.GetBitmap(wx.ART_FILE_OPEN)" />
    <Export bitmap="wx.ArtProvider.GetBitmap(wx.ART_FILE_SAVE)" kind="dropdown"
            menu="{Export}" />

    <Button value="Action" />
</MainToolBar>
```

### Filter Nodes

This section describes special "filter" nodes, that operate on the current node tag's and try to find an appropriate Python object for it.

Unlike the previous section, these node handlers are not tied to a specific node tag. Instead, the value of the node tag is evaluated in sequence until one of these filters matches.

#### create_component

This constructs a previously registered custom component.

The component internally calls `UiBuilder.compile` to handle the construction of the component and its children. The constructed top level object is returned. If the top level is a subclass of Frame or Panel , then `UiBuilder.wx_setsizer` to set up the sizer.

#### create_drop_target

This looks for a subclass of ```wx.DropTarget```.

#### create_sizer

This looks for a subclass of ```wx.Sizer``` and then passes it to all child nodes. If a sizer exists when a child is created, then it will automatically be added to the sizer.

#### wx_node

This looks for the node tag as a member of the ```wx``` module.

To use other wxPython modules, either fully qualify the class name or import the module directly.

Sizer arguments are removed from the arguments passed to the object constructor. These sizer arguments need to be capitalized to be recognized. Default sizer arguments are overwritten by node specific ones.

#### wx_imported

This looks at all imported wxPython modules for the node tag.

Internally, after it finds the class, it will call ```wx_node``` to perform the same processing.

#### wx_import_node

### Post Nodes

This section describes actions for nodes that appear after processing a node and all its children.

#### Frame, Panel

After a Frame or Panel node's children have completed processing, and a ```wx.Sizer``` exists, the sizer object will be set to the frame using ```SetSizerAndFit```.

## Bindings

You no doubt want to be able to bind properties of the UI to your code, without having to updating relevant widgets manually. This section describes how this is done.

Bindings can be used in the following places, constructing a wx object (```wx_node```) and configuring the parent object (```Config```). When calling functions or setting properties, the current bind value is passed in place of the BindValue. The BindValue then registers a target and/or source, and then call ```update_target```.

### One Time

```xml
<Button label="{text}" />
```

The above example will look into the attached view model when the UI is being created, and grab the current value and set the Button's label.

### One Way (Source to Widget)

```xml
<Button label="(text)" />
```

The above example will look for a BindValue named "text" in the view model, and set the label's value to its current value. Whenever the text's value is changed, the Button label will be updated as well.

### One Way (Widget to Source)

```xml
<TextCtrl>
    <Config>
        <Value Bind="(text:EVT_TEXT)" />
    </Config>
</TextCtrl>
```

This example shows how to create a one way binding, where the widget updates the BindValue. The BindValue will receive the updated contents of the text control when its content change, but, modifications to the BindValue will not update the widget.

The separate ```Bind``` attribute is required to tell the BindValue to receive updates and not send them to the widget.

### Two Way

```xml
<TextCtrl value="(text:EVT_TEXT)" />
```

The above example will subscribe to the BindValue to be notified when it changes. Additionally, the wxPython event after the colon will notify the BindValue when it needs to update its internal value. An event has to be specified for two-way binding to work.

The event is required so that the BindValue knows when the widget's attribute changes.

When ```update_target``` is called due to a subscribed event firing, the responsible widget is excluded from the ```update_target``` call.

### Transformers

The value you are binding to may not match the type expected by the widget, or you may want to perform processing on the value before updating the widget or after getting the widget's changed value. This is possible by specifying a function or Transformer class to handle these conversions. If a function is specified, then it will be wrapped in ```bind.ToWidgetGenericTransformer``` or ```bind.FromWidgetGenericTransformer```.

Customer transformers shall inherit from the ```bind.Transformer``` class. The BindValue object is available in this class, so extra processing can be done with that information.

```xml
<TextCtrl value="(text:EVT_TEXT[str.upper])" />
<Gauge>
    <Config>
        <Value value="(text[len])">
    </Config>
</Gauge>
```

This example ties a Gauge's value to the length of a string. Editing the contents of the TextCtrl would change the size of the gauge.

### DynamicValue

You may want to compute a value based on the values of other BindValues, and update that property automatically when one of its dependencies changes.

```python
a = bind.BindValue(10)
b = bind.BindValue(20)

def add():
    return a.value + b.value

c = bind.DynamicValue(a, b, update=add)
```

Whenever `a` or `b` are changed, the value of `c` will be updated.

### ArrayBindValue



### value_changed Event

When the BindValue's value is changed, the `value_changed` event handler is fired. This occurs before the updates are sent out to any BindValue targets. This can be useful to do other work that is needed with the new value, but does not warrant a BindValue to do so. Subscribed methods should not modify the BindValue.

### Data Persistence

BindValues can be persisted by passing `serialize=True` when constructing. The bind value's will then be stored in a Json file, and read when starting up the application again. A name for the bind value must
be specified if serializing.

If the Json file does not exist, then the BindValue will stay with the `value` that it was given, functioning in this situation as the default value.

### Putting it all together

This shows a simple example of linking a StaticText and TextCtrl to the same bind value. Changing the TextCtrl's contents will update the StaticText appropriately. Clicking the button will set the bind value to the empty string, clearing the TextCtrl's content and changing the StaticText's label to the empty string as well. The Gauge is bound to the text BindValue; however, the value is transformed using ```len()``` before applying the update to the Gauge's Value property.

```xml
<Frame>
    <Panel>
        <BoxSizer orient="VERTICAL" Expand="" Border="ALL, 5">
            <StaticText label="Test" />
            <Button label="{message}">
                <EventBindings>
                    <EVT_BUTTON handler="pushed" />
                </EventBindings>
            </Button>
            <TextCtrl value="(text:EVT_TEXT)"  />
            <StaticText label="(text)" />
            <Gauge style="GA_SMOOTH">
                <Config>
                    <Value value="(text[len])" />
                </Config>
            </Gauge>
        </BoxSizer>
    </Panel>

    <Config>
        <SetInitialSize size="500, 500" />
    </Config>
</Frame>
```

```python
@wxml.Ui('grid.xml')
class TestBed(wxml.ViewModel):
    text = BindValue('2345', name='Text', serialize=True)
    message = 'Clear field'

    def pushed(self, evt):
        self.text.value = ''
```

#### wxml Error Viewer

Another example that shows how to use bindings is the Error Viewer. This component appears when a construction error was encountered during the instantiation of a `ViewModel`.

Selecting an line in the ListCtrl will display the stacktrace associated with that error.

This shows how to use one BindValue, and transformer functions to create useful behavior with a minimum of code. The only direct manipulation of a wxPython widget in the view model occurs when adding a new error in `ErrorViewModel.add_error`.

## Custom Components

Custom components allow to compose widgets for reuse. These can be done in two ways: defining it entirely in Xml, or defining a class that is decorated by `wxml.Component`.

### Defining in XML

A reuseable component can be defined entirely in Xml, and used anywhere.

In the component definition, customization can be done like normal with other wx widgets. Here, the customization is flagged by using the colon character to identify the attribute as an construction argument.

The parent class for the component can be specified using the `Parent` attribute (by default it will be `wx.Panel`).

If the parent class is `None`, then no custom type will be created for the component. The parent object will then be passed through to the component's children.

```xml
<Component Name="EasyButton">
    <Button label="{:Label}">
        <EventBindings>
            <EVT_BUTTON handler="{:Action}" />
        </EventBindings>
    </Button>
</Component>

<Component Name="EasyButton2" Parent="Button">
    <Config>
        <Label value="{:Label}" />
        <ToolTip tooltip="{:Tooltip}" />
    </Config>
    <EventBindings>
        <EVT_BUTTON handler="{:Action}" />
    </EventBindings>
</Component>

<EasyButton Label="A button" Action="on_click" />
<EasyButton2 Label="A button" Action="on_click" Tooltip="help text 2" />
```

This example shows the defining of a custom component, that takes two arguments. Care should be taken not to shadow sizer arguments or the parent's constructor arguments. The second component shows how to specify the parent class.

Custom components can also be nested within another custom component. Arguments for the nested component do not need to be specified again when defining the component.


### Codebehind

For components that require more control, it is possible to define a class for the component. This class needs to be decorated with `wxml.Control` decorator.

```python
@wxml.Control
class EasyChoice(wx.Choice):
    def set_choices(self, choices):
        self.ClearItems()
        self.AppendItems(choices)
    def get_choices(self):
        return self.Items
```

```xml
<EasyChoice>
    <Config>
        <set_choices choices="{:my_choices}" />
    </Config>
</EasyChoice>
```

## Details

### Attribute Evaluation Order

This section describes how a string value of an node's attribute is converted into an useable item. This evaluation is performed in ```UiBuilder.str2py(value)```.

Overrides refer to attributes used in the creation of a custom component. Calls to look at nested objects can use the full path (dotted).

If the value is prefixed with a `$`, then the value will be interpreted as an `int`, `float`, or `str`. This avoids
collisions with classes.

- One or two way binding: ```(<bind_value>[<to_transformer>]:<wx_event>[<from_transformer>])```
    - ```bind_value``` is evaluated by calling ```str2py``` recursively.
    - ```wx_event``` (optional) is looked for in the wxPython modules.
    - ```to_transformer``` (optional) is evaluated by calling ```str2py``` recursively.
    - ```from_transformer``` (optional) is evaluated by calling ```str2py``` recursively.
- One time binding: ```{<bind_value>}```
    - ```bind_value``` is looked for in the loop_vars, overrides, view model, and children.
- When requested, looks in the view model class and the overrides.
- Searches all imported wxPython modules and ```UiBuilder.components```.
- Calls ```ast.literal_eval```.
- Converts to ```int``` or ```float```.
- For each imported wxPython modules, calls ```exec``` on the string in the context of that module.
- Returns the original string value, if all previous steps failed.

### Debugging Flags

The following are flags that will echo information about the parsing, evaluation, and construction of an Xml file.

- `wxml.builder.DEBUG_EVAL`: Shows input strings and their evaluated output.
- `wxml.builder.DEBUG_ATTR`: Shows attribute names, their string value, and the evaluated value.
- `DEBUG_COMPILEwxml.builder.`: For each node in the document, shows what `wxml.builder` method was used to process the node.
- `wxml.builder.DEBUG_TIME`: Prints how long the construction process took for each ViewModel built.
- `wxml.builder.DEBUG_BIND`: Shows what bind values are bound to which object, its method or attribute, and the direction of the binding.
- `wxml.builder.DEBUG_ERROR`: When true, the error viewer will display construction errors.
- `wxml.builder.DEBUG_EVENT`: Shows which event handlers were constructed for event bindings, and methods that were subscribed automatically.
- `wxml.bind.DEBUG_UPDATE`: Shows when a bind value is updated.


## Decorators

### wxml.Ui

This decorator associates a `ViewModel` class with an Xml file. The path to the Xml file is relative to the file that the class is defined in.

### wxml.Control

This decorator informs wxml about a custom wxPython widget, so it can be used in an Xml file.

### wxml.invoke_ui

This decorator will make sure that the executing method is run on the main thread, useful
for UI interactions.

If not the main thread, `wx.CallAfter` will be used to execute it on the main thread.


## Command Line Options

This module can be run from the command line as well.

```
usage: __main__.py [-h] [--inspect] [--design] [--verbose] filename

positional arguments:
  filename       Xml file to build and run UI for

optional arguments:
  -h, --help     show this help message and exit
  --inspect, -i  Opens the wxpython inspector after construction
  --design, -d   Watch the named file for changes, and reload if it changes
  --verbose, -v
```