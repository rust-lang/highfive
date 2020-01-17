#!/usr/bin/env python

from setuptools import setup

setup(
    name='highfive',
    version='0.1',
    description='GitHub hooks to provide an encouraging atmosphere for new contributors',
    author='Rust Community',
    author_email='no-idea@no-server.no-suffix',
    url='https://github.com/rust-lang-nursery/highfive',
    packages=[
        'highfive',
    ],
    install_requires=[
        'click',
        'flask',
        'python-dotenv',
        'requests',
        'waitress',
    ],
    entry_points={
        'console_scripts': [
            'highfive=highfive.app:main',
        ],
    },
    zip_safe=False,
)
