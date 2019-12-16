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
import json
import subprocess


class TcpReader(object):

    """
    This class reads a single PCAP file and generates events that record
    the TCP/IP flow activities. This class uses the "tshark" executable
    to interpret the PCAP file.
    """

    def __init__(self, pcap_filename):
        self.pcap_filename = pcap_filename
        self.proc = None

    def __enter__(self):
        try:
            self.proc = subprocess.Popen(
                [
                    'tshark', '-r', self.pcap_filename,
                    '-T', 'ek',
                    '-e', 'data',
                    '-e', 'ip.src',
                    '-e', 'ip.dst',
                    '-e', 'tcp.stream',
                    '-e', 'tcp.srcport',
                    '-e', 'tcp.dstport',
                    '-e', 'frame.time_epoch',
                    '--disable-protocol', 'cil',
                    'tcp.stream', 'and', 'data'
                ],
                stdout=subprocess.PIPE,
                bufsize=-1,
                close_fds=True,
                universal_newlines=True)
        except OSError as err:
            if err.errno == 2:
                raise RuntimeError("please install tshark")
            else:
                raise
        return self

    def _get1(self, data, item):
        assert item in data and len(data[item]) == 1
        return data[item][0]

    def read(self):
        while True:
            line = self.proc.stdout.readline()
            if not line:
                return None
            line = line.rstrip()
            if not line:
                continue
            data = json.loads(line)
            if 'layers' not in data:
                continue

            data = data['layers']
            return {
                'frame_time': float(self._get1(data, 'frame_time_epoch')),
                'tcp_stream': int(self._get1(data, 'tcp_stream')),
                'src_ip': self._get1(data, 'ip_src'),
                'src_port': int(self._get1(data, 'tcp_srcport')),
                'dst_ip': self._get1(data, 'ip_dst'),
                'dst_port': int(self._get1(data, 'tcp_dstport')),
                'data': bytes(bytearray.fromhex(self._get1(data, 'data')))
            }

    def __exit__(self, err_typ, err_val, trace):
        if self.proc:
            self.proc.terminate()
            self.proc = None


def run(args=None):
    import argparse
    import binascii

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('filename', help="pcap file")
    args = parser.parse_args(args)

    with TcpReader(args.filename) as reader:
        while True:
            fragment = reader.read()
            if fragment is None:
                break
            # just for pretty printing
            fragment['data'] = binascii.hexlify(fragment['data'])
            print(json.dumps(fragment, indent=2, sort_keys=True), '\n')


if __name__ == '__main__':
    run()
