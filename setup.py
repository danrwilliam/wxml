from distutils.core import setup, find_packages

setup(
    name='wxml',
    version='0.2dev',
    packages=find_packages(),
    install_requires=[
        'wxpython',
        'watchdog'
    ]
)