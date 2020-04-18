## 1. Hello, World!

This example shows how to start building a UI with wxml.

### Getting Started

`hello.xml` contains a simple UI, shown below.

```xml
<Frame>
    <StaticText label="Hello, world!" />
</Frame>
```

All wxPython interfaces must contain a top level Frame window, and that is expressed with the `<Frame>` element.
All elements will use their parent object when built.

The `<StaticText>` element uses the Frame object as its parent, and gives the `label` value to its constructor.

The equivalent Python code for the above UI is:

```python
import wx

app = wx.App()

frame = wx.Frame(None, wx.ID_ANY)
text = wx.StaticText(frame, label='Hello, world')

frame.Show(True)

app.MainLoop()
```

### Running wxml

The `wxml` package can build interfaces directly when given an Xml filename.

This can be done with the following command:
```bash
<python> -m wxml hello.xml
```

After running the above command, you should now see a window like the one below.

![picture of hello.xml running](screenshots/01.png)

### Running in Design Mode

When you're starting to design a user interface, you probably don't want to
have to keep running the above command when you make changes to file.

Fortunately, wxml can be told to watch the given filename for changes and
when it detects modifications, it will automatically rebuild the UI for you.

Run `<python> -m wxml --design hello.xml` or `<python> -m wxml -d hello.xml`

Now, open `hello.xml` in your text editor of choice and change the StaticText's text attribute
to something else (`"HELLO, WORLD!"`). After you save the file, the UI will rebuilt automatically and
you can see your changes.

![picture of hello.xml in design mode after xml file was changed](screenshots/02.png)

### Error Viewer

If you're running in design mode, you may make an edit that will result in errors
when the UI is built. The module comes in a built-in error viewer that can be shown
by passing in a debug flag argument.

Run `<python> -m wxml --design --debug-flags ERROR hello.xml`.
