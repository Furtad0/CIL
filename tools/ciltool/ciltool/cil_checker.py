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
import logging
import socket
import struct
from google.protobuf.json_format import MessageToJson

from .cil_reader import CilReader

DEFAULT_VALID_WINDOW_START = 0  # January 1970
DEFAULT_VALID_WINDOW_END = (2 ** 32) - 1  # February 2106

logger = logging.getLogger(__name__)

class CheckLinkSrc(object):

    """
    This class processes CIL messages between a source and a destination
    gateway node and records errors within the messages created by the
    the source.
    """

    TIMESTAMP_MAX_ERROR = 5
    SPECTRUM_USAGE_MIN_RATE = 0.5  # add 0.5 second of grace period
    SPECTRUM_USAGE_MAX_RATE = 30.5
    SPECTRUM_VOXEL_MAX_TIME_OFFSET = 60.5
    LOCATION_UPDATE_MIN_RATE = 0.5
    LOCATION_UPDATE_MAX_RATE = 30.5
    LOCATION_INFO_MAX_HISTORY = 60.5
    DETAILED_PERFORMANCE_MIN_RATE = 0.5
    DETAILED_PERFORMANCE_MAX_RATE = 10.5
    DETAILED_PERFORMANCE_MAX_HISTORY = 10.5
    RATE_LIMITED_MIN_COUNT = 2
    FREQUENCY_MIN = 900e6 - 20e6  # from FAQ
    FREQUENCY_MAX = 1100e6 + 20e6
    LATITUDE_MIN = -90.0
    LATITUDE_MAX = 90.0
    LONGITUDE_MIN = -180.0
    LONGITUDE_MAX = 180.0
    RADIO_ID_MIN = 1
    RADIO_ID_MAX = 128

    class Report(object):

        def __init__(self, src, dst):
            self.cil_check_passed = False
            self.cil_version = None
            self.sender_ip_address = src
            self.receiver_ip_address = dst
            self.total_messages = 0
            self.picoseconds_valid = True
            self.sender_network_id_valid = True
            self.timestamp_is_set = True
            self.timestamp_valid = True
            self.timestamp_offset = None
            self.timestamp_first = None
            self.timestamp_last = None
            self.msg_count_monotone = True
            self.hello_first = True
            self.hello_messages = 0
            self.spectrum_voxel_freq_valid = True
            self.spectrum_voxel_time_start_valid = True
            self.spectrum_voxel_time_end_valid = True
            self.spectrum_usage_messages = 0
            self.spectrum_usage_voxels = []
            self.spectrum_usage_good_rate = True
            self.location_update_messages = 0
            self.location_info_timestamp_valid = True
            self.location_info_location_valid = True
            self.location_update_good_rate = True
            self.radio_ids = []
            self.radio_id_valid = True
            self.detailed_performance_messages = 0
            self.detailed_performance_good_rate = True
            self.detailed_performance_max_mandate_count = 0
            self.detailed_performance_max_achieved = 0
            self.detailed_performance_timestamp_valid = True
            self.mandate_performance_messages = 0
            self.mandate_flow_id_valid = True
            self.detailed_performance_mandate_point_value_valid = True
            self.detailed_performance_scoring_point_threshold_valid = True
            self.incumbent_notify_messages = 0
            self.peer_disconnect_count = 0

    def __init__(self, src, dst, validation_config=None):
        self.log = logging.getLogger('check_link_src')
        self.sender_network_id = struct.unpack('!L', socket.inet_aton(src))[0]
        self.report = self.Report(src, dst)
        self.last_msg_count = 0
        self.last_spectrum_usage = None
        self.last_location_update = None
        self.last_detailed_performance = None
        self.timestamp_offset_cnt = 0
        self.timestamp_offset_sum = 0
        self.peer_connected = True

        if validation_config is not None:
            self.validation_config = validation_config
        else:
            self.validation_config = {"valid_window_start": DEFAULT_VALID_WINDOW_START,
                                      "valid_window_end": DEFAULT_VALID_WINDOW_END}

    def process_cil_sent(self, message):
        if ('cil_message' not in message
                or message['src_ip'] != self.report.sender_ip_address
                or message['dst_ip'] != self.report.receiver_ip_address):
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

        self.report.total_messages += 1
        self.check_sender_network_id(message)
        self.check_timestamp(message)
        self.check_hello_first(message)
        self.check_message_count(message)
        self.check_spectrum_usage(message, msg_in_timing_window)
        self.check_location_update(message, msg_in_timing_window)
        self.check_detailed_performance_message(message, msg_in_timing_window)
        self.check_incumbent_notify_messages(message)

    def process_reg_rcvd(self, message):
        if ('server_msg' not in message
                or message['dst_ip'] != self.report.sender_ip_address):
            self.log.critical('unexpected message')
            return

        if message['server_msg'].HasField('inform'):
            self.update_peer_connection(message['server_msg'].inform.neighbors)
        if message['server_msg'].HasField('notify'):
            self.update_peer_connection(message['server_msg'].notify.neighbors)

    def update_peer_connection(self, neighbors):
        connected = False
        for neighbor in neighbors:
            if self.report.receiver_ip_address == socket.inet_ntoa(struct.pack('!L', neighbor)):
                connected = True

        if self.peer_connected and not connected:
            self.report.peer_disconnect_count += 1
            self.last_spectrum_usage = None
            self.last_location_update = None
            self.last_detailed_performance = None

        self.peer_connected = connected

    def report_failure(self, test, message):
        if self.report.__getattribute__(test):
            pretty = dict(message)
            pretty['cil_message'] = json.loads(MessageToJson(
                pretty['cil_message'], preserving_proto_field_name=True))
            self.log.debug(test + ' error:\n' +
                           json.dumps(pretty, indent=2, sort_keys=True) + '\n')
        self.report.__setattr__(test, False)

    def check_sender_network_id(self, message):
        if self.sender_network_id != message['cil_message'].sender_network_id:
            logger.error("msg %i: Invalid sender network ID. Expected %s, found %s",
                         message['cil_message'].msg_count,
                         self.sender_network_id,
                         message['cil_message'].sender_network_id)

            self.report.sender_network_id_valid = False

    def get_timestamp_value(self, timestamp):
        if timestamp.picoseconds < 0 or timestamp.picoseconds >= 1e12:
            self.report.picoseconds_valid = False
            logger.error("Picoseconds field invalid. Was %e, must be between %i and %.2e",
                         timestamp.picoseconds,
                         0, 1e12)
        return timestamp.seconds + 1e-12 * timestamp.picoseconds

    def add_radio_id(self, radio_id):
        if radio_id not in self.report.radio_ids:
            self.report.radio_ids.append(radio_id)

    def check_radio_id(self, radio_id, message):
        if radio_id < self.RADIO_ID_MIN or radio_id > self.RADIO_ID_MAX:
            logger.error("msg %i: Radio ID invalid. Was %i, must be between %i and %i.",
                         message['cil_message'].msg_count,
                         radio_id,
                         self.RADIO_ID_MIN,
                         self.RADIO_ID_MAX)
            self.report_failure('radio_id_valid', message)

    def check_timestamp(self, message):
        timestamp = self.get_timestamp_value(message['cil_message'].timestamp)

        if message['cil_message'].timestamp.seconds == 0:
            self.report_failure('timestamp_is_set', message)
        else:
            offset = message['timestamp'] - timestamp

            self.timestamp_offset_cnt += 1
            self.timestamp_offset_sum += offset
            if abs(offset) > self.TIMESTAMP_MAX_ERROR:
                logger.warning("msg %i: Found large offset between CIL Message timestamp and TCP timestamp",
                message['cil_message'].msg_count)
                self.report_failure('timestamp_valid', message)

        self.report.timestamp_last = timestamp
        if self.report.timestamp_first is None:
            self.report.timestamp_first = timestamp

    def check_hello_first(self, message):
        if self.report.total_messages == 1:
            if not message['cil_message'].HasField('hello'):
                logger.error("msg %i: Hello message must be first CIL message sent to peers. Found %s instead",
                             message['cil_message'].msg_count,
                             message['cil_message'].WhichOneof("payload"))
                self.report_failure('hello_first', message)

        if message['cil_message'].HasField('hello'):
            self.last_msg_count = message['cil_message'].msg_count - 1
            self.report.hello_messages += 1
            self.report.cil_version = (
                str(message['cil_message'].hello.version.major) + '.' +
                str(message['cil_message'].hello.version.minor) + '.' +
                str(message['cil_message'].hello.version.patch))

    def check_message_count(self, message):
        if self.last_msg_count >= message['cil_message'].msg_count:
            logger.error("Found message count %i after count %i. Message count must be monotonically increasing",
                         message['cil_message'].msg_count, self.last_msg_count)
            self.report_failure('msg_count_monotone', message)

        self.last_msg_count = message['cil_message'].msg_count

    def check_spectrum_voxel(self, voxel, message):
        if not (self.FREQUENCY_MIN <= voxel.freq_start < voxel.freq_end <= self.FREQUENCY_MAX):
            logger.error("msg %i: Invalid spectrum voxel frequency range",
                         message['cil_message'].msg_count)
            self.report_failure('spectrum_voxel_freq_valid', message)

        timestamp = self.get_timestamp_value(message['cil_message'].timestamp)
        time_start = self.get_timestamp_value(voxel.time_start)
        if abs(time_start - timestamp) > self.SPECTRUM_VOXEL_MAX_TIME_OFFSET:
            self.report_failure('spectrum_voxel_time_start_valid', message)
            logger.error("msg %i: voxel start time was invalid", message['cil_message'].msg_count)

        if voxel.HasField('time_end'):
            time_end = self.get_timestamp_value(voxel.time_end)
            if time_end < time_start or abs(time_end - timestamp) > self.SPECTRUM_VOXEL_MAX_TIME_OFFSET:
                self.report_failure('spectrum_voxel_time_end_valid', message)
                logger.error("msg %i: voxel end time was invalid", message['cil_message'].msg_count)

        voxel_data = {
            'freq_start': voxel.freq_start,
            'freq_width': voxel.freq_end - voxel.freq_start,
            'duty_cycle_set': voxel.HasField('duty_cycle'),
            'period_time': voxel.period_time.value if voxel.HasField('period_time') else None,
            'slot_time': voxel.slot_time.value if voxel.HasField('slot_time') else None
        }
        if voxel_data not in self.report.spectrum_usage_voxels:
            self.report.spectrum_usage_voxels.append(voxel_data)

    def check_spectrum_usage(self, message, msg_in_timing_window):
        if not message['cil_message'].HasField('spectrum_usage'):
            return

        self.report.spectrum_usage_messages += 1
        for usage in message['cil_message'].spectrum_usage.voxels:
            self.check_spectrum_voxel(usage.spectrum_voxel, message)

            self.check_radio_id(usage.transmitter_info.radio_id, message)
            self.add_radio_id(usage.transmitter_info.radio_id)
            for info in usage.receiver_info:
                self.check_radio_id(info.radio_id, message)
                self.add_radio_id(info.radio_id)

        timestamp = self.get_timestamp_value(message['cil_message'].timestamp)
        if self.last_spectrum_usage is not None:
            # only perform rate checks for messages after the startup grace period and before teardown
            if msg_in_timing_window:
                rate = timestamp - self.last_spectrum_usage
                if rate < self.SPECTRUM_USAGE_MIN_RATE or rate > self.SPECTRUM_USAGE_MAX_RATE:
                    self.report_failure('spectrum_usage_good_rate', message)
                    logger.error("msg %i: spectrum usage message rate failure", message['cil_message'].msg_count)
                    logger.error("Actual interval was %.2f s, must be between %.2f and %.2f s",
                                 rate, self.SPECTRUM_USAGE_MIN_RATE, self.SPECTRUM_USAGE_MAX_RATE)
        if self.peer_connected:
            self.last_spectrum_usage = timestamp

    def check_location_update(self, message, msg_in_timing_window):
        if not message['cil_message'].HasField('location_update'):
            return

        self.report.location_update_messages += 1
        for location_info in message['cil_message'].location_update.locations:
            self.check_radio_id(location_info.radio_id, message)
            self.add_radio_id(location_info.radio_id)
            timestamp = self.get_timestamp_value(location_info.timestamp)
            sendtime = self.get_timestamp_value(
                message['cil_message'].timestamp)
            if timestamp > sendtime or timestamp < sendtime - self.LOCATION_INFO_MAX_HISTORY:
                self.report_failure('location_info_timestamp_valid', message)
                logger.warning("msg %i: location update timestamp was invalid",message['cil_message'].msg_count)

            if location_info.HasField('location'):
                if location_info.location.latitude < self.LATITUDE_MIN or location_info.location.latitude > self.LATITUDE_MAX:
                    self.report_failure('location_info_location_valid', message)
                    logger.error("msg %i: location update latitude is invalid", message['cil_message'].msg_count)
                    logger.error("Actual latitude %.2f degrees, must be between %.2f and %.2f degrees",
                                location_info.location.latitude, self.LATITUDE_MIN, self.LATITUDE_MAX)

                if location_info.location.longitude < self.LONGITUDE_MIN or location_info.location.longitude > self.LONGITUDE_MAX:
                    self.report_failure('location_info_location_valid', message)
                    logger.error("msg %i: location update longitude is invalid", message['cil_message'].msg_count)
                    logger.error("Actual longitude %.2f degrees, must be between %.2f and %.2f degrees",
                                location_info.location.longitude, self.LONGITUDE_MIN, self.LONGITUDE_MAX)

            else:
                self.report_failure('location_info_location_valid', message)
                logger.error("msg %i: location update did not include a location field for at least one location.",
                             message['cil_message'].msg_count)

        timestamp = self.get_timestamp_value(message['cil_message'].timestamp)
        if self.last_location_update is not None:
            # only perform rate checks for messages after the startup grace period and before teardown
            if msg_in_timing_window:
                rate = timestamp - self.last_location_update
                if rate < self.LOCATION_UPDATE_MIN_RATE or rate > self.LOCATION_UPDATE_MAX_RATE:
                    self.report_failure('location_update_good_rate', message)
                    logger.error("msg %i: location update message rate failure", message['cil_message'].msg_count)
                    logger.error("Actual interval was %.2f s, must be between %.2f and %.2f s",
                                 rate, self.LOCATION_UPDATE_MIN_RATE, self.LOCATION_UPDATE_MAX_RATE)
        if self.peer_connected:
            self.last_location_update = timestamp

    def check_detailed_performance_message(self, message, msg_in_timing_window):
        if not message['cil_message'].HasField('detailed_performance'):
            return

        self.report.detailed_performance_messages += 1

        self.report.detailed_performance_max_mandate_count = max(
            self.report.detailed_performance_max_mandate_count,
            message['cil_message'].detailed_performance.mandate_count)

        self.report.detailed_performance_max_achieved = max(
            self.report.detailed_performance_max_achieved,
            message['cil_message'].detailed_performance.mandates_achieved)

        if message['cil_message'].detailed_performance.scoring_point_threshold == 0:
            self.report_failure('detailed_performance_scoring_point_threshold_valid', message)

        for mandate in message['cil_message'].detailed_performance.mandates:
            self.report.mandate_performance_messages += 1

            for radio_id in mandate.radio_ids:
                self.check_radio_id(radio_id, message)
                self.add_radio_id(radio_id)

            for voxel in mandate.desired_voxels:
                self.check_spectrum_voxel(voxel, message)

            if mandate.flow_id == 0:
                self.report_failure('mandate_flow_id_valid', message)

            if mandate.point_value == 0:
                self.report_failure('detailed_performance_mandate_point_value_valid', message)

        timestamp = self.get_timestamp_value(message['cil_message'].timestamp)
        if self.last_detailed_performance is not None:
            # only perform rate checks for messages after the startup grace period and before teardown
            if msg_in_timing_window:
                rate = timestamp - self.last_detailed_performance
                if rate < self.DETAILED_PERFORMANCE_MIN_RATE or rate > self.DETAILED_PERFORMANCE_MAX_RATE:
                    self.report_failure('detailed_performance_good_rate', message)
                    logger.error("msg %i: detailed performance message rate failure", message['cil_message'].msg_count)
                    logger.error("Actual interval was %.2f s, must be between %.2f and %.2f s",
                                 rate, self.DETAILED_PERFORMANCE_MIN_RATE, self.DETAILED_PERFORMANCE_MAX_RATE)
        if self.peer_connected:
            self.last_detailed_performance = timestamp

        perf_time = self.get_timestamp_value(
            message['cil_message'].detailed_performance.timestamp)
        if (perf_time > timestamp or 
                perf_time < timestamp - self.DETAILED_PERFORMANCE_MAX_HISTORY):
            self.report_failure('detailed_performance_timestamp_valid', message)
            logger.warning("msg %i: detailed performance timestamp was invalid",
                message['cil_message'].msg_count)

    def check_incumbent_notify_messages(self, message):
        if message['cil_message'].HasField('incumbent_notify'):
            self.report.incumbent_notify_messages += 1

    def validate(self):
        self.report.cil_check_passed = (
            self.report.hello_first and
            self.report.msg_count_monotone and
            self.report.picoseconds_valid and
            self.report.sender_network_id_valid and
            self.report.radio_id_valid and
            self.report.timestamp_is_set and
            # self.report.timestamp_valid and  # Commented out prior to Scrimmage 5 CIL Validation
            self.report.spectrum_voxel_freq_valid and
            self.report.spectrum_voxel_time_start_valid and
            self.report.spectrum_voxel_time_end_valid and
            self.report.spectrum_usage_good_rate and
            self.report.spectrum_usage_messages >= self.RATE_LIMITED_MIN_COUNT and
            self.report.location_info_timestamp_valid and
            self.report.location_info_location_valid and
            self.report.location_update_good_rate and
            self.report.location_update_messages >= self.RATE_LIMITED_MIN_COUNT and
            self.report.detailed_performance_timestamp_valid and
            self.report.detailed_performance_good_rate and
            self.report.detailed_performance_messages >= self.RATE_LIMITED_MIN_COUNT and
            self.report.mandate_flow_id_valid and
            self.report.detailed_performance_mandate_point_value_valid and
            self.report.detailed_performance_scoring_point_threshold_valid) 

        if self.report.spectrum_usage_messages < self.RATE_LIMITED_MIN_COUNT:
            logger.error("Found %i spectrum usage messages in log. Must find at least %i messages to check rate",
                         self.report.spectrum_usage_messages, self.RATE_LIMITED_MIN_COUNT)

        if self.report.location_update_messages < self.RATE_LIMITED_MIN_COUNT:
            logger.error("Found %i location update messages in log. Must find at least %i messages to check rate",
                         self.report.location_update_messages, self.RATE_LIMITED_MIN_COUNT)

        if self.report.detailed_performance_messages < self.RATE_LIMITED_MIN_COUNT:
            logger.error("Found %i detailed performance messages in log. Must find at least %i messages to check rate",
                         self.report.detailed_performance_messages, self.RATE_LIMITED_MIN_COUNT)

        if self.timestamp_offset_cnt > 0:
            self.report.timestamp_offset = \
                self.timestamp_offset_sum / self.timestamp_offset_cnt
        else:
            self.report.timestamp_offset = None

        self.report.spectrum_usage_voxels = sorted(
            self.report.spectrum_usage_voxels, key=lambda v: v['freq_start'])

        return self.report.cil_check_passed

    def get_report(self):
        self.validate()
        return dict(self.report.__dict__)


