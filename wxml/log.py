import logging
import wxml

LOG = logging.getLogger('wxml')
LOG.setLevel(logging.DEBUG)

class ConsoleHandler(logging.StreamHandler):
    pass

console = ConsoleHandler()

LOG.addHandler(console)