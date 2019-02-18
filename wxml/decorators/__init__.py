import threading
import wx
import queue

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
        else:
            q = queue.Queue()
            def wraps(func, q, *args, **kwargs):
                try:
                    retval = func(*args, **kwargs)
                except Exception as ex:
                    retval = ex
                q.put(retval)

            t = threading.Thread(target=wraps, args=(func, q, *args), kwargs=kwargs)
            t.start()

            obj = q.get(block=True)
            if isinstance(obj, Exception):
                raise obj
            else:
                return obj
    return wraps