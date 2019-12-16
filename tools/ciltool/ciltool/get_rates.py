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
import socket
import struct
from collections import namedtuple
from google.protobuf.json_format import MessageToJson

from .cil_reader import CilReader


class GetRates(object):

    """
    This class processes CIL messages between a source and a destination
    gateway node and the server and the source node and collects events
    and rates for different types of messages.
    """

    def __init__(self, sender, receiver, abs_time=False, dump=True):
        self.log = logging.getLogger('rate_printer')
        self.sender = sender
        self.receiver = receiver
        self.abs_time = abs_time
        self.dump = dump
        self.receiver_network_id = struct.unpack(
            '!L', socket.inet_aton(receiver))[0]

        self.entries = []
        self.start_time = None
        self.last_spectrum_usage = None
        self.last_location_update = None
        self.last_detailed_performance = None

    def process(self, message):
        if self.start_time is None:
            self.start_time = message['timestamp']
            if self.dump:
                print(
                    "event                tcp_time cil_time offset msg_count rate")

        if ('cil_message' in message and self.sender == message['src_ip']
                and self.receiver == message['dst_ip']):
            cil_message = message['cil_message']
            if cil_message.HasField('timestamp'):
                timestamp = (cil_message.timestamp.seconds
                             + 1e-12 * cil_message.timestamp.picoseconds)
            else:
                timestamp = None

            rate = None
            if cil_message.HasField('hello'):
                event = 'hello_sent'
            elif cil_message.HasField('spectrum_usage'):
                event = 'spectrum_usage'
                if self.last_spectrum_usage is not None:
                    rate = timestamp - self.last_spectrum_usage
                self.last_spectrum_usage = timestamp
            elif cil_message.HasField('location_update'):
                event = 'location_update'
                if self.last_location_update is not None:
                    rate = timestamp - self.last_location_update
                self.last_location_update = timestamp
            elif cil_message.HasField('detailed_performance'):
                event = 'detailed_performance'
                if self.last_detailed_performance is not None:
                    rate = timestamp - self.last_detailed_performance
                self.last_detailed_performance = timestamp

            else:
                return

            self.add_entry(
                event=event,
                tcp_time=message['timestamp'],
                cil_time=timestamp,
                msg_count=message['cil_message'].msg_count,
                rate=rate)

        elif ('cil_message' in message and self.sender == message['dst_ip']
                and self.receiver == message['src_ip']):
            if message['cil_message'].HasField('hello'):
                self.add_entry(
                    event='hello_received',
                    tcp_time=message['timestamp'])

        elif 'server_msg' in message:
            if message['server_msg'].HasField('inform'):
                neighbors = message['server_msg'].inform.neighbors
            elif message['server_msg'].HasField('notify'):
                neighbors = message['server_msg'].notify.neighbors
            else:
                return

            registered = self.receiver_network_id in neighbors
            self.add_entry(
                event='peer_is_registered' if registered else 'peer_is_unregisterd',
                tcp_time=message['timestamp'])

    Entry = namedtuple(
        'Entry', ['event', 'tcp_time', 'cil_time', 'msg_count', 'rate'])

    def add_entry(self, event, tcp_time, cil_time=None, msg_count=None, rate=None):
        self.entries.append(
            self.Entry(event, tcp_time, cil_time, msg_count, rate))
        if self.dump:
            if not self.abs_time:
                tcp_time -= self.start_time
                if cil_time is not None:
                    cil_time -= self.start_time
            if cil_time is None and rate is None:
                print("{:20} {:8.3f}".format(event, tcp_time))
            elif rate is None:
                print("{:20} {:8.3f} {:8.3f} {:6.3f} {:9}".format(
                    event, tcp_time, cil_time, tcp_time - cil_time, msg_count))
            else:
                print("{:20} {:8.3f} {:8.3f} {:6.3f} {:9} {:6.3f}".format(
                    event, tcp_time, cil_time, tcp_time - cil_time, msg_count, rate))

    def get_report(self):
        pass


def run(args=None):
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("filename", help="pcap file")
    parser.add_argument('-v', metavar='NUM', type=int,
                        help="set logging verbosity", default=1)
    parser.add_argument('--src', metavar='IP', required=True,
                        help="the mandatory source IPv4 address")
    parser.add_argument('--dst', metavar='IP', required=True,
                        help="the mandatory destination IPv4 address")
    parser.add_argument('--abs', action='store_true',
                        help="print absolute times")
    args = parser.parse_args(args)
    logging.basicConfig(level=logging.CRITICAL if args.v < 1 else
                        logging.INFO if args.v < 2 else logging.DEBUG,
                        stream=sys.stdout)

    collector = GetRates(
        sender=args.src,
        receiver=args.dst,
        abs_time=args.abs)

    with CilReader(args.filename, read_reg=True) as reader:
        while True:
            message = reader.read()
            if message is None:
                break
            collector.process(message)


if __name__ == "__main__":
    run()
