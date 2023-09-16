from setuptools import setup, find_packages

setup(
    name='wxml',
    version='0.9.2',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'wxpython',
    ],
    package_data={
        'wxml': ['*.xml'],
    }
)
