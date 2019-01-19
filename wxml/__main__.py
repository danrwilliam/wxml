import argparse
import os
import wx
import wxml

parser = argparse.ArgumentParser()
parser.add_argument('filename', type=os.path.abspath, help='Xml file to build and run UI for')
parser.add_argument('--inspect', '-i', action='store_true', help='Opens the wxpython inspector after construction')
parser.add_argument('--design', '-d', action='store_true', help='Watch the named file for changes, and reload if it changes')
parser.add_argument('--verbose', '-v', action='store_true')
opts = parser.parse_args()

app = wx.App()

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
        #error=wxml.ErrorViewModel.instance if opts.verbose else None
    )
    watch.thread.start()
else:
    vm = create(opts.filename)
    vm.view.Show()
    if opts.inspect:
        vm.inspect()

app.MainLoop()