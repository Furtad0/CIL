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
from os import path
import math
import numpy as np

from .reservation_reader import ReservationReader
from .observer_reader import ObserverReader
from .spectrum_grid import SpectrumGrid
from .usage_reader import UsageReader
from .geodata_reader import GeodataReader


class SpecEval(object):

    """
    Creates statistics on spectrum usage.
    """

    def __init__(self):
        self.log = logging.getLogger('spec_eval')

        # for the observer data
        self.observer_dir = None
        self.observer_config = None
        self.observer_grid = None
        self.observer_threshold = None

        # for the CIL reports
        self.gateway_pcap = None
        self.gateway_stats = None
        self.measured_voxels = []
        self.forecast_voxels = []

        # for the spec-val tool
        self.gdf_file_name = None
        self.gdf_file_report = None
        self.gdf_file_shapes = None

        # bounds of the spectrum region
        self.time_start = None
        self.time_stop = None
        self.time_bins = None

        self.freq_start = None
        self.freq_stop = None
        self.freq_bins = None

        # numpy matrixes with duty cycles for each bin
        self.observer_duty = None  # from observer passband data
        self.observer_quantized = None # from observer passband data, quantized to be true or false
        self.measured_duty = None  # from CIL past measurements
        self.measured_quantized = None # from CIL past measurements, quantized to be true or false
        self.forecast_duty = None  # from CIL future forecasts
        self.gdf_file_duty = None  # from the spec-val tool
        self.forecast_quantized = None # from CIL future forecasts, quantized to be true or false

        # numpy matrices with quantized errors for each bin
        self.measured_v_observer = None
        self.forecast_v_observer = None

    def read_observer_data(self, observer_dir):
        self.log.info('Reading observer data from %s',
                      path.basename(observer_dir))
        reader = ObserverReader(observer_dir)
        reader.read_state_change()
        reader.read_configs()
        reader.read_pass_band_rf()

        self.observer_dir = observer_dir
        self.observer_config = reader.config
        self.observer_grid = reader.grid

    def read_usage_data(self, gateway_pcap, gateway_srn=None, incumbent_srn=None):
        self.log.info('Reading usage data from %s',
                      path.basename(gateway_pcap))
        reader = UsageReader(gateway_pcap, gateway_srn, incumbent_srn)
        reader.read_messages()

        self.gateway_pcap = gateway_pcap
        self.gateway_stats = reader.stats
        self.measured_voxels = reader.measured_past_voxels
        self.forecast_voxels = reader.forecast_future_voxels

    def read_gdf_data(self, gdf_file_name, rf_start_time):
        self.log.info('Reading geodata frames from %s', gdf_file_name)
        reader = GeodataReader(gdf_file_name, rf_start_time)
        self.gdf_file_name = gdf_file_name
        self.gdf_file_report = {
            'filename': reader.stats['filename'],
            'bbox': reader.stats['bbox'],
            'geometry_types': reader.stats['geometry_types'],
        }
        self.gdf_file_shapes = reader.select_shapes()

    def set_bounds(self, time_start, time_stop, time_bins, time_step,
                   freq_start, freq_stop, freq_bins, freq_step):
        # use the bounds from the observer if not specified
        time_start = time_start or self.observer_grid.time_start
        time_stop = time_stop or self.observer_grid.time_stop

        freq_start = freq_start or self.observer_grid.freq_start
        freq_stop = freq_stop or self.observer_grid.freq_stop

        # make sure that we have proper ranges
        time_start = min(max(time_start, self.observer_grid.time_start),
                         self.observer_grid.time_stop)
        time_stop = min(max(time_stop, self.observer_grid.time_start),
                        self.observer_grid.time_stop)
        freq_start = min(max(freq_start, self.observer_grid.freq_start),
                         self.observer_grid.freq_stop)
        freq_stop = min(max(freq_stop, self.observer_grid.freq_start),
                        self.observer_grid.freq_stop)

        # override bins if step is specified
        if time_step and (time_stop - time_start) > time_step > 0:
            time_stop = time_start + \
                math.floor((time_stop - time_start) / time_step) * time_step
            time_bins = int(round((time_stop - time_start) / time_step))

        if freq_step and (freq_stop - freq_start) > freq_step > 0:
            freq_stop = freq_start + \
                math.floor((freq_stop - freq_start) / freq_step) * freq_step
            freq_bins = int(round((freq_stop - freq_start) / freq_step))

        # save everything
        self.time_start = time_start
        self.time_stop = time_stop
        self.time_bins = time_bins
        self.freq_start = freq_start
        self.freq_stop = freq_stop
        self.freq_bins = freq_bins

        self.log.info('Selected times: start %s stop %s',
                      time_start, time_stop)
        self.log.info('Selected bins: time %s freq %s', time_bins, freq_bins)

    def calculate_observer_duty_cylces(self, threshold):
        self.log.info('Calculating observer duty cycles')

        grid = self.observer_grid.threshold(threshold)
        grid = grid.resample(
            self.time_start, self.time_stop, self.time_bins,
            self.freq_start, self.freq_stop, self.freq_bins)
        self.observer_threshold = threshold
        self.observer_duty = grid.data
        self.observer_quantized = self.observer_grid.resample( self.time_start, self.time_stop, self.time_bins, self.freq_start, self.freq_stop, self.freq_bins, take_max=True ).data
        self.observer_quantized[self.observer_quantized >= threshold] = 1
        self.observer_quantized[self.observer_quantized < 1] = 0

    def calculate_spectrum_usage_duty_cycles(self):
        self.log.info('Calculating measured spectrum duty cycles')

        grid = SpectrumGrid(
            self.time_start, self.time_stop, self.time_bins,
            self.freq_start, self.freq_stop, self.freq_bins)

        for voxel in self.measured_voxels:
            grid.add_voxel(voxel)
        self.measured_duty = grid.data
        self.measured_quantized = grid.data
        self.measured_quantized[self.measured_quantized>0] = 1

        self.log.info('Calculating forecast spectrum duty cycles')

        grid = SpectrumGrid(
            self.time_start, self.time_stop, self.time_bins,
            self.freq_start, self.freq_stop, self.freq_bins)

        for voxel in self.forecast_voxels:
            grid.add_voxel(voxel)
        self.forecast_duty = grid.data
        self.forecast_quantized = grid.data ;
        self.forecast_quantized[self.forecast_quantized>0] = 1

    def calculate_gdf_file_duty_cycles(self):
        self.log.info('Calculating geodata spectrum duty cycles')

        grid = SpectrumGrid(
            self.time_start, self.time_stop, self.time_bins,
            self.freq_start, self.freq_stop, self.freq_bins)

        for shape in self.gdf_file_shapes:
            grid.add_shape(shape)
        self.gdf_file_duty = grid.data

    def get_diff_stat(self, diff):
        return {
            'above': float(np.average(np.maximum(diff, 0))),
            'below': float(np.average(np.maximum(-diff, 0))),
            'total': float(np.average(np.abs(diff)))
        }

    def get_diff_quant_stat(self, a, b):
        above = a-b ;
        below = -above ;
        total = np.abs(a-b) ;
        above[above<0] = 0 ;
        below[below<0] = 0 ;
        return {
            'above': float(np.sum(above)/np.sum(b)),
            'below': float(np.sum(below)/np.sum(b)),
            'total': float(np.sum(total)/np.sum(b)),
        }

    def create_report(self):
        self.log.info('Creating reports')

        self.measured_v_observer = -1*self.measured_quantized - (self.observer_quantized*-5)
        self.forecast_v_observer = -1*self.forecast_quantized - (self.observer_quantized*-5)

        # fraction of spectrum where there is anything
        observer_occupied = np.array(self.observer_duty > 0.0, dtype=float)
        measured_occupied = np.array(self.measured_duty > 0.0, dtype=float)
        forecast_occupied = np.array(self.forecast_duty > 0.0, dtype=float)

        report = {
            'bounds': {
                'time_start': self.time_start,
                'time_stop': self.time_stop,
                'time_bins': self.time_bins,
                'time_step': (self.time_stop - self.time_start) / self.time_bins,
                'freq_start': self.freq_start,
                'freq_stop': self.freq_stop,
                'freq_bins': self.freq_bins,
                'freq_step': (self.freq_stop - self.freq_start) / self.freq_bins,
            },
            'observer': {
                'directory': path.basename(self.observer_dir),
                'center_frequency': self.observer_config.get('center_frequency'),
                'rf_bandwidth': self.observer_config.get('rf_bandwidth'),
                'real_frame_len': self.observer_config.get('real_frame_len'),
                'threshold': self.observer_threshold,
            },
            'gateway': {
                'filename': path.basename(self.gateway_pcap),
                'forecast_future_voxels': self.gateway_stats.get('forecast_future_voxels'),
                'forecast_past_voxels': self.gateway_stats.get('forecast_past_voxels'),
                'measured_future_voxels': self.gateway_stats.get('measured_future_voxels'),
                'measured_past_voxels': self.gateway_stats.get('measured_past_voxels'),
                'measured_past_duplicates': self.gateway_stats.get('measured_past_duplicates'),
            },
            'gdf-file': self.gdf_file_report,
            'duty_cycles': {
                'observer': float(np.average(self.observer_duty)),
                'measured': float(np.average(self.measured_duty)),
                'forecast': float(np.average(self.forecast_duty)),
                'differences': {
                    'measured_vs_observer':
                        self.get_diff_stat(self.measured_duty - self.observer_duty),
                    'forecast_vs_observer':
                        self.get_diff_stat(self.forecast_duty - self.observer_duty),
                    'forecast_vs_measured':
                        self.get_diff_stat(self.forecast_duty - self.measured_duty),
                }
            },
            'occupied': {
                'observer': float(np.average(observer_occupied)),
                'measured': float(np.average(measured_occupied)),
                'forecast': float(np.average(forecast_occupied)),
                'differences': {
                    'measured_vs_observer':
                        self.get_diff_stat(measured_occupied - observer_occupied),
                    'forecast_vs_observer':
                        self.get_diff_stat(forecast_occupied - observer_occupied),
                    'forecast_vs_measured':
                        self.get_diff_stat(forecast_occupied - measured_occupied),
                }
            },
            'quantized_totals': {
                'observer': float(np.sum(self.observer_quantized)),
                'measured': float(np.sum(self.measured_quantized)),
                'forecast': float(np.sum(self.forecast_quantized)),
            },
            'quantized_errors': {
                'measured_vs_observer': self.get_diff_quant_stat(self.measured_quantized, self.observer_quantized),
                'forecast_vs_observer': self.get_diff_quant_stat(self.forecast_quantized, self.observer_quantized),
                'forecast_vs_measured': self.get_diff_quant_stat(self.forecast_quantized, self.measured_quantized),
            }
        }

        if self.gdf_file_duty is not None:
            gdf_file_occupied = np.array(self.gdf_file_duty > 0.0, dtype=float)

            report['duty_cycles']['gdf_file'] = float(np.average(self.gdf_file_duty))
            report['occupied']['gdf_file'] = float(np.average(gdf_file_occupied))

            report['duty_cycles']['differences'].update({
                'gdf_file_vs_observer':
                    self.get_diff_stat(self.gdf_file_duty - self.observer_duty),
                'gdf_file_vs_measured':
                    self.get_diff_stat(self.gdf_file_duty - self.measured_duty),
                'gdf_file_vs_forecast':
                    self.get_diff_stat(self.gdf_file_duty - self.forecast_duty),
            })

            report['occupied']['differences'].update({
                'gdf_file_vs_observer':
                    self.get_diff_stat(gdf_file_occupied - observer_occupied),
                'gdf_file_vs_measured':
                    self.get_diff_stat(gdf_file_occupied - measured_occupied),
                'gdf_file_vs_forecast':
                    self.get_diff_stat(gdf_file_occupied - forecast_occupied),
            })

        return report


