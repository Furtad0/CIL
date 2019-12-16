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
import configparser
import datetime
import glob
import logging
import math
from os import path
import re

import numpy as np

from .spectrum_grid import SpectrumGrid


class ObserverReader(object):

    """
    Reads the config and the passband raw data from an observer directory.
    """

    def __init__(self, directory):
        self.directory = directory
        self.log = logging.getLogger('observer_reader')

        self.config = {}
        self.grid = None

    def parser_getint(self, parser, section, option):
        try:
            self.config[option] = parser.getint(section, option)
        except configparser.Error:
            pass

    def parser_getfloat(self, parser, section, option):
        try:
            self.config[option] = parser.getfloat(section, option)
        except configparser.Error:
            pass

    RE_CONFIG = re.compile(r'^([A-Za-z ]+)\s*:\s*([-A-Za-z0-9]*)\s*$')
    RE_RADIOAPI = re.compile(
        r'^Timestamp:\s*(\d{4})-(\d{2})-(\d{2})\s*(\d{2}):(\d{2}):(\d{2})\s*RadioAPI:\s*(\w*)\s*-\s*([a-zA-Z0-9\.]*):')

    def read_state_change(self):
        """Reads the content of the StateChange.log file."""

        state_change_files = glob.glob(
            path.join(self.directory, '*StateChange.log'))
        if not state_change_files:
            self.log.critical("StateChange.log file was not found")
            return

        epoch = datetime.datetime.utcfromtimestamp(0)

        with open(state_change_files[0], 'r') as f:
            for line in f:
                line = line.strip()

                match = self.RE_CONFIG.match(line)
                if match:
                    key = match.group(1).strip().replace(' ', '_').lower()
                    self.config[key] = match.group(2).strip()

                match = self.RE_RADIOAPI.match(line)
                if match:
                    status = match.group(7)
                    script = match.group(8)

                    timeparts = [int(match.group(i)) for i in range(1, 7)]
                    timestamp = (datetime.datetime(
                        *timeparts) - epoch).total_seconds()

                    if script == 'start.sh':
                        if status != 'SUCCESS':
                            self.log.critical("start.sh did not succeed")
                        self.config['start_sh_time'] = timestamp

                    if script == 'stop.sh':
                        if status != 'SUCCESS':
                            self.log.critical("stop.sh did not succeed")
                        self.config['stop_sh_time'] = timestamp

    def read_configs(self):
        """Reads all config options and calculates parameters used by the flowgraph."""

        parser = configparser.ConfigParser()
        parser.read(path.join(self.directory, 'colosseum_config.ini'))
        self.parser_getfloat(parser, 'RF', 'center_frequency')
        self.parser_getfloat(parser, 'RF', 'rf_bandwidth')

        parser = configparser.ConfigParser()
        parser.read(path.join(self.directory, 'radio.conf'))
        self.parser_getfloat(parser, 'RX', 'rx_samp_rate')
        self.parser_getint(parser, 'FFT', 'input_nfft')
        self.parser_getint(parser, 'FFT', 'obs_nfft')
        self.parser_getfloat(parser, 'FFT', 'frame_len')

        self.config['rf_decimation'] = int(
            2**np.floor(np.log2(self.config['rx_samp_rate']/self.config['rf_bandwidth'])))
        self.config['start_bin'] = (
            self.config['input_nfft']-self.config['input_nfft']//self.config['rf_decimation'])//2
        self.config['stop_bin'] = self.config['start_bin'] + \
            self.config['input_nfft']//self.config['rf_decimation']

        if (self.config['stop_bin'] - self.config['start_bin']) % self.config['obs_nfft'] != 0:
            self.log.critical("FFT lengths and start/stop bins do not match")

        self.config['obs_bandwidth'] = self.config['rx_samp_rate'] / \
            self.config['rf_decimation']

        return self.config

    def read_pass_band_rf(self, between_start_stop_sh=True):
        """Reads an RF file produced by the observer and updates the config and
        sets the data field."""

        header_dt = np.dtype([('obs_nfft', np.uint32), ('frame_len', np.float64),
                              ('t0_int_s', np.uint64), ('t0_frac_s', np.float64)])

        with open(path.join(self.directory, 'pass_band.rf'), "rb") as f:
            header = np.fromfile(f, dtype=header_dt, count=1)[0]

            row_dt = np.dtype([("sync", np.uint32), ("frame_num", np.uint32),
                               ("fft_bins", np.float32, (1, header["obs_nfft"]))])

            rows = np.fromfile(f, dtype=row_dt)

        if 'obs_nfft' in self.config and self.config['obs_nfft'] != header['obs_nfft']:
            self.log.critical(
                "FFT lengths from config and RF data do not match")
            self.config['obs_nfft'] = header['obs_nfft']
        else:
            self.config['obs_nfft'] = int(header['obs_nfft'])

        if 'frame_len' in self.config and self.config['frame_len'] != header['frame_len']:
            self.log.critical(
                "Frame lengths from config and RF data do not match")
        self.config['frame_len'] = header['frame_len']

        self.config['start_time'] = header['t0_int_s'] + header['t0_frac_s']
        self.config['num_frames'] = len(rows)

        self.config['last_frame_num'] = self.config['num_frames']
        self.config['real_frame_len'] = self.config['frame_len']

        self.config['has_magic_number'] = False
        if len(rows) >= 1:
            self.config['last_frame_num'] = int(rows[-1][1])
            self.config['real_frame_len'] *= float(
                self.config['last_frame_num'] + 1) / self.config['num_frames']
            if rows[0][0] == 503107354:
                self.config['has_magic_number'] = True

        self.config['stop_time'] = self.config['start_time'] + \
            self.config['num_frames'] * self.config['real_frame_len']

        if between_start_stop_sh:
            grid_frame_start = int(math.floor((
                self.config['start_sh_time'] -
                self.config['start_time']) / self.config['real_frame_len']))
            grid_frame_stop = int(math.ceil((
                self.config['stop_sh_time'] -
                self.config['start_time']) / self.config['real_frame_len']))
            self.config['grid_frame_start'] = min(
                max(grid_frame_start, 0), len(rows))
            self.config['grid_frame_stop'] = min(
                max(grid_frame_stop, grid_frame_start), len(rows))
        else:
            self.config['grid_frame_start'] = 0
            self.config['grid_frame_stop'] = len(rows)

        data = np.empty((self.config['grid_frame_stop'] -
                         self.config['grid_frame_start'], self.config['obs_nfft']),
                        dtype=np.float32)

        self.config['time_validation'] = []
        max_time_error = 0

        for idx in range(self.config['grid_frame_start'], self.config['grid_frame_stop']):
            row = rows[idx]
            data[idx - self.config['grid_frame_start']] = row[2]

            # old data format with magic numbers
            if self.config['has_magic_number']:
                if row[0] != 503107354:
                    self.log.critical('Corrupted RF file')
                max_time_error = max(max_time_error, abs(
                    row[1] * self.config['frame_len'] - idx * self.config['real_frame_len']))

            # new data format with embedded times
            else:
                modulo = int(2 ** 32)
                frame_num = int(row[1])
                nominal_time = self.config['start_time'] + frame_num * self.config['frame_len']
                nominal_low32 = int(nominal_time * 1000) % modulo

                embedded_low32 = int(row[0]) % modulo
                difference = ((embedded_low32 - nominal_low32 + modulo // 2) % modulo) - modulo // 2
                max_time_error = max(max_time_error, abs(difference))

                self.config['time_validation'].append({
                    'frame_num': frame_num,
                    'nominal_time': nominal_time,
                    'nominal_low32': nominal_low32,
                    'embedded_low32': embedded_low32,
                    'difference': difference
                })

        self.config['max_time_error'] = max_time_error

        self.config['start_freq'] = self.config['center_frequency'] - \
            0.5 * self.config['obs_bandwidth']
        self.config['stop_freq'] = self.config['center_frequency'] + \
            0.5 * self.config['obs_bandwidth']

        self.config['grid_time_start'] = self.config['start_time'] + \
            self.config['grid_frame_start'] * self.config['real_frame_len']
        self.config['grid_time_stop'] = self.config['start_time'] + \
            self.config['grid_frame_stop'] * self.config['real_frame_len']
        self.config['grid_time_bins'] = self.config['grid_frame_stop'] - \
            self.config['grid_frame_start']

        self.grid = SpectrumGrid(self.config['grid_time_start'], self.config['grid_time_stop'],
                                 self.config['grid_time_bins'], self.config['start_freq'],
                                 self.config['stop_freq'], self.config['obs_nfft'], data)


def run(args=None):
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("dir", help="observer directory")
    parser.add_argument('--config-only', action='store_true',
                        help="do not read the rf data file")
    parser.add_argument('--save', action='store_true',
                        help="save spectrogram avg/max plots into PNG")
    parser.add_argument('--plot', action='store_true',
                        help="displays spectrogram avg/max plots")
    parser.add_argument('--time-start', nargs="?", type=float,
                        help="specifies the start time of the plot")
    parser.add_argument('--time-stop', nargs="?", type=float,
                        help="specifies the stop time of the plot")
    parser.add_argument('--freq-start', nargs="?", type=float,
                        help="specifies the start freq of the plot")
    parser.add_argument('--freq-stop', nargs="?", type=float,
                        help="specifies the stop freq of the plot")
    parser.add_argument('--time-validation', action='store_true',
                        help="Print or plot time validation data")

    args = parser.parse_args(args)
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)

    if args.save:
        import matplotlib
        matplotlib.use('Agg')

    reader = ObserverReader(args.dir)

    if args.time_validation:
        reader.config['center_frequency'] = 1e8
        reader.config['obs_bandwidth'] = 50e6
        reader.read_pass_band_rf(between_start_stop_sh=False)

        if args.config_only:
            print(json.dumps(reader.config, indent=2, sort_keys=True))
        else:
            import matplotlib.pyplot as plt
            plt.figure()
            plt.plot(
                [x['frame_num'] for x in reader.config['time_validation']],
                [x['difference'] for x in reader.config['time_validation']])
            plt.xlabel("Frame number")
            plt.ylabel("embedded - nominal time")
            plt.show()

    else:
        reader.read_state_change()
        reader.read_configs()
        if not args.config_only:
            reader.read_pass_band_rf()

        print(json.dumps(reader.config, indent=2, sort_keys=True))

        if not args.config_only:
            title = "Observer pass band"
            png_file = (title + '.png').replace(' ', '_') if args.save else None

            if args.save or args.plot:
                reader.grid.plot_figure(time_start=args.time_start,
                                        time_stop=args.time_stop,
                                        freq_start=args.freq_start,
                                        freq_stop=args.freq_stop,
                                        title=title,
                                        png_file=png_file)


if __name__ == "__main__":
    run()
