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

from ciltool import CilReader, cil_pb2
from .spectrum_grid import SpectrumGrid, SpectrumVoxel, get_voxels_bounds
from .reservation_reader import ip_to_srn


class UsageReader(object):

    """
    Reads the CIL spectrum usage messages and creates the predicted and
    measured spectrum grids.
    """

    def __init__(self, filename, src_srn=None, dst_srn=None):
        self.filename = filename
        self.log = logging.getLogger('usage_reader')

        self.stats = {
            'src_srn': None if src_srn is None else int(src_srn),
            'dst_srn': None if dst_srn is None else int(dst_srn),
            'spectrum_usage_msgs': 0,
        }
        self.measured_past_voxels = []    # real measurement
        self.measured_future_voxels = []  # invalid reports
        self.forecast_past_voxels = []    # invalid or stale
        self.forecast_future_voxels = []  # real prediction
        self.message_times = []

    @staticmethod
    def read_timestamp(msg):
        return msg.seconds + 1e-12 * msg.picoseconds

    def read_messages(self):
        with CilReader(self.filename, read_reg=False) as reader:
            last_predicted_voxels = []
            while True:
                msg = reader.read()
                if msg is None:
                    break

                if 'cil_message' not in msg:
                    continue

                src_srn = ip_to_srn(msg['src_ip'])
                dst_srn = ip_to_srn(msg['dst_ip'])
                msg = msg['cil_message']
                network_type = msg.network_type.network_type

                # first competitor
                if (self.stats['src_srn'] is None and
                        network_type in {cil_pb2.NetworkType.UNKNOWN, cil_pb2.NetworkType.COMPETITOR}):
                    self.stats['src_srn'] = src_srn

                # first incumbent
                if (self.stats['dst_srn'] is None and
                        msg.network_type.network_type == cil_pb2.NetworkType.INCUMBENT_PASSIVE):
                    self.stats['dst_srn'] = src_srn

                if src_srn != self.stats['src_srn'] or dst_srn != self.stats['dst_srn']:
                    continue

                if not msg.HasField('spectrum_usage'):
                    continue

                timestamp = UsageReader.read_timestamp(msg.timestamp)
                self.stats['spectrum_usage_msgs'] += 1
                self.message_times.append(timestamp)

                for voxel in last_predicted_voxels:
                    time_stop2 = min(voxel.time_stop, timestamp)
                    time_start2 = min(voxel.time_start, time_stop2)
                    if time_start2 < time_stop2:
                        voxel2 = SpectrumVoxel(
                            time_start=time_start2,
                            time_stop=time_stop2,
                            freq_start=voxel.freq_start,
                            freq_stop=voxel.freq_stop,
                            duty_cycle=voxel.duty_cycle)
                        self.forecast_future_voxels.append(voxel2)
                last_predicted_voxels = []

                for usage_msg in msg.spectrum_usage.voxels:
                    voxel_msg = usage_msg.spectrum_voxel
                    time_start = UsageReader.read_timestamp(
                        voxel_msg.time_start)
                    time_stop = UsageReader.read_timestamp(voxel_msg.time_end)

                    if voxel_msg.HasField('duty_cycle'):
                        duty_cycle = voxel_msg.duty_cycle.value
                        if duty_cycle < 0 or 1 < duty_cycle:
                            self.log.critical(
                                'Invalid duty cycle in voxel %s', voxel_msg)
                        duty_cycle = min(max(duty_cycle, 0), 1)
                    else:
                        duty_cycle = 1

                    past_time_stop = min(time_stop, timestamp)
                    past_time_start = min(time_start, past_time_stop)
                    if past_time_start < past_time_stop:
                        voxel = SpectrumVoxel(
                            time_start=past_time_start,
                            time_stop=past_time_stop,
                            freq_start=voxel_msg.freq_start,
                            freq_stop=voxel_msg.freq_end,
                            duty_cycle=duty_cycle)
                        if usage_msg.measured_data:
                            self.measured_past_voxels.append(voxel)
                        else:
                            self.forecast_past_voxels.append(voxel)

                    future_time_start = max(time_start, timestamp)
                    future_time_stop = max(time_stop, future_time_start)
                    if future_time_start < future_time_stop:
                        voxel = SpectrumVoxel(
                            time_start=future_time_start,
                            time_stop=future_time_stop,
                            freq_start=voxel_msg.freq_start,
                            freq_stop=voxel_msg.freq_end,
                            duty_cycle=duty_cycle)
                        if usage_msg.measured_data:
                            self.measured_future_voxels.append(voxel)
                        else:
                            last_predicted_voxels.append(voxel)

        self.stats['measured_past_voxels'] = len(self.measured_past_voxels)
        self.stats['measured_future_voxels'] = len(self.measured_future_voxels)
        self.stats['forecast_past_voxels'] = len(self.forecast_past_voxels)
        self.stats['forecast_future_voxels'] = len(
            self.forecast_future_voxels)

        self.stats['measured_past_duplicates'] = self.stats['measured_past_voxels'] - \
            len(set(self.measured_past_voxels))

        self.stats['time_start'], self.stats['time_stop'], self.stats['freq_start'], self.stats['freq_stop'] = \
            get_voxels_bounds(self.measured_past_voxels + self.measured_future_voxels +
                              self.forecast_past_voxels + self.forecast_future_voxels)
        self.stats['duplicate_message_timestamps'] = len(
            self.message_times) - len(set(self.message_times))


