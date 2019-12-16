#!/usr/bin/env python
# MIT License
#
# Copyright (c) 2019 Malcolm Stagg
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# This file is a part of the CIRN Interaction Language.

from setuptools import setup
import sys
import subprocess

if subprocess.call(['make', 'all']) != 0:
    raise EnvironmentError("Error calling make")

setup(
    name='scoringtool',
    #version='0.1',
    packages=['scoringtool'],
    package_data={'scoringtool': ['scoring_parser']},
    include_package_data=True,
    license='MIT',
    description="Tools for scoring DARPA SC2 traffic logs",
    long_description=open('README.md').read(),
    use_scm_version={"root": "../..", "relative_to": __file__},
    setup_requires=['setuptools_scm'],
    # do not list standard packages
    install_requires=[
        'numpy'
    ],
    entry_points={
        'console_scripts': [
            'scoringtool = scoringtool.__main__:run'
        ]
    }
)
