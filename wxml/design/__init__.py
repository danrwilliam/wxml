import wx
import threading
import os
import time
import traceback

import wxml.builder
from wxml.decorators import invoke_ui

class DesignThread(object):
    def __init__(self, filename : str, create, error=None, show_widgets=False):
        self.filename = filename
        self.closed = threading.Event()
        self.view = None
        self.builder = create
        self.show_widgets = show_widgets

        self.error_vm = error or (lambda: None)
        self._error = True

        self._hidden = wx.Frame(None, wx.ID_ANY)

        self.thread = threading.Thread(target=self.watch)

        self.recreate_done = threading.Event()
        self.recreate()

    @property
    def ok(self):
        return self._error

    def close(self, evt: wx.Event):
        evt.StopPropagation()

    def cleanup(self):
        self.closed.set()
        self._hidden.Close()
        if self.thread.is_alive():
            self.thread.join()

    def display_widgets(self, obj):
        print('widgets:')
        if self.show_widgets:
            for name, ctrl in obj.view.widgets.items():
                print(' - %s: %s' % (name, ctrl))            

    @invoke_ui
    def recreate(self):
        if self.view is not None and self.view.view is not None:
            self.position = self.view.view.Position
            self.view.view.Destroy()

        vm = self.error_vm()
        if vm is not None:
            vm.clear()

        try:
            self.view = self.builder(self.filename)
            self.view.on_close += self.cleanup
            self.display_widgets(self.view)
        except Exception as ex:
            dlg = wx.MessageDialog(None, '{ex.__class__.__name__} occured while building\n\n{ex}\n\n{tb}'.format(
                    ex=ex,
                    tb=traceback.format_exc()
                ),
                'Exception: failed to build',
                style=wx.ICON_ERROR | wx.OK | wx.CANCEL
            )
            res = dlg.ShowModal()
            dlg.Destroy()

            if res == wx.ID_CANCEL:
                self.recreate_done.set()
                self.cleanup()
                self._error = False
                return

            self.view = None
        else:
            self._error = True
            if self.view.view is not None:
                self.view.view.Show()
                if hasattr(self, 'position'):
                    self.view.view.Position = self.position

            self.recreate_done.set()

    def watch(self):
        import collections
        Main = collections.namedtuple('Wrap', 'filename')(self.filename)

        self.recreate_done.wait()

        watch_files = {
                f.filename: os.stat(f.filename).st_mtime
                for f in list(wxml.builder.Ui.Registry.values()) + [Main]
        }

        while not self.closed.is_set():
            if any(os.stat(f).st_mtime > watch_files[f] for f in watch_files):
                wxml.builder.Ui.Registry.clear()
                wxml.builder.Control.Registry.clear()

                self.recreate_done.clear()
                self.recreate()
                self.recreate_done.wait()

                watch_files = {
                    f.filename: os.stat(f.filename).st_mtime
                    for f in list(wxml.builder.Ui.Registry.values()) + [Main]
                }

            self.closed.wait(timeout=1)
