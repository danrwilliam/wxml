import argparse
import os
import sys

import wx
import wxml

parser = argparse.ArgumentParser()
parser.add_argument('filename', type=os.path.abspath, help='Xml file to build and run UI for')
parser.add_argument('--inspect', '-i', action='store_true', help='Opens the wxpython inspector after construction')
parser.add_argument('--design', '-d', action='store_true', help='Watch the named file for changes, and reload if it changes')
parser.add_argument('--verbose', '-v', action='store_true')
parser.add_argument('--debug-flags', '-f', type=lambda s: s.split(','), default=[])
parser.add_argument('--check', '-c', action='store_true', help='Process the xml file but do not show the UI')
parser.add_argument('--widgets', '-w', action='store_true', help='Print widgets and their names')
opts = parser.parse_args()

app = wx.App()

for f in opts.debug_flags:
    if hasattr(wxml.builder, 'DEBUG_%s' % f.upper()):
        setattr(wxml.builder, 'DEBUG_%s' % f.upper(), True)

def create(filename):
    if filename in wxml.Ui.Registry:
        vm = wxml.Ui.Registry[filename]()
    else:
        vm = wxml.GenericViewModel(filename)

    return vm

if opts.design:
    from wxml.design import DesignThread
    watch = DesignThread(
        opts.filename,
        create=create,
        error=wxml.ErrorViewModel.instance,
        show_widgets=opts.widgets
    )
    if watch.ok:
        watch.thread.start()
    else:
        sys.exit(1)
else:
    vm = create(opts.filename)
    if vm.view is not None and not opts.check:
        vm.view.Show()
        if opts.inspect:
            vm.inspect()
    if opts.widgets:
        print('widgets:')
        for name, ctrl in vm.view.widgets.items():
            print(' - %s: %s' % (name, ctrl))                    

if not opts.check:
    app.MainLoop()