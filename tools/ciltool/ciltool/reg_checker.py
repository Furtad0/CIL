#!/usr/bin/env python
# MIT License
#
# Copyright (c) 2019 DARPA
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
import logging
import socket
import struct
from google.protobuf.json_format import MessageToJson

from .cil_reader import CilReader

DEFAULT_VALID_WINDOW_START = 0  # January 1970
DEFAULT_VALID_WINDOW_END = (2 ** 32) - 1  # February 2106


class CheckClient(object):
    """
    This class processes CIL registration messages and checks that the client sends heartbeats
    at the required rate.

    This also checks that the client does not send registration messages during the timing valid window.
    Any registration message should have been sent during the initial grace period
    """

    KEEPALIVE_MAX_INTERVAL = 30.5

    class Report(object):

        def __init__(self, server, client):
            self.reg_check_passed = False
            self.server_ip_address = server
            self.client_ip_address = client
            self.total_keepalives = 0
            self.keepalive_good_rate = True
            self.total_registrations = 0
            self.no_repeat_registration = True

    def __init__(self, server, client, validation_config=None):
        self.log = logging.getLogger(__name__)
        self.report = self.Report(server, client)
        self.last_keepalive = None

        if validation_config is not None:
            self.validation_config = validation_config
        else:
            self.validation_config = {"valid_window_start": DEFAULT_VALID_WINDOW_START,
                                      "valid_window_end": DEFAULT_VALID_WINDOW_END}

    def process(self, message):
        if 'client_msg' not in message and 'server_msg' not in message:
            self.log.critical('unexpected message')
            return

        # check that this message is within our message validation time window
        # If the message is within the validation time window, set msg_in_timing_window True.
        # False otherwise.
        if(self.validation_config["valid_window_start"] <= message["timestamp"]
                < self.validation_config["valid_window_end"]):
            msg_in_timing_window = True
        else:
            msg_in_timing_window = False

        # count messages
        if 'client_msg' in message:

            if message['client_msg'].HasField('keepalive'):
                self.report.total_keepalives += 1

            if message['client_msg'].HasField('register'):
                self.report.total_registrations += 1

            # only run these checks on client messages
            self.check_no_repeat_registration(message, msg_in_timing_window)
            self.check_keepalive_good_rate(message, msg_in_timing_window)

    def report_failure(self, test, message):
        if self.report.__getattribute__(test):
            pretty = dict(message)
            if 'client_msg' in pretty:
                pretty['client_msg'] = json.loads(MessageToJson(
                    pretty['client_msg'], preserving_proto_field_name=True))
            elif 'server_msg' in pretty:
                pretty['server_msg'] = json.loads(MessageToJson(
                    pretty['server_msg'], preserving_proto_field_name=True))

            self.log.debug(test + ' error:\n' +
                           json.dumps(pretty, indent=2, sort_keys=True) + '\n')
        self.report.__setattr__(test, False)

    def check_no_repeat_registration(self, message, msg_in_timing_window):
        """ Test whether this is a registration message occurring after the grace period ends """

        if msg_in_timing_window:
            if message['client_msg'].HasField('register'):
                self.report_failure('no_repeat_registration', message)

    def check_keepalive_good_rate(self, message, msg_in_timing_window):
        if not message['client_msg'].HasField('keepalive'):
            return

        timestamp = message["timestamp"]
        if self.last_keepalive is not None:
            # only perform rate checks for messages after the startup grace period and before teardown
            if msg_in_timing_window:
                interval = timestamp - self.last_keepalive
                if interval > self.KEEPALIVE_MAX_INTERVAL:
                    self.report_failure('keepalive_good_rate', message)
        self.last_keepalive = timestamp

    def get_timestamp_value(self, timestamp):
        if timestamp.picoseconds < 0 or timestamp.picoseconds >= 1e12:
            self.report.picoseconds_valid = False
        return timestamp.seconds + 1e-12 * timestamp.picoseconds

    def validate(self):
        self.report.reg_check_passed = (
            self.report.keepalive_good_rate and
            self.report.no_repeat_registration and
            self.report.total_keepalives > 0 and
            self.report.total_registrations > 0
            )

        return self.report.reg_check_passed

    def get_report(self):
        self.validate()
        return dict(self.report.__dict__)


