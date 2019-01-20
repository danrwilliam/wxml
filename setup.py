from distutils.core import setup

setup(
    name='wxml',
    version='0.1dev',
    packages=['wxml'],
    install_requires=[
        'wxpython',
        'watchdog'
    ]
)