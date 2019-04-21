import sys

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

def nested_hasattr(name, root=None):
    return nested_getattr(name, root) is not None