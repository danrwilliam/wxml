from distutils.core import setup

setup(
    name='wxml',
    version='0.2dev',
    packages=['wxml'],
    install_requires=[
        'wxpython',
        'watchdog'
    ]
)