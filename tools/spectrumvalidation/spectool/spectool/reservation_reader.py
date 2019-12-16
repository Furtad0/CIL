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

from __future__ import print_function, division
import logging
import json
import os
import re

COLOSSEUM_SRN_TO_IP_OFFSET = 100


def ip_to_srn(ip):
    return int(ip.split('.')[-1]) - COLOSSEUM_SRN_TO_IP_OFFSET


class ReservationReader(object):

    """
    Collects basic data from a reservation directory.
    """

    def __init__(self, directory):
        self.log = logging.getLogger('reservation_reader')
        self.data = {
            'directory': os.path.abspath(directory),
            'reservation': None,
            'observer_srn': None,
            'incumbent_srn': None,
            'collab_server_srn': None,
            'gateway_srn': None,
            'rf_start_time': None,
            'nodes': {},
        }

    def read_match_conf(self):
        filename = os.path.join(
            self.data['directory'], 'Inputs', 'match_conf.json')
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                match = json.load(f)
                self.data['batch_filename'] = match.get('batch_filename')
                self.data['team'] = match.get('team')
                self.data['node_to_srn_mapping'] = match.get(
                    'node_to_srn_mapping', {})
            return

        self.log.critical('missing match_conf.json file in %s',
                          self.data['directory'])

    def read_batch_input(self):
        filename = os.path.join(
            self.data['directory'], 'Inputs', 'batch_input.json')
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                batch = json.load(f)
                self.data['rf_scenario'] = batch.get('RFScenario')
                self.data['batch_name'] = batch.get('BatchName')
                self.data['duration'] = batch.get('Duration')
                for node in batch.get('NodeData', []):
                    image = node.get('ImageName')
                    is_gateway = node.get('isGateway', False)
                    rfn_id = node.get('RFNode_ID')
                    srn_id = self.data['node_to_srn_mapping'].get(str(rfn_id))
                    self.data['nodes'][srn_id] = {
                        'srn_id': srn_id,
                        'rfn_id': rfn_id,
                        'trn_id': node.get('TrafficNode'),
                        'image': image,
                        'config': node.get('ModemConfig'),
                        'is_gateway': is_gateway
                    }

                    if image and image.startswith('sc2observer'):
                        self.data['observer_srn'] = srn_id
                    elif image and image.startswith('incumbent'):
                        self.data['incumbent_srn'] = srn_id
                    elif is_gateway:
                        self.data['gateway_srn'] = srn_id

    def read_rf_start_time(self):
        filename = os.path.join(
            self.data['directory'], 'Inputs', 'rf_start_time.json')
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                time = json.load(f)
                self.data['rf_start_time'] = float(time)

    def find_logs_dirs(self):
        for filename in os.listdir(self.data['directory']):
            if not os.path.isdir(os.path.join(self.data['directory'], filename)):
                continue

            match = re.match(
                r'^[-A-Za-z_0-9]*-srn(\d*)-RES(\d*)$', filename)
            if not match:
                continue

            self.data['reservation'] = match.group(2)
            node = self.data['nodes'].get(int(match.group(1)))
            if node is not None:
                node['logs_dir'] = filename
            else:
                self.log.critical("unexpected srn logs directory %s", filename)

    def find_pcap_files(self):
        for filename in os.listdir(self.data['directory']):
            if not os.path.isfile(os.path.join(self.data['directory'], filename)):
                continue

            match = re.match(
                r'^[-A-Za-z_0-9]*-srn(\d*)-RES(\d*)-colbr(\d*)-[-A-Za-z_0-9]*\.pcap$', filename)
            if not match:
                continue

            self.data['reservation'] = match.group(2)
            self.data['collab_server_srn'] = int(match.group(3))

            node = self.data['nodes'].get(int(match.group(1)))
            if node is not None:
                node['pcap_file'] = filename
            else:
                self.log.critical("unexpected pcap file %s", filename)

    def read_all(self):
        self.read_match_conf()
        self.read_batch_input()
        self.read_rf_start_time()
        self.find_logs_dirs()
        self.find_pcap_files()
        return self.data


def run(args=None):
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("directory", help="RESERVATION directory")

    args = parser.parse_args(args)
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)

    data = ReservationReader(args.directory).read_all()
    print(json.dumps(data, indent=2, sort_keys=True))


if __name__ == "__main__":
    run()
