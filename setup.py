#!/usr/bin/env python

from distutils.core import setup

setup(name='highfive',
      version='0.1',
      description='GitHub hooks to provide an encouraging atmosphere for new contributors',
      author='Rust Community',
      author_email='no-idea@no-server.no-suffix',
      url='https://github.com/rust-lang-nursery/highfive',
      packages=['highfive'],
      install_requires=['retry'],
)