def run(args=None):
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("filename", help="PCAP filename")
    parser.add_argument('--src-srn', type=int,
                        help="read messages sent by this node")
    parser.add_argument('--dst-srn', type=int,
                        help="read messages sent to this node")
    parser.add_argument('--mode', choices=['measured-past', 'measured-future',
                                           'predicted-past', 'predicted-future'],
                        default='measured-past',
                        help="selects which group of voxels to work with")
    parser.add_argument('--print', action='store_true',
                        help="print the selected voxels")
    parser.add_argument('--save', action='store_true',
                        help="save spectrogram avg/max plots into PNG")
    parser.add_argument('--plot', action='store_true',
                        help="displays spectrogram avg/max plots")
    parser.add_argument('--time-start', type=float,
                        help="specifies the start time of the plot")
    parser.add_argument('--time-stop', type=float,
                        help="specifies the stop time of the plot")
    parser.add_argument('--time-bins', type=int, default=1024,
                        help="specifies the number of frequency bins")
    parser.add_argument('--freq-start', type=float,
                        help="specifies the start freq of the plot")
    parser.add_argument('--freq-stop', type=float,
                        help="specifies the stop freq of the plot")
    parser.add_argument('--freq-bins', type=int, default=512,
                        help="specifies the number of frequency bins")

    args = parser.parse_args(args)
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)

    if args.save:
        import matplotlib
        matplotlib.use('Agg')

    reader = UsageReader(args.filename, args.src_srn, args.dst_srn)
    reader.read_messages()
    print(json.dumps(reader.stats, indent=2, sort_keys=True))

    title = "CIL " + args.mode.replace('-', ' ') + " voxels"
    voxels = getattr(reader, args.mode.replace('-', '_') + '_voxels')

    if args.print:
        for voxel in voxels:
            print(voxel)

    if voxels and (args.plot or args.save):
        time_start, time_stop, freq_start, freq_stop = get_voxels_bounds(
            voxels)
        time_start = args.time_start or time_start
        time_stop = args.time_stop or time_stop
        freq_start = args.freq_start or freq_start
        freq_stop = args.freq_stop or freq_stop
        grid = SpectrumGrid(time_start, time_stop, args.time_bins,
                            freq_start, freq_stop, args.freq_bins)
        for voxel in voxels:
            grid.add_voxel(voxel)

        # print message times only in zoomed in mode
        message_times = reader.message_times if grid.time_stop - \
            grid.time_start <= 30 else None

        png_file = (title + '.png').replace(' ', '_') if args.save else None
        grid.plot_figure(title=title,
                         message_times=message_times,
                         png_file=png_file)


if __name__ == "__main__":
    run()
