import threading
import wx

def invoke_ui(func):
    """
        makes sure that the function called is called from the
        UI thread, can't return a value
    """
    def wraps(*args, **kwargs):
        # print(func.__name__, threading.current_thread().name)
        if not wx.IsMainThread():
            wx.CallAfter(func, *args, **kwargs)
        else:
            return func(*args, **kwargs)
    return wraps