class CheckAllClients(object):

    """
    This class processes registration messages and checks that each client is following
    the protocol specification.
    """

    def __init__(self, validation_config=None):
        self.clients = dict()

        if validation_config is not None:
            self.validation_config = validation_config
        else:
            self.validation_config = {"valid_window_start": DEFAULT_VALID_WINDOW_START,
                                      "valid_window_end": DEFAULT_VALID_WINDOW_END}

    def process(self, message):
        if 'client_msg' in message:
            # Client messages go client => server
            client_ip = message['src_ip']
            server_ip = message['dst_ip']

        elif 'server_msg' in message:
            # Server messages go server => client
            server_ip = message['src_ip']
            client_ip = message['dst_ip']

        else:
            return

        if client_ip not in self.clients:
            self.clients[client_ip] = CheckClient(server_ip, client_ip, self.validation_config)

        self.clients[client_ip].process(message)

    def get_reports(self):
        reports = []
        for key in self.clients:
            reports.append(self.clients[key].get_report())
        return reports


def run(args=None):
    import argparse
    import os
    import re
    import sys

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("filename", help="Collaboration server pcap file")
    parser.add_argument('-v', metavar='NUM', type=int,
                        help="set logging verbosity", default=1)
    parser.add_argument('--server', metavar='IP',
                        help="specify Collaboration server IPv4 address")
    parser.add_argument('--required-gateway', metavar='IP', action='append',
                        help="Which client IPs to evaluate for disconnects. This parameter can be repeated",
                        default=None)
    parser.add_argument("--match-start-time", type=int,
                        help="unix epoch time (UTC seconds since 00:00:00 January 1 1970) of the start of the match",
                        default=0)
    parser.add_argument("--match-duration", type=int,
                        help="duration of the match in seconds", default=None)
    parser.add_argument("--startup-grace-period", type=int,
                        help="seconds after the start of the match at which to begin evaluating CIL compliance",
                        default=0)
    args = parser.parse_args(args)
    logging.basicConfig(level=logging.CRITICAL if args.v < 1 else
                        logging.INFO if args.v < 2 else logging.DEBUG,
                        stream=sys.stdout)

    # validate message timing parameters
    valid_window_start = args.match_start_time + args.startup_grace_period
    if args.match_duration is not None:
        valid_window_end = args.match_start_time + args.match_duration
    else:
        valid_window_end = (2**32)-1 # Will occur in early February 2106. Not a typo.

    if valid_window_end < valid_window_start:
        logging.critical("Bad CIL validation time window: Check that startup grace period is less than match duration")

    # build validation_config dictionary. Notionally this could be used in the future to pass in constants parsed
    # from an external file
    validation_config = {"valid_window_start":valid_window_start,
                         "valid_window_end":valid_window_end}

    check_all_clients = CheckAllClients(validation_config=validation_config)

    with CilReader(args.filename, read_reg=True) as reader:
        while True:
            message = reader.read()
            if message is None:
                break
            if 'cil_message' in message:  # ignore CIL messages
                continue
            if args.server and 'server_msg' in message and args.server != message['src_ip']:
                continue
            if args.server and 'client_msg' in message and args.server != message['dst_ip']:
                continue
            if args.required_gateway and 'server_msg' in message and message['dst_ip'] not in args.required_gateway:
                continue
            if args.required_gateway and 'client_msg' in message and message['src_ip'] not in args.required_gateway:
                continue

            check_all_clients.process(message)

    reports = check_all_clients.get_reports()
    reg_check_passed = all(report["reg_check_passed"] for report in reports)

    print(json.dumps(reports,
                     indent=2, sort_keys=True))

    # only exit with successful return code if the CIL checks pass
    if reg_check_passed:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    run()
