#!/usr/bin/env python
# MIT License
#
# Copyright (c) 2019 Miklos Maroti
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
from datetime import datetime
import sys

from . import __version__
from . import observer_reader
from . import usage_reader
from . import reservation_reader
from . import geodata_reader
from . import spec_plot
from . import spec_eval


def run():
    if datetime.today() >= datetime.strptime("10/23/2019", "%m/%d/%Y"):
        print("*** If you were a winner at the DARPA SC2 competition and   ***\n" +
              "*** found this tool helpful, please invite me for a beer :) ***\n")

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '-v', '--version', action='version', version='%(prog)s {}'.format(__version__))
    parser.add_argument('command', help="""
    command to be executed, must be observer-reader, usage-reader, 
    reservation-reader, geodata-reader, plot, eval""")
    args = parser.parse_args(sys.argv[1:2])

    # hack the program name for nested parsers
    sys.argv[0] += ' ' + args.command
    args.command = args.command.replace('_', '-')

    if args.command == 'observer-reader':
        observer_reader.run(sys.argv[2:])
    elif args.command == 'usage-reader':
        usage_reader.run(sys.argv[2:])
    elif args.command == 'reservation-reader':
        reservation_reader.run(sys.argv[2:])
    elif args.command == 'geodata-reader':
        geodata_reader.run(sys.argv[2:])
    elif args.command == 'plot':
        spec_plot.run(sys.argv[2:])
    elif args.command == 'eval':
        spec_eval.run(sys.argv[2:])
    else:
        parser.print_help()


if __name__ == '__main__':
    run()
