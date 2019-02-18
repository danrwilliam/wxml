from setuptools import setup, find_packages

setup(
    name='wxml',
    version='0.5dev',
    packages=find_packages(),
    install_requires=[
        'wxpython',
        'watchdog'
    ]
)