import queue
import threading
from typing import Optional, Callable, Tuple
import sys
import wx

from wxml.event import Event

_stop_block_ui = threading.Event()

def stop_bind_updates():
    """

    """
    _stop_block_ui.set()

def resume_bind_updates():
    _stop_block_ui.clear()

def invoke_ui(func):
    """
        makes sure that the function called is called from the
        UI thread, can't return a value.
        Calling from a non-UI thread will return immediately,
        use block_ui if you want to wait or get the return value.
    """
    def wraps(*args, **kwargs):
        # print(func.__name__, threading.current_thread().name)
        if not wx.IsMainThread():
            wx.CallAfter(func, *args, **kwargs)
        else:
            return func(*args, **kwargs)
    return wraps


def block_ui(func):
    """
        calls the wrapped function on the UI thread, and waits
        for it to return, returning the function's return value.
        Exceptions that occur are re-raised on the calling thread.
    """

    def wraps(*args, **kwargs):
        if wx.IsMainThread():
            return func(*args, **kwargs)
        elif not _stop_block_ui.is_set():
            q = queue.Queue()
            def wraps(q, func, *args, **kwargs):
                try:
                    retval = func(*args, **kwargs)
                except Exception as ex:
                    retval = ex
                q.put(retval)

            # invoke on ui thread
            wx.CallAfter(wraps, q, func, *args, **kwargs)

            # wait for return
            obj = q.get(block=True)
            if isinstance(obj, Exception):
                raise obj
            else:
                return obj
    return wraps


def background(func):
    """
        Calls the wrapped function on a non-UI thread.
        If called on a non-UI thread, the function returns normally,
        otherwise, the thread is launched and does not wait.

        The handler member is a callable that will be called if an
        exception is thrown. The handler takes an Exception object, and
        a tuple
    """

    def wrapped(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except Exception as ex:
            background.handler(ex, sys.exc_info())

    def wraps(*args, **kwargs):
        if wx.IsMainThread():
            t = threading.Thread(target=wrapped, args=args, kwargs=kwargs)
            t.start()
        else:
            return func(*args, **kwargs)

    return wraps
background.handler = Event('wxml.background.handler')