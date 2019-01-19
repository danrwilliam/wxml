import wx
import threading
import os
import time

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent

from wxml.decorators import invoke_ui

class DesignThread(object):
    def __init__(self, filename : str, create, error=None):
        self.filename = filename
        self.closed = threading.Event()
        self.view = None
        self.builder = create

        self.error_vm = error or (lambda: None)

        self._hidden = wx.Frame(None, wx.ID_ANY)

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

    def watch(self):
        tstamp = os.stat(self.filename).st_mtime

        while not self.closed.is_set():
            now = os.stat(self.filename).st_mtime
            if now > tstamp:
                tstamp = now
                self.recreate()
            self.closed.wait(timeout=1)