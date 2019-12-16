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
import binascii
import logging
import struct

from .tcp_reader import TcpReader


class ZmqConn(object):

    """
    This class represents the state of an open ZMQ TCP/IP socket.
    You can query the state of the socket using the state member,
    which can be unknown, error, or valid. Only data packets are
    returned.
    """

    def __init__(self, fragment, force_zmq=False):
        self.log = logging.getLogger('zmq_reader')
        self.force_zmq = force_zmq
        self.tcp_stream = fragment['tcp_stream']
        self.src_ip = fragment['src_ip']
        self.src_port = fragment['src_port']
        self.dst_ip = fragment['dst_ip']
        self.dst_port = fragment['dst_port']
        self.frame_time = fragment['frame_time']
        self.tcp_length = None
        self.unread_data = bytearray(fragment['data'])
        self.state = 'unknown'
        self.long_warn = True

    @staticmethod
    def _fragment_hash(fragment):
        return ('#' + str(fragment['tcp_stream']) +
                ',' + fragment['src_ip'] + ',' + str(fragment['src_port']) +
                ',' + fragment['dst_ip'] + ',' + str(fragment['dst_port']))

    def append(self, fragment):
        if self.state == 'error':
            return
        assert self.tcp_stream == fragment['tcp_stream']
        assert self.src_ip == fragment['src_ip']
        assert self.src_port == fragment['src_port']
        assert self.dst_ip == fragment['dst_ip']
        assert self.dst_port == fragment['dst_port']
        self.frame_time = fragment['frame_time']
        self.unread_data += fragment['data']

    def read(self):
        if self.state == 'error':
            return None
        if self.state == 'unknown':
            if len(self.unread_data) < 0x40:
                return None

            # support only version 3 with no authentication and confidelity
            data = struct.unpack_from('!BQBBBcccc', self.unread_data)
            if data == (255, 1, 127, 3, 0, b'N', b'U', b'L', b'L'):
                del self.unread_data[:0x40]
                self.state = 'valid'
            # maybe we have missed the initial header
            elif self.force_zmq and data[0] & 0xfc == 0:
                self.log.info("forcing as zmq stream from {}:{} to {}:{}".format(
                    self.src_ip, self.src_port, self.dst_ip, self.dst_port))
                self.state = 'valid'
            else:
                self.log.info("skipping non-zmq stream from {}:{} to {}:{}".format(
                    self.src_ip, self.src_port, self.dst_ip, self.dst_port))
                self.log.debug("header data: {}".format(
                    binascii.hexlify(self.unread_data[:0x40])))
                del self.unread_data[:]
                self.state = 'error'
            return None

        while True:
            if len(self.unread_data) < 1:
                return None
            flags = struct.unpack_from('B', self.unread_data, 0)[0]

            if (flags & 0x02) == 0:  # short frame
                if len(self.unread_data) < 2:
                    return None
                length = struct.unpack_from('B', self.unread_data, 1)[0]
                start = 2
            else:  # long frame
                if len(self.unread_data) < 9:
                    return None
                length = struct.unpack_from('!Q', self.unread_data, 1)[0]
                start = 9

            if length > 65535 and self.long_warn:
                self.log.info("large payload of size {} from {}:{} to {}:{}".format(
                    length, self.src_ip, self.src_port, self.dst_ip, self.dst_port))
                self.long_warn = False

            if len(self.unread_data) < start + length:
                return None

            self.long_warn = True
            if (flags & 0x04) != 0:  # command frame
                del self.unread_data[:start + length]
                continue

            data = bytes(self.unread_data[start:start + length])
            del self.unread_data[:start + length]
            self.tcp_length = start + length
            return data


class ZmqReader(object):

    """
    This class reads a single PCAP file and generates events that record
    the ZeroMQ TCP/IP messages. This class reads the TCP/IP messages using
    the TcpReader. If the full TCP/IP flow is not recorded in the PCAP file
    then we will miss the initial ZMQ handshake that we use to identify
    ZMQ connections. You can force a list of ports to always be regarded
    as ZMQ streams.
    """

    def __init__(self, pcap_filename, force_zmq_ports=[]):
        self.pcap_filename = pcap_filename
        self.force_zmq_ports = force_zmq_ports
        self.tcp_reader = None
        self.zmq_conns = {}
        self.conn = None

    def __enter__(self):
        self.tcp_reader = TcpReader(self.pcap_filename)
        self.tcp_reader.__enter__()
        return self

    def read(self):
        while True:
            if self.conn is not None:
                message = self.conn.read()
                if message is not None:
                    return {
                        'timestamp': self.conn.frame_time,
                        'tcp_length': self.conn.tcp_length,
                        'tcp_stream': self.conn.tcp_stream,
                        'src_ip': self.conn.src_ip,
                        'src_port': self.conn.src_port,
                        'dst_ip': self.conn.dst_ip,
                        'dst_port': self.conn.dst_port,
                        'message': message
                    }

            fragment = self.tcp_reader.read()
            if fragment is None:
                return None

            frag_hash = ZmqConn._fragment_hash(fragment)
            if frag_hash in self.zmq_conns:
                self.conn = self.zmq_conns[frag_hash]
                self.conn.append(fragment)
            else:
                self.conn = ZmqConn(fragment, force_zmq=fragment[
                    'dst_port'] in self.force_zmq_ports)
                self.zmq_conns[frag_hash] = self.conn

    def __exit__(self, err_typ, err_val, trace):
        self.tcp_reader.__exit__(err_typ, err_val, trace)


def run(args=None):
    import argparse
    import json

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('filename', help="pcap file")
    parser.add_argument('-v', metavar='NUM', type=int,
                        help="set logging verbosity", default=1)
    args = parser.parse_args(args)
    logging.basicConfig(level=logging.CRITICAL if args.v < 1 else
                        logging.INFO if args.v < 2 else logging.DEBUG)

    with ZmqReader(args.filename) as reader:
        while True:
            message = reader.read()
            if message is None:
                break

            # just for pretty printing
            message['message'] = binascii.hexlify(message['message'])
            print(json.dumps(message, indent=2, sort_keys=True), '\n')


if __name__ == '__main__':
    run()
