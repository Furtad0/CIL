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
import logging

import google.protobuf.message

from . import cil_pb2
from . import registration_pb2 as reg_pb2
from .zmq_reader import ZmqReader


class CilReader(object):

    """
    This class reads a single PCAP file using ZmqReader and generates
    CilMessage protobuf objects with extra metadata: timestamp, src_ip,
    src_port, dst_ip, dst_port. If you set read_reg, then it will also
    return registration (server and client) messages.
    """

    SERVER_PORT = 5556
    CLIENT_PORT = 5557
    PEER_PORT = 5558

    def __init__(self, pcap_filename, read_reg=False):
        self.log = logging.getLogger('cil_reader')
        self.pcap_filename = pcap_filename
        self.read_reg = read_reg
        self.zmq_reader = None

    def __enter__(self):
        self.zmq_reader = ZmqReader(
            self.pcap_filename,
            force_zmq_ports=[self.SERVER_PORT, self.CLIENT_PORT, self.PEER_PORT])
        self.zmq_reader.__enter__()
        return self

    def read(self):
        while True:
            message = self.zmq_reader.read()
            if message is None:
                return None
            if (message['src_port'] == self.PEER_PORT
                    or message['dst_port'] == self.PEER_PORT):
                try:
                    cil_msg = cil_pb2.CilMessage.FromString(message['message'])
                except KeyError as err:
                    self.log.critical("parsing error {}".format(err))
                    continue
                except google.protobuf.message.DecodeError as err:
                    self.log.critical("protobuf decode error {}".format(err))
                    continue
                return {
                    'timestamp': message['timestamp'],
                    'tcp_length': message['tcp_length'],
                    'tcp_stream': message['tcp_stream'],
                    'src_ip': message['src_ip'],
                    'src_port': message['src_port'],
                    'dst_ip': message['dst_ip'],
                    'dst_port': message['dst_port'],
                    'cil_message': cil_msg
                }
            if self.read_reg and (message['src_port'] == self.SERVER_PORT
                                  or message['dst_port'] == self.SERVER_PORT):
                try:
                    client_msg = reg_pb2.TalkToServer.FromString(
                        message['message'])
                except KeyError as err:
                    self.log.critical("parsing error {}".format(err))
                    continue
                return {
                    'timestamp': message['timestamp'],
                    'tcp_length': message['tcp_length'],
                    'tcp_stream': message['tcp_stream'],
                    'src_ip': message['src_ip'],
                    'src_port': message['src_port'],
                    'dst_ip': message['dst_ip'],
                    'dst_port': message['dst_port'],
                    'client_msg': client_msg
                }
            if self.read_reg and (message['src_port'] == self.CLIENT_PORT
                                  or message['dst_port'] == self.CLIENT_PORT):
                try:
                    server_msg = reg_pb2.TellClient.FromString(
                        message['message'])
                except KeyError as err:
                    self.log.critical("parsing error {}".format(err))
                    continue
                return {
                    'timestamp': message['timestamp'],
                    'tcp_length': message['tcp_length'],
                    'tcp_stream': message['tcp_stream'],
                    'src_ip': message['src_ip'],
                    'src_port': message['src_port'],
                    'dst_ip': message['dst_ip'],
                    'dst_port': message['dst_port'],
                    'server_msg': server_msg
                }

    def __exit__(self, err_typ, err_val, trace):
        self.zmq_reader.__exit__(err_typ, err_val, trace)


def run(args=None):
    import argparse
    from google.protobuf.json_format import MessageToJson
    import json

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("filenames", nargs='*',
                        help="list of pcap filenames")
    parser.add_argument('-v', metavar='NUM', type=int,
                        help="set logging verbosity", default=1)
    parser.add_argument('--src', metavar='IP',
                        help="filters by source ipv4 address")
    parser.add_argument('--dst', metavar='IP',
                        help="filters by destination ipv4 address")
    parser.add_argument('--reg', action='store_true',
                        help="print registration messages too")
    args = parser.parse_args(args)
    logging.basicConfig(level=logging.CRITICAL if args.v < 1 else
                        logging.INFO if args.v < 2 else logging.DEBUG)

    for filename in args.filenames:
        with CilReader(filename, read_reg=args.reg) as reader:
            while True:
                message = reader.read()
                if message is None:
                    break
                if args.src and args.src != message['src_ip']:
                    continue
                if args.dst and args.dst != message['dst_ip']:
                    continue

                # just for pretty printing
                if 'cil_message' in message:
                    message['cil_message'] = json.loads(MessageToJson(
                        message['cil_message'], preserving_proto_field_name=True))
                if 'client_msg' in message:
                    message['client_msg'] = json.loads(MessageToJson(
                        message['client_msg'], preserving_proto_field_name=True))
                if 'server_msg' in message:
                    message['server_msg'] = json.loads(MessageToJson(
                        message['server_msg'], preserving_proto_field_name=True))
                print(json.dumps(message, indent=2, sort_keys=True), '\n')


if __name__ == "__main__":
    run()