def run(args=None):
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('directory', help="RESERVATION directory")
    parser.add_argument('--observer-srn', type=int,
                        help="override the observer SRN to be used")
    parser.add_argument('--gateway-srn', type=int,
                        help="override the gateway SRN to be used")
    parser.add_argument('--incumbent-srn', type=int,
                        help="override the incumbent SRN to be used")
    parser.add_argument('--threshold', type=float, default=-65,
                        help="The duty cycle threshold for the observer in dB")
    parser.add_argument('--extra', action='store_true',
                        help="include extra info into the report")
    parser.add_argument('--save', metavar='file',
                        help="save the json report to this file")
    parser.add_argument('--save-error', dest='save_error', action='store_true', default=False,
                        help="save the quantized error. Yellow=observed and not reported. Navy=reported and not observed. Green=both reported and observed")
    parser.add_argument('--time-start', type=float,
                        help="specifies the start time of the plot")
    parser.add_argument('--time-stop', type=float,
                        help="specifies the stop time of the plot")
    parser.add_argument('--time-bins', type=int, default=1024,
                        help="specifies the number of frequency bins")
    parser.add_argument('--time-step', type=float,
                        help="calculates the time bins parameter")
    parser.add_argument('--freq-start', type=float,
                        help="specifies the start freq of the plot")
    parser.add_argument('--freq-stop', type=float,
                        help="specifies the stop freq of the plot")
    parser.add_argument('--freq-bins', type=int, default=512,
                        help="specifies the number of frequency bins")
    parser.add_argument('--freq-step', type=float,
                        help="calculates the freq bins parameter")
    parser.add_argument('--gdf-file',
                        help="Load in this json geodata file from spec-val")

    args = parser.parse_args(args)
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)

    logging.info('Reading reservation info')

    res = ReservationReader(args.directory).read_all()
    res['observer_srn'] = args.observer_srn or res.get('observer_srn')
    res['gateway_srn'] = args.gateway_srn or res.get('gateway_srn')
    res['incumbent_srn'] = args.incumbent_srn or res.get('incumbent_srn')

    observer_dir = path.join(res['directory'],
                             res['nodes'][res['observer_srn']]['logs_dir'])
    gateway_pcap = path.join(res['directory'],
                             res['nodes'][res['gateway_srn']]['pcap_file'])

    spec_eval = SpecEval()
    spec_eval.read_observer_data(observer_dir)
    spec_eval.read_usage_data(
        gateway_pcap, res['gateway_srn'], res['incumbent_srn'])
    if args.gdf_file:
        spec_eval.read_gdf_data(args.gdf_file, res['rf_start_time'])

    spec_eval.set_bounds(args.time_start, args.time_stop, args.time_bins, args.time_step,
                         args.freq_start, args.freq_stop, args.freq_bins, args.freq_step)

    spec_eval.calculate_observer_duty_cylces(args.threshold)
    spec_eval.calculate_spectrum_usage_duty_cycles()
    if args.gdf_file:
        spec_eval.calculate_gdf_file_duty_cycles()

    report = spec_eval.create_report()
    report['srns'] = {
        'observer': res.get('observer_srn'),
        'gateway': res.get('gateway_srn'),
        'incumbent': res.get('incumbent_srn'),
        'collab_server': res.get('collab_server_srn'),
    }
    for name in ['directory', 'rf_start_time', 'duration', 'reservation']:
        report[name] = res.get(name)

    if args.extra:
        report['reservation_info'] = res
        report['observer_config'] = spec_eval.observer_config
        report['gateway_stats'] = spec_eval.gateway_stats

    if args.save_error:
        import matplotlib
        matplotlib.use('Agg')
        grid = SpectrumGrid(spec_eval.time_start, spec_eval.time_stop, spec_eval.time_bins, spec_eval.freq_start, spec_eval.freq_stop, spec_eval.freq_bins, spec_eval.measured_v_observer)
        title = 'Measured v. Observer (threshold = {:.0f}, error = {:.2f})'.format(args.threshold, report['quantized_errors']['measured_vs_observer']['total'])
        png_file = 'measured_v_observer.png'
        grid.plot_figure(time_start=args.time_start, time_stop=args.time_stop, freq_start=args.freq_start, freq_stop=args.freq_stop, title=title, png_file=png_file)

        grid = SpectrumGrid(spec_eval.time_start, spec_eval.time_stop, spec_eval.time_bins, spec_eval.freq_start, spec_eval.freq_stop, spec_eval.freq_bins, spec_eval.forecast_v_observer)
        title = 'Forecast v. Observer (threshold = {:.0f}, error = {:.2f})'.format(args.threshold, report['quantized_errors']['forecast_vs_observer']['total'])
        png_file = 'forecast_v_observer.png'
        grid.plot_figure(time_start=args.time_start, time_stop=args.time_stop, freq_start=args.freq_start, freq_stop=args.freq_stop, title=title, png_file=png_file)

    report = json.dumps(report, indent=2, sort_keys=True)
    if args.save:
        logging.info("Saving report to %s", args.save)
        with open(args.save, 'w') as f:
            f.write(report)
    else:
        print(report)


if __name__ == "__main__":
    run()
