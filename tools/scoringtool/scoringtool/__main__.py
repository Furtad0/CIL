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

from __future__ import print_function
import argparse
import sys

from . import mandate_reader
from . import scoring_reader
from . import scoring_checker

import pkg_resources  # part of setuptools
TOOL_VERSION = pkg_resources.require("scoringtool")[0].version

def run():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '-v', '--version', action='version', version='%(prog)s {}'.format(TOOL_VERSION))
    parser.add_argument('command', help="""
    command to be executed, must be mandate-reader, scoring-reader,
    or scoring-checker
    """)
    args = parser.parse_args(sys.argv[1:2])

    # hack the program name for nested parsers
    sys.argv[0] += ' ' + args.command
    args.command = args.command.replace('_', '-')

    if args.command == 'mandate-reader':
        mandate_reader.run(sys.argv[2:])
    elif args.command == 'scoring-reader':
        scoring_reader.run(sys.argv[2:])
    elif args.command == 'scoring-checker':
        scoring_checker.run(sys.argv[2:])
    else:
        parser.print_help()

if __name__ == '__main__':
    run()
