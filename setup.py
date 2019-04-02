from setuptools import setup, find_packages

setup(
    name='wxml',
    version='0.6.2',
    packages=find_packages(),
    install_requires=[
        'wxpython',
        'watchdog'
    ]
)