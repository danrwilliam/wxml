import wx
import threading
import os
import time

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent

import wxml.builder
from wxml.decorators import invoke_ui

class DesignThread(object):
    def __init__(self, filename : str, create, error=None):
        self.filename = filename
        self.closed = threading.Event()
        self.view = None
        self.builder = create

        self.error_vm = error or (lambda: None)

        self._hidden = wx.Frame(None, wx.ID_ANY)

        self.recreate_done = threading.Event()

        self.recreate()
        self.thread = threading.Thread(target=self.watch)


    def close(self, evt: wx.Event):
        evt.StopPropagation()

    def cleanup(self):
        self.closed.set()
        self._hidden.Close()
        self.thread.join()

    @invoke_ui
    def recreate(self):
        if self.view is not None and self.view.view is not None:
            self.position = self.view.view.Position
            self.view.view.Destroy()

        vm = self.error_vm()
        if vm is not None:
            vm.clear()

        self.view = self.builder(self.filename)
        self.view.on_close += self.cleanup

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
                watch_files = {
                    f.filename: os.stat(f.filename).st_mtime
                    for f in list(wxml.builder.Ui.Registry.values()) + [Main]
                }
                self.recreate_done.clear()
                self.recreate()
                self.recreate_done.wait()

            self.closed.wait(timeout=1)