class CheckAllLinks(object):

    """
    This class process CIL messages and checks that each link is following
    the protocol specification. You can filter the checked links by specifying
    the src and/or dst client addresses.
    """

    def __init__(self, src=None, dst=None, validation_config=None):
        self.links = dict()
        self.src = src
        self.dst = dst
        self.validation_config = validation_config

    def process(self, message):
        if ('cil_message' in message and
                (self.src is None or self.src == message['src_ip']) and
                (self.dst is None or self.dst == message['dst_ip'])):
            key = (message['src_ip'], message['dst_ip'])
            if key not in self.links:
                self.links[key] = CheckLinkSrc(key[0], key[1], self.validation_config)
            self.links[key].process_cil_sent(message)

        if 'server_msg' in message:
            for key in self.links:
                if message['dst_ip'] == key[0]:
                    self.links[key].process_reg_rcvd(message)

    def get_reports(self):
        reports = []
        for key in self.links:
            reports.append(self.links[key].get_report())
        return reports


def run(args=None):
    import argparse
    import os
    import re
    import sys

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("filename", help="pcap file")
    parser.add_argument('-v', metavar='NUM', type=int,
                        help="set logging verbosity", default=1)
    parser.add_argument('--src', metavar='IP',
                        help="filters by source IPv4 address")
    parser.add_argument('--src-auto', action='store_true',
                        help="obtain the src filter address from the filename")
    parser.add_argument('--dst', metavar='IP',
                        help="filters by destination IPv4 address")
    parser.add_argument("--match-start-time", type=int,
                        help="unix epoch time (UTC seconds since 00:00:00 January 1 1970) of the start of the match",
                        default=0)
    parser.add_argument("--match-duration", type=int,
                        help="duration of the match in seconds", default=None)
    parser.add_argument("--startup-grace-period", type=int,
                        help="seconds after the start of the match at which to begin evaluating CIL compliance",
                        default=0)
    args = parser.parse_args(args)
    log_fmt = '%(levelname)s: %(message)s'
    log_levels = {0: logging.CRITICAL,
                  1: logging.ERROR,
                  2: logging.WARNING,
                  3: logging.INFO,
                  4: logging.DEBUG}
    logging.basicConfig(format=log_fmt,
                        stream=sys.stdout,
                        level=logging.CRITICAL if args.v < 1 else
                        log_levels[args.v] if 1 <= args.v <= 4 else logging.DEBUG)

    if args.src_auto and not args.src:
        match = re.match(
            r'^[-a-zA-Z0-9_]*-srn(\d*)-RES\d*-colbr(\d*)-\d*-\d*\.pcap$',
            os.path.basename(args.filename))
        if match:
            args.src = "172.30." + str(100 + int(match.group(2))) + \
                "." + str(100 + int(match.group(1)))
            logging.info(
                "Discovered source filter address is {}".format(args.src))
        else:
            logging.critical("Invalid PCAP filename format")

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

    check_all_links = CheckAllLinks(src=args.src, dst=args.dst,
                                    validation_config=validation_config)

    with CilReader(args.filename, read_reg=True) as reader:
        while True:
            message = reader.read()
            if message is None:
                break
            check_all_links.process(message)

    reports = check_all_links.get_reports()
    cil_check_passed = all(report["cil_check_passed"] for report in reports)

    print(json.dumps(reports,
                     indent=2, sort_keys=True))

    # only exit with successful return code if the CIL checks pass
    if cil_check_passed:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    run